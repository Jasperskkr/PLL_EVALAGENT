"""Deterministic sampled-region construction for V1.5 allocation."""

from __future__ import annotations

from hashlib import sha256
import json
from math import prod
from typing import Any, Dict, Mapping, Sequence

from .design_space import DesignSpaceDefinition
from .multidim_evaluator import BEHAVIOR_VECTOR_FIELDS


SYSTEM_METRIC_FIELDS = (
    "integrated_jitter_s",
    "lock_time_s",
    "output_frequency_hz",
    "power_w",
)


def _artifact_digest(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _record_map(
    records: Sequence[Mapping[str, Any]],
    design_space: DesignSpaceDefinition,
) -> dict[int, Mapping[str, Any]]:
    by_ordinal: dict[int, Mapping[str, Any]] = {}
    point_ids: set[str] = set()
    for record in records:
        ordinal = int(record["ordinal"])
        point_id = str(record["point_id"])
        if ordinal in by_ordinal:
            raise ValueError(f"duplicate sampled-point ordinal: {ordinal}")
        if point_id in point_ids:
            raise ValueError(f"duplicate sampled-point id: {point_id}")
        by_ordinal[ordinal] = record
        point_ids.add(point_id)
    expected_ordinals = set(range(design_space.expected_point_count))
    if set(by_ordinal) != expected_ordinals:
        raise ValueError("sampled-point ordinals do not close the design space")
    return by_ordinal


def _numeric_bounds(
    members: Sequence[Mapping[str, Any]],
    vector_name: str,
    fields: Sequence[str],
) -> Dict[str, Dict[str, float | None]]:
    result: Dict[str, Dict[str, float | None]] = {}
    for field in fields:
        values = [
            float(member[vector_name][field])
            for member in members
            if member[vector_name].get(field) is not None
        ]
        result[field] = {
            "min": min(values) if values else None,
            "max": max(values) if values else None,
        }
    return result


def _boundary_transitions(
    records: Sequence[Mapping[str, Any]],
    design_space: DesignSpaceDefinition,
    status_key: str,
) -> list[Dict[str, Any]]:
    """Return adjacent grid edges whose membership verdict changes."""

    by_ordinal = _record_map(records, design_space)
    axis_map = {axis.name: axis for axis in design_space.axes}
    shape = [len(axis_map[name].values()) for name in design_space.axis_order]
    transitions: list[Dict[str, Any]] = []

    for ordinal in range(design_space.expected_point_count):
        record = by_ordinal[ordinal]
        for axis_index, axis_name in enumerate(design_space.axis_order):
            stride = prod(shape[axis_index + 1 :])
            coordinate_index = (ordinal // stride) % shape[axis_index]
            if coordinate_index + 1 >= shape[axis_index]:
                continue
            neighbor = by_ordinal[ordinal + stride]
            current_status = bool(record["status"][status_key])
            neighbor_status = bool(neighbor["status"][status_key])
            if current_status == neighbor_status:
                continue
            feasible = record if current_status else neighbor
            infeasible = neighbor if current_status else record
            transitions.append(
                {
                    "axis": axis_name,
                    "point_a": str(record["point_id"]),
                    "point_b": str(neighbor["point_id"]),
                    "value_a": float(
                        record["design_vector"]["values"][axis_name]
                    ),
                    "value_b": float(
                        neighbor["design_vector"]["values"][axis_name]
                    ),
                    "feasible_point_id": str(feasible["point_id"]),
                    "infeasible_point_id": str(infeasible["point_id"]),
                    "infeasible_reasons": list(
                        infeasible["status"]["failure_reasons"]
                    ),
                }
            )
    return transitions


def build_capability_region(
    case_id: str,
    records: Sequence[Mapping[str, Any]],
    design_space: DesignSpaceDefinition,
    sample_set_sha256: str,
) -> Dict[str, Any]:
    """Build the BlockTB-pass region in measured Behavior space."""

    _record_map(records, design_space)
    members = [
        {
            "point_id": str(record["point_id"]),
            "ordinal": int(record["ordinal"]),
            "realized_instance_id": str(
                record["realized_instance"]["instance_id"]
            ),
            "behavior_vector": dict(record["behavior_vector"]),
            "block_constraint_residuals": dict(
                record["constraint_residual_vector"]["block"]
            ),
            "sampled_point_ref": (
                f"sampled_points.jsonl#point_id={record['point_id']}"
            ),
        }
        for record in records
        if record["status"]["block_feasible"]
    ]
    if any(
        not record["status"]["block_feasible"]
        for record in records
        if str(record["point_id"])
        in {str(member["point_id"]) for member in members}
    ):
        raise ValueError("BlockTB-failing point entered Capability Region")

    artifact: Dict[str, Any] = {
        "schema_version": "v1.5-capability-region-1.0",
        "case_id": case_id,
        "region_type": "block_capability_region",
        "formal_status": "sampled_discrete",
        "representation_space": "measured_behavior",
        "axes": list(BEHAVIOR_VECTOR_FIELDS),
        "membership_rule": "BlockTB PASS under frozen VCOBlockContext.v1_5",
        "member_count": len(members),
        "members": members,
        "behavior_bounds_summary": _numeric_bounds(
            members,
            "behavior_vector",
            BEHAVIOR_VECTOR_FIELDS,
        ),
        "boundary_transitions": _boundary_transitions(
            records,
            design_space,
            "block_feasible",
        ),
        "topology_preserved_as_sampled_points": True,
        "bounds_are_summary_not_region_definition": True,
        "source_sample_set_sha256": sample_set_sha256,
        "provenance": {
            "builder": "v1.allocation.regions.build_capability_region",
            "deterministic": True,
        },
    }
    artifact["region_sha256"] = _artifact_digest(artifact)
    return artifact


def build_system_feasible_region(
    case_id: str,
    records: Sequence[Mapping[str, Any]],
    design_space: DesignSpaceDefinition,
    sample_set_sha256: str,
) -> Dict[str, Any]:
    """Build the joint BlockTB/context/SystemTB feasible region."""

    _record_map(records, design_space)
    members: list[Dict[str, Any]] = []
    for record in records:
        if not record["status"]["jointly_feasible"]:
            continue
        if not (
            record["status"]["block_feasible"]
            and record["status"]["system_constraints_passed"]
            and record["status"]["context_covered"]
        ):
            raise ValueError("jointly feasible point lacks complete TB closure")
        members.append(
            {
                "point_id": str(record["point_id"]),
                "ordinal": int(record["ordinal"]),
                "realized_instance_id": str(
                    record["realized_instance"]["instance_id"]
                ),
                "design_vector": dict(record["design_vector"]["values"]),
                "behavior_vector": dict(record["behavior_vector"]),
                "system_metric_vector": {
                    field: record["system_tb"]["metrics"].get(field)
                    for field in SYSTEM_METRIC_FIELDS
                },
                "constraint_residual_vector": {
                    "block": dict(
                        record["constraint_residual_vector"]["block"]
                    ),
                    "system": dict(
                        record["constraint_residual_vector"]["system"]
                    ),
                },
                "sampled_point_ref": (
                    f"sampled_points.jsonl#point_id={record['point_id']}"
                ),
            }
        )

    design_axes = list(design_space.axis_order)
    artifact: Dict[str, Any] = {
        "schema_version": "v1.5-system-feasible-region-1.0",
        "case_id": case_id,
        "region_type": "joint_system_feasible_region",
        "formal_status": "sampled_discrete",
        "representation_space": "design_vector_with_measured_evidence",
        "design_axes": design_axes,
        "membership_rule": (
            "BlockTB PASS and context covered and all immutable SystemSpec checks PASS"
        ),
        "member_count": len(members),
        "members": members,
        "design_bounds_summary": _numeric_bounds(
            members,
            "design_vector",
            design_axes,
        ),
        "behavior_bounds_summary": _numeric_bounds(
            members,
            "behavior_vector",
            BEHAVIOR_VECTOR_FIELDS,
        ),
        "system_metric_bounds_summary": _numeric_bounds(
            members,
            "system_metric_vector",
            SYSTEM_METRIC_FIELDS,
        ),
        "boundary_transitions": _boundary_transitions(
            records,
            design_space,
            "jointly_feasible",
        ),
        "topology_preserved_as_sampled_points": True,
        "bounds_are_summary_not_region_definition": True,
        "source_sample_set_sha256": sample_set_sha256,
        "provenance": {
            "builder": "v1.allocation.regions.build_system_feasible_region",
            "deterministic": True,
        },
    }
    artifact["region_sha256"] = _artifact_digest(artifact)
    return artifact


__all__ = [
    "SYSTEM_METRIC_FIELDS",
    "build_capability_region",
    "build_system_feasible_region",
]
