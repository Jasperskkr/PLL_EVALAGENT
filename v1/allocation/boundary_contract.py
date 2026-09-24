"""Conditional BlockTB contract extraction at the V1.5 system boundary.

The system-boundary artifact is expressed in candidate-knob space.  This
module independently replays every passing side of that boundary under the
frozen BlockTB context and records the measured block behavior.  The result is
a discrete conditional contract, not yet an engineering-margin BlockSpec.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, Mapping

from ..io import evidence_digest
from ..model.pll_behavioral import VCOParams
from ..specs import SystemSpec
from .design_space import DesignPointDefinition, DesignSpaceDefinition
from .multidim_evaluator import evaluate_design_point


CONTRACT_METHOD = "independent_frozen_context_blocktb_replay"
CONTRACT_STATUS = "validated_boundary_block_contract"
WORKFLOW_OUTCOME = "boundary_block_contract_extracted_block_spec_pending"


def _measurement_context(case: Mapping[str, Any]) -> Dict[str, Any]:
    context = case["block_context"]
    return {
        "vctrl_min_v": float(context["vctrl_min_v"]),
        "vctrl_max_v": float(context["vctrl_max_v"]),
        "temperature_points_c": [
            float(value) for value in context["temperature_points_c"]
        ],
        "vdd_v": float(context["vdd_v"]),
        "source": context.get("source", "frozen VCOBlockContext"),
        "context_id": context["context_id"],
    }


def _context_contract_matches(
    actual: Mapping[str, Any], expected: Mapping[str, Any]
) -> bool:
    """Compare contract fields while allowing additive observation metadata."""

    return all(actual.get(name) == value for name, value in expected.items())


def _unchanged_hidden_parameters(
    base_vco: VCOParams,
    realized_parameters: Mapping[str, Any],
    design_values: Mapping[str, Any],
) -> bool:
    base_parameters = asdict(base_vco)
    design_names = set(design_values)
    return all(
        name in base_parameters
        and float(realized_parameters[name]) == float(value)
        for name, value in design_values.items()
    ) and all(
        realized_parameters.get(name) == value
        for name, value in base_parameters.items()
        if name not in design_names
    )


def extract_boundary_block_contract(
    *,
    case: Mapping[str, Any],
    system_boundary_map: Mapping[str, Any],
    design_space: DesignSpaceDefinition,
    system_spec: SystemSpec,
    base_vco: VCOParams,
) -> Dict[str, Any]:
    """Extract a replay-validated block-behavior table along the boundary."""

    config = dict(case.get("boundary_contract_extraction", {}))
    if config.get("status") != "enabled":
        raise ValueError("boundary contract extraction is not enabled")
    if config.get("method") != CONTRACT_METHOD:
        raise ValueError(
            f"unsupported boundary contract method: {config.get('method')}"
        )
    if config.get("source_boundary_side") != "passing":
        raise ValueError("boundary contract must use the passing boundary side")
    if config.get("contract_form") != "discrete_conditional_table":
        raise ValueError("unsupported V1.5 boundary contract form")
    if config.get("interpolation_allowed") is not False:
        raise ValueError("V1.5 boundary contract must not imply interpolation")

    condition_axis = str(system_boundary_map["condition_axis"]["name"])
    search_axis = str(system_boundary_map["search_axis"]["name"])
    if {condition_axis, search_axis} != set(design_space.axis_order):
        raise ValueError("boundary contract axes do not match the design space")

    expected_context = _measurement_context(case)
    entries: list[Dict[str, Any]] = []
    unmapped_slices: list[Dict[str, Any]] = []

    for slice_item in system_boundary_map.get("slices", []):
        condition = dict(slice_item["condition"])
        if slice_item.get("status") != "refined_system_boundary":
            unmapped_slices.append(
                {
                    "condition": condition,
                    "status": slice_item.get("status"),
                    "blocking_system_checks": list(
                        slice_item.get("blocking_system_checks", [])
                    ),
                }
            )
            continue

        boundary = slice_item["refined_boundary"]
        source_passing = boundary["passing_evidence"]
        values = {
            name: float(value)
            for name, value in source_passing["design_vector"].items()
        }
        expected_point_id = design_space.point_id(values)
        point = DesignPointDefinition(
            point_id=expected_point_id,
            ordinal=-(len(entries) + 1),
            values=values,
        )
        replay = evaluate_design_point(case, system_spec, base_vco, point)

        comparison = {
            "point_id_matches": (
                expected_point_id == str(source_passing["point_id"])
                and expected_point_id == str(replay["point_id"])
            ),
            "design_vector_matches": (
                replay["design_vector"]["values"]
                == source_passing["design_vector"]
            ),
            "block_behavior_identical": (
                replay["behavior_vector"] == source_passing["behavior_vector"]
            ),
            "block_pass_preserved": (
                bool(replay["block_tb"]["passed"])
                == bool(source_passing["block_tb_passed"])
                and bool(replay["block_tb"]["passed"])
            ),
            "system_boundary_pass_preserved": (
                bool(replay["system_tb"]["passed"])
                == bool(source_passing["system_passed"])
                and bool(replay["system_tb"]["passed"])
            ),
            "system_checks_identical": (
                replay["system_tb"]["checks"]
                == source_passing["system_checks"]
            ),
            "system_metrics_identical": (
                replay["system_tb"]["metrics"]
                == source_passing["system_metrics"]
            ),
            "system_residuals_identical": (
                replay["system_tb"]["residuals"]
                == source_passing["system_residuals"]
            ),
            "frozen_context_matches": _context_contract_matches(
                replay["block_tb"].get(
                    "characterization_window", replay["block_tb"]["context"]
                ),
                expected_context,
            ),
            "context_covered": (
                bool(replay["context_coverage"]["passed"])
                and bool(source_passing["context_covered"])
            ),
            "non_design_parameters_unchanged": _unchanged_hidden_parameters(
                base_vco,
                replay["realized_instance"]["parameters"],
                values,
            ),
        }
        comparison["passed"] = all(comparison.values())

        entries.append(
            {
                "condition": condition,
                "source_system_boundary": {
                    "search_axis": search_axis,
                    "unit": boundary["unit"],
                    "passing_value": float(boundary["passing_value"]),
                    "nearest_failing_value": float(
                        boundary["nearest_failing_value"]
                    ),
                    "bracket_width": float(boundary["bracket_width"]),
                    "limiting_system_checks": list(
                        boundary["limiting_system_checks"]
                    ),
                    "passing_point_id": str(source_passing["point_id"]),
                    "nearest_failing_point_id": str(
                        boundary["nearest_failing_evidence"]["point_id"]
                    ),
                },
                "contract_input": {
                    "independent_variables": values,
                    "frozen_context_id": expected_context["context_id"],
                },
                "realized_instance": dict(replay["realized_instance"]),
                "measured_block_behavior": dict(replay["behavior_vector"]),
                "block_tb": {
                    "passed": bool(replay["block_tb"]["passed"]),
                    "checks": dict(replay["block_tb"]["checks"]),
                    "residuals": dict(replay["block_tb"]["residuals"]),
                    "context": dict(replay["block_tb"]["context"]),
                    "measurement_method": replay["block_tb"][
                        "measurement_method"
                    ],
                },
                "system_boundary_confirmation": {
                    "passed": bool(replay["system_tb"]["passed"]),
                    "checks": dict(replay["system_tb"]["checks"]),
                    "metrics": dict(replay["system_tb"]["metrics"]),
                    "residuals": dict(replay["system_tb"]["residuals"]),
                },
                "independent_replay_validation": comparison,
            }
        )

    refined_conditions = {
        float(item["condition"]["value"])
        for item in system_boundary_map.get("slices", [])
        if item.get("status") == "refined_system_boundary"
    }
    entry_conditions = {float(item["condition"]["value"]) for item in entries}
    checks = {
        "source_boundary_hash_present": bool(
            system_boundary_map.get("boundary_map_sha256")
        ),
        "all_mapped_boundaries_extracted": (
            len(entries) == system_boundary_map.get("mapped_boundary_count")
            and entry_conditions == refined_conditions
        ),
        "unmapped_slices_preserved": len(unmapped_slices)
        == system_boundary_map.get("unmapped_slice_count"),
        "all_boundary_replays_pass": bool(entries)
        and all(
            item["independent_replay_validation"]["passed"] for item in entries
        ),
        "all_blocktb_measurements_pass": bool(entries)
        and all(item["block_tb"]["passed"] for item in entries),
        "all_system_boundary_points_pass": bool(entries)
        and all(item["system_boundary_confirmation"]["passed"] for item in entries),
        "all_contexts_frozen_and_covered": bool(entries)
        and all(
            item["independent_replay_validation"]["frozen_context_matches"]
            and item["independent_replay_validation"]["context_covered"]
            for item in entries
        ),
        "all_hidden_parameters_invariant": bool(entries)
        and all(
            item["independent_replay_validation"][
                "non_design_parameters_unchanged"
            ]
            for item in entries
        ),
    }
    validation = {
        "passed": all(checks.values()),
        "checks": checks,
        "entry_count": len(entries),
        "unmapped_slice_count": len(unmapped_slices),
    }
    if not validation["passed"]:
        failed = sorted(name for name, passed in checks.items() if not passed)
        raise ValueError(f"boundary block contract validation failed: {failed}")

    artifact: Dict[str, Any] = {
        "schema_version": "v1.5-boundary-block-contract-1.0",
        "case_id": str(case["case_id"]),
        "contract_id": "VCO.conditional_boundary_behavior.v1_5",
        "contract_type": "discrete_conditional_boundary_block_behavior",
        "status": CONTRACT_STATUS,
        "workflow_outcome": WORKFLOW_OUTCOME,
        "block_spec_mapping_status": "pending",
        "contract_form": "discrete_conditional_table",
        "interpolation_allowed": False,
        "condition_axis": dict(system_boundary_map["condition_axis"]),
        "search_axis": dict(system_boundary_map["search_axis"]),
        "semantics": {
            "independent_variables": list(design_space.axis_order),
            "derived_block_outputs": list(
                case["measurement_contract"]["behavior_vector"]
            ),
            "system_outputs": [
                "integrated_jitter_s",
                "lock_time_s",
                "output_frequency_hz",
                "power_w",
            ],
            "source_boundary_side": "passing",
        },
        "validity_domain": {
            "frozen_context": dict(case["block_context"]),
            "condition_values": sorted(entry_conditions),
            "only_listed_condition_values_validated": True,
            "interpolation_allowed": False,
            "model_fidelity": "synthetic_behavioral_vco_v1",
        },
        "measurement_method": CONTRACT_METHOD,
        "source_boundary_map_sha256": system_boundary_map[
            "boundary_map_sha256"
        ],
        "entry_count": len(entries),
        "entries": entries,
        "unmapped_slices": unmapped_slices,
        "validation": validation,
        "claim_boundary": (
            "Replay-validated boundary BlockTB behavior only; no interpolation, "
            "engineering margin, conditional BlockSpec, or transistor-level "
            "signoff is claimed."
        ),
        "provenance": {
            "builder": (
                "v1.allocation.boundary_contract."
                "extract_boundary_block_contract"
            ),
            "deterministic": True,
            "random_seed": None,
        },
    }
    artifact["contract_sha256"] = evidence_digest(artifact)
    return artifact


__all__ = [
    "CONTRACT_METHOD",
    "CONTRACT_STATUS",
    "WORKFLOW_OUTCOME",
    "extract_boundary_block_contract",
]
