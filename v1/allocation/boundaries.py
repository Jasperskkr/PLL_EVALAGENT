"""Deterministic conditional SystemSpec-boundary extraction for V1.5.

The sampled grid locates fail/pass cells.  This module refines one search-axis
boundary for every fixed condition-axis slice.  It deliberately stops at the
system boundary: no measured BlockSpec or engineering margin is allocated
here.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Sequence

from ..io import evidence_digest
from ..model.pll_behavioral import VCOParams
from ..specs import SystemSpec
from .design_space import DesignPointDefinition, DesignSpaceDefinition
from .multidim_evaluator import evaluate_design_point


BOUNDARY_METHOD = "sampled_bracket_then_deterministic_bisection"
BOUNDARY_OUTCOME = "system_boundary_mapped_block_spec_pending"


def _system_passed(record: Mapping[str, Any]) -> bool:
    return bool(record["system_tb"]["passed"])


def _failed_system_checks(record: Mapping[str, Any]) -> list[str]:
    return sorted(
        str(name)
        for name, passed in record["system_tb"]["checks"].items()
        if not passed
    )


def _common_failed_system_checks(
    records: Sequence[Mapping[str, Any]],
) -> list[str]:
    failed_sets = [set(_failed_system_checks(record)) for record in records]
    if not failed_sets:
        return []
    return sorted(set.intersection(*failed_sets))


def _compact_trial(record: Mapping[str, Any]) -> Dict[str, Any]:
    """Keep enough evidence to audit a refined boundary trial."""

    return {
        "point_id": str(record["point_id"]),
        "design_vector": dict(record["design_vector"]["values"]),
        "system_passed": _system_passed(record),
        "system_checks": dict(record["system_tb"]["checks"]),
        "system_metrics": dict(record["system_tb"]["metrics"]),
        "system_residuals": dict(record["system_tb"]["residuals"]),
        "block_tb_passed": bool(record["block_tb"]["passed"]),
        "context_covered": bool(record["context_coverage"]["passed"]),
        "behavior_vector": dict(record["behavior_vector"]),
    }


def _refined_trial(
    *,
    case: Mapping[str, Any],
    system_spec: SystemSpec,
    base_vco: VCOParams,
    design_space: DesignSpaceDefinition,
    values: Mapping[str, float],
    ordinal: int,
) -> Dict[str, Any]:
    point = DesignPointDefinition(
        point_id=design_space.point_id(values),
        ordinal=ordinal,
        values={str(name): float(value) for name, value in values.items()},
    )
    return evaluate_design_point(case, system_spec, base_vco, point)


def build_system_boundary_map(
    *,
    case: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    design_space: DesignSpaceDefinition,
    system_spec: SystemSpec,
    base_vco: VCOParams,
    sample_set_sha256: str,
) -> Dict[str, Any]:
    """Build ``search_axis_boundary(condition_axis)`` from SystemTB evidence.

    A slice is refined only when the sampled grid contains exactly one
    pass/fail transition and increasing the configured search axis moves from
    PASS to FAIL.  Slices with no feasible point, no failing point, or multiple
    transitions remain explicit non-mapped results instead of being compressed
    into a false scalar boundary.
    """

    config = dict(case.get("system_boundary_mapping", {}))
    if config.get("status") != "enabled":
        raise ValueError("system boundary mapping is not enabled")
    if config.get("method") != BOUNDARY_METHOD:
        raise ValueError(
            f"unsupported system boundary method: {config.get('method')}"
        )
    condition_axis = str(config.get("condition_axis", ""))
    search_axis = str(config.get("search_axis", ""))
    if condition_axis == search_axis or {
        condition_axis,
        search_axis,
    } != set(design_space.axis_order):
        raise ValueError(
            "V1.5 boundary mapping must name the two design-space axes"
        )
    if config.get("search_direction") != "increasing_value_moves_pass_to_fail":
        raise ValueError("unsupported system boundary search direction")
    iterations = int(config.get("refinement_iterations", 0))
    if iterations < 1:
        raise ValueError("system boundary refinement requires iterations >= 1")

    axis_map = {axis.name: axis for axis in design_space.axes}
    by_condition: dict[float, list[Mapping[str, Any]]] = {}
    for record in records:
        values = record["design_vector"]["values"]
        by_condition.setdefault(float(values[condition_axis]), []).append(record)

    expected_conditions = axis_map[condition_axis].values()
    if set(by_condition) != set(expected_conditions):
        raise ValueError("sampled records do not cover every condition-axis slice")

    slices: list[Dict[str, Any]] = []
    refined_count = 0
    for condition_value in expected_conditions:
        sampled = sorted(
            by_condition[float(condition_value)],
            key=lambda record: float(
                record["design_vector"]["values"][search_axis]
            ),
        )
        sampled_values = [
            float(record["design_vector"]["values"][search_axis])
            for record in sampled
        ]
        expected_search_values = list(axis_map[search_axis].values())
        if sampled_values != expected_search_values:
            raise ValueError(
                f"slice {condition_value} does not cover the search axis"
            )

        transitions: list[Dict[str, Any]] = []
        for left, right in zip(sampled, sampled[1:]):
            if _system_passed(left) == _system_passed(right):
                continue
            passing = left if _system_passed(left) else right
            failing = right if _system_passed(left) else left
            transitions.append(
                {
                    "passing_point_id": str(passing["point_id"]),
                    "passing_value": float(
                        passing["design_vector"]["values"][search_axis]
                    ),
                    "failing_point_id": str(failing["point_id"]),
                    "failing_value": float(
                        failing["design_vector"]["values"][search_axis]
                    ),
                    "failing_system_checks": _failed_system_checks(failing),
                }
            )

        pass_count = sum(_system_passed(record) for record in sampled)
        slice_result: Dict[str, Any] = {
            "condition": {
                "axis": condition_axis,
                "value": float(condition_value),
                "unit": axis_map[condition_axis].unit,
            },
            "sampled_summary": {
                "point_count": len(sampled),
                "system_pass_count": pass_count,
                "system_fail_count": len(sampled) - pass_count,
                "transition_count": len(transitions),
            },
            "sampled_transitions": transitions,
        }

        if pass_count == 0:
            slice_result.update(
                {
                    "status": "no_system_feasible_point_in_search_range",
                    "blocking_system_checks": _common_failed_system_checks(sampled),
                }
            )
            slices.append(slice_result)
            continue
        if pass_count == len(sampled):
            slice_result.update(
                {
                    "status": "boundary_not_bracketed_in_search_range",
                    "blocking_system_checks": [],
                }
            )
            slices.append(slice_result)
            continue
        if len(transitions) != 1:
            slice_result.update(
                {
                    "status": "multiple_system_boundaries_require_window_mapping",
                    "blocking_system_checks": sorted(
                        {
                            check
                            for transition in transitions
                            for check in transition["failing_system_checks"]
                        }
                    ),
                }
            )
            slices.append(slice_result)
            continue

        transition = transitions[0]
        passing_value = float(transition["passing_value"])
        failing_value = float(transition["failing_value"])
        if passing_value >= failing_value:
            slice_result.update(
                {
                    "status": "unsupported_transition_direction",
                    "blocking_system_checks": list(
                        transition["failing_system_checks"]
                    ),
                }
            )
            slices.append(slice_result)
            continue

        passing_record = next(
            record
            for record in sampled
            if str(record["point_id"]) == transition["passing_point_id"]
        )
        failing_record = next(
            record
            for record in sampled
            if str(record["point_id"]) == transition["failing_point_id"]
        )
        history: list[Dict[str, Any]] = [
            {"phase": "sampled_passing_bracket", **_compact_trial(passing_record)},
            {"phase": "sampled_failing_bracket", **_compact_trial(failing_record)},
        ]

        for iteration in range(iterations):
            midpoint = 0.5 * (passing_value + failing_value)
            values = {
                condition_axis: float(condition_value),
                search_axis: midpoint,
            }
            trial = _refined_trial(
                case=case,
                system_spec=system_spec,
                base_vco=base_vco,
                design_space=design_space,
                values=values,
                ordinal=-(iteration + 1),
            )
            history.append(
                {
                    "phase": "bisection",
                    "iteration": iteration,
                    **_compact_trial(trial),
                }
            )
            if _system_passed(trial):
                passing_value = midpoint
                passing_record = trial
            else:
                failing_value = midpoint
                failing_record = trial

        refined_count += 1
        slice_result.update(
            {
                "status": "refined_system_boundary",
                "initial_bracket": transition,
                "refined_boundary": {
                    "search_axis": search_axis,
                    "unit": axis_map[search_axis].unit,
                    "passing_value": passing_value,
                    "nearest_failing_value": failing_value,
                    "bracket_width": failing_value - passing_value,
                    "iterations": iterations,
                    "limiting_system_checks": _failed_system_checks(
                        failing_record
                    ),
                    "passing_evidence": _compact_trial(passing_record),
                    "nearest_failing_evidence": _compact_trial(failing_record),
                },
                "refinement_history": history,
            }
        )
        slices.append(slice_result)

    artifact: Dict[str, Any] = {
        "schema_version": "v1.5-system-boundary-map-1.0",
        "case_id": str(case["case_id"]),
        "map_type": "conditional_system_spec_boundary",
        "status": BOUNDARY_OUTCOME,
        "block_spec_mapping_status": "pending",
        "condition_axis": {
            "name": condition_axis,
            "unit": axis_map[condition_axis].unit,
        },
        "search_axis": {
            "name": search_axis,
            "unit": axis_map[search_axis].unit,
            "direction": config["search_direction"],
        },
        "membership_rule": "all immutable SystemSpec checks PASS",
        "refinement": {
            "method": "deterministic_bisection",
            "iterations": iterations,
        },
        "slice_count": len(slices),
        "mapped_boundary_count": refined_count,
        "unmapped_slice_count": len(slices) - refined_count,
        "slices": slices,
        "source_sample_set_sha256": sample_set_sha256,
        "claim_boundary": (
            "System-level conditional boundary evidence only; engineering "
            "margin and BlockSpec allocation remain pending."
        ),
        "provenance": {
            "builder": "v1.allocation.boundaries.build_system_boundary_map",
            "deterministic": True,
            "random_seed": None,
        },
    }
    artifact["boundary_map_sha256"] = evidence_digest(artifact)
    return artifact


__all__ = [
    "BOUNDARY_METHOD",
    "BOUNDARY_OUTCOME",
    "build_system_boundary_map",
]
