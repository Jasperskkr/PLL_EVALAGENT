"""Explicit, deterministic candidate selection and replay evidence for V1.5."""

from __future__ import annotations

from dataclasses import asdict
from math import prod
from typing import Any, Dict, Mapping, Sequence

from ..model.pll_behavioral import VCOParams
from ..io import evidence_digest
from .design_space import DesignSpaceDefinition


SELECTION_METHOD = "lexicographic_interior_min_cost_v1"


def _resolve_reference(case: Mapping[str, Any], reference: str) -> Any:
    current: Any = case
    for part in reference.split("."):
        if not isinstance(current, Mapping) or part not in current:
            raise ValueError(f"case reference does not resolve: {reference}")
        current = current[part]
    return current


def _interior_joint_points(
    records: Sequence[Mapping[str, Any]],
    design_space: DesignSpaceDefinition,
) -> list[Mapping[str, Any]]:
    by_ordinal = {int(record["ordinal"]): record for record in records}
    if len(by_ordinal) != design_space.expected_point_count:
        raise ValueError("selection requires a closed sampled design space")
    axis_map = {axis.name: axis for axis in design_space.axes}
    shape = [len(axis_map[name].values()) for name in design_space.axis_order]
    eligible: list[Mapping[str, Any]] = []

    for ordinal in range(design_space.expected_point_count):
        record = by_ordinal[ordinal]
        if not record["status"]["jointly_feasible"]:
            continue
        all_neighbors_feasible = True
        for axis_index, _axis_name in enumerate(design_space.axis_order):
            stride = prod(shape[axis_index + 1 :])
            coordinate_index = (ordinal // stride) % shape[axis_index]
            if coordinate_index == 0 or coordinate_index + 1 == shape[axis_index]:
                all_neighbors_feasible = False
                break
            lower = by_ordinal[ordinal - stride]
            upper = by_ordinal[ordinal + stride]
            if not (
                lower["status"]["jointly_feasible"]
                and upper["status"]["jointly_feasible"]
            ):
                all_neighbors_feasible = False
                break
        if all_neighbors_feasible:
            eligible.append(record)
    return eligible


def _engineering_cost(
    record: Mapping[str, Any],
    design_space: DesignSpaceDefinition,
    base_vco: VCOParams,
) -> tuple[float, Dict[str, float]]:
    base = asdict(base_vco)
    axis_map = {axis.name: axis for axis in design_space.axes}
    values = record["design_vector"]["values"]
    components: Dict[str, float] = {}
    for name in design_space.axis_order:
        axis = axis_map[name]
        span = float(axis.stop) - float(axis.start)
        if span <= 0.0:
            raise ValueError(f"selection axis has zero span: {name}")
        if name not in base:
            raise ValueError(f"selection axis is not a base VCO parameter: {name}")
        components[name] = abs(float(values[name]) - float(base[name])) / span
    return sum(components.values()), components


def _normalized_active_margins(
    case: Mapping[str, Any], record: Mapping[str, Any]
) -> Dict[str, float]:
    residuals = record["system_tb"]["residuals"]
    margins: Dict[str, float] = {}
    for constraint in case["system_constraints"]["active_for_region"]:
        check = str(constraint["check"])
        residual_name = str(constraint["residual"])
        residual = residuals.get(residual_name)
        if residual is None:
            raise ValueError(f"selection residual is unavailable: {residual_name}")
        limit = abs(float(_resolve_reference(case, str(constraint["limit_ref"]))))
        if limit <= 0.0:
            raise ValueError(f"selection limit must be positive: {check}")
        margins[check] = -float(residual) / limit
    return margins


def select_candidate(
    case: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    design_space: DesignSpaceDefinition,
    base_vco: VCOParams,
) -> Dict[str, Any]:
    """Select one sampled interior point using an explicit lexicographic rule."""

    config = case["selection"]
    if config.get("status") != "enabled":
        raise ValueError("V1.5 candidate selection is not enabled")
    if config.get("method") != SELECTION_METHOD:
        raise ValueError(f"unsupported selection method: {config.get('method')}")
    if config.get("pareto_enabled") is not False:
        raise ValueError("V1.5-A selection must not claim Pareto")
    if config.get("require_all_immediate_grid_neighbors_feasible") is not True:
        raise ValueError("selection must require an interior sampled point")

    jointly_feasible = [
        record for record in records if record["status"]["jointly_feasible"]
    ]
    interior = _interior_joint_points(records, design_space)
    if not interior:
        raise ValueError("no interior jointly feasible point is available")

    ranked: list[Dict[str, Any]] = []
    for record in interior:
        cost, cost_components = _engineering_cost(
            record,
            design_space,
            base_vco,
        )
        margins = _normalized_active_margins(case, record)
        ranked.append(
            {
                "point_id": str(record["point_id"]),
                "ordinal": int(record["ordinal"]),
                "design_vector": dict(record["design_vector"]["values"]),
                "engineering_cost": cost,
                "engineering_cost_components": cost_components,
                "normalized_active_margins": margins,
                "minimum_normalized_active_margin": min(margins.values()),
            }
        )

    ranked.sort(
        key=lambda item: (
            float(item["engineering_cost"]),
            -float(item["minimum_normalized_active_margin"]),
            str(item["point_id"]),
        )
    )
    for rank, item in enumerate(ranked, start=1):
        item["rank"] = rank
    selected = ranked[0]
    sampled_record = next(
        record
        for record in records
        if str(record["point_id"]) == selected["point_id"]
    )

    artifact: Dict[str, Any] = {
        "schema_version": "v1.5-selection-decision-1.0",
        "case_id": str(case["case_id"]),
        "method": SELECTION_METHOD,
        "pareto_claimed": False,
        "hard_constraints": (
            "BlockTB PASS, context covered, and all immutable SystemSpec checks PASS"
        ),
        "interior_rule": (
            "all immediate grid neighbors on every design axis exist and are jointly feasible"
        ),
        "engineering_cost": (
            "sum of absolute distance from base VCO, normalized by each axis span"
        ),
        "margin_normalization": "negative SystemSpec residual divided by absolute limit",
        "tie_break_order": [
            "engineering_cost_ascending",
            "minimum_normalized_active_margin_descending",
            "point_id_ascending",
        ],
        "eligible_counts": {
            "jointly_feasible": len(jointly_feasible),
            "interior_jointly_feasible": len(interior),
        },
        "selected_candidate": {
            **selected,
            "candidate_id": f"Candidate.{selected['point_id']}",
            "realized_instance_id": sampled_record["realized_instance"][
                "instance_id"
            ],
            "sampled_point_ref": (
                f"sampled_points.jsonl#point_id={selected['point_id']}"
            ),
        },
        "ranked_interior_candidates": ranked,
        "independent_replay_required": True,
        "provenance": {
            "selector": "v1.allocation.selection.select_candidate",
            "deterministic": True,
            "random_seed": None,
        },
    }
    artifact["selection_sha256"] = evidence_digest(artifact)
    return artifact


def build_replay_evidence(
    selection_decision: Mapping[str, Any],
    sampled_record: Mapping[str, Any],
    replay_record: Mapping[str, Any],
) -> Dict[str, Any]:
    """Compare an independently recomputed point with its sampled evidence."""

    selected_id = str(selection_decision["selected_candidate"]["point_id"])
    if str(sampled_record["point_id"]) != selected_id:
        raise ValueError("sampled replay source is not the selected point")
    if str(replay_record["point_id"]) != selected_id:
        raise ValueError("independent replay evaluated the wrong point")

    comparisons = {
        "design_vector_identical": (
            sampled_record["design_vector"] == replay_record["design_vector"]
        ),
        "realized_instance_identical": (
            sampled_record["realized_instance"]
            == replay_record["realized_instance"]
        ),
        "behavior_vector_identical": (
            sampled_record["behavior_vector"] == replay_record["behavior_vector"]
        ),
        "block_tb_identical": (
            sampled_record["block_tb"] == replay_record["block_tb"]
        ),
        "system_tb_identical": (
            sampled_record["system_tb"] == replay_record["system_tb"]
        ),
        "context_coverage_identical": (
            sampled_record["context_coverage"]
            == replay_record["context_coverage"]
        ),
        "residual_vector_identical": (
            sampled_record["constraint_residual_vector"]
            == replay_record["constraint_residual_vector"]
        ),
        "status_identical": sampled_record["status"] == replay_record["status"],
    }
    artifact: Dict[str, Any] = {
        "schema_version": "v1.5-selected-candidate-replay-1.0",
        "case_id": str(sampled_record["case_id"]),
        "selected_point_id": selected_id,
        "selection_sha256": selection_decision["selection_sha256"],
        "sampled_record_sha256": evidence_digest(sampled_record),
        "replay_record_sha256": evidence_digest(replay_record),
        "comparisons": comparisons,
        "identical_to_sampled_evaluation": all(comparisons.values()),
        "replay_jointly_feasible": bool(
            replay_record["status"]["jointly_feasible"]
        ),
        "replay_record": dict(replay_record),
        "provenance": {
            "builder": "v1.allocation.selection.build_replay_evidence",
            "replay_mode": "independent_recompile_and_reevaluate",
            "deterministic": True,
        },
    }
    artifact["replay_sha256"] = evidence_digest(artifact)
    return artifact


__all__ = [
    "SELECTION_METHOD",
    "build_replay_evidence",
    "select_candidate",
]
