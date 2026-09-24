"""Judgment of measured behavior against declarative BlockSpec constraints."""

from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Sequence

from ..evaluation.constraints import BEHAVIOR_VECTOR_FIELDS


def _reference_paths(value: Any, prefix: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(value, Mapping):
        for name, child in value.items():
            path = f"{prefix}.{name}" if prefix else str(name)
            paths.extend(_reference_paths(child, path))
    elif prefix:
        paths.append(prefix)
    return paths


def resolve_reference(references: Mapping[str, Any], reference: str) -> Any:
    """Resolve a dotted reference and report useful alternatives on failure."""

    current: Any = references
    for part in reference.split("."):
        if not isinstance(current, Mapping) or part not in current:
            available = ", ".join(_reference_paths(references))
            raise ValueError(
                f"reference does not resolve: {reference}; "
                f"available references: {available}"
            )
        current = current[part]
    return current


def validate_constraint_references(
    references: Mapping[str, Any],
    constraints: Sequence[Mapping[str, Any]],
) -> None:
    """Resolve every ``*_ref`` before any constraint verdict is produced."""

    for constraint in constraints:
        constraint_id = str(constraint.get("constraint_id", "<missing>"))
        for field, reference in constraint.items():
            if field.endswith("_ref"):
                if not isinstance(reference, str) or not reference:
                    raise ValueError(
                        f"constraint {constraint_id} has invalid {field}: {reference!r}"
                    )
                resolve_reference(references, reference)


def evaluate_block_constraints(
    references: Mapping[str, Any],
    behavior_vector: Mapping[str, float],
    constraints: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Return deterministic checks/residuals for measured block behavior."""

    if not constraints:
        raise ValueError("constraint_set must contain at least one constraint")
    missing_metrics = sorted(set(BEHAVIOR_VECTOR_FIELDS) - set(behavior_vector))
    if missing_metrics:
        raise ValueError(f"behavior vector is missing metrics: {missing_metrics}")
    validate_constraint_references(references, constraints)

    identifiers = [str(item.get("constraint_id", "")) for item in constraints]
    if any(not identifier for identifier in identifiers):
        raise ValueError("every constraint requires a non-empty constraint_id")
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("constraint_id values must be unique")

    results: list[Dict[str, Any]] = []
    residuals: Dict[str, float | None] = {}
    checks: Dict[str, bool] = {}

    for constraint in constraints:
        constraint_id = str(constraint["constraint_id"])
        kind = str(constraint["kind"])
        result: Dict[str, Any] = {"constraint_id": constraint_id, "kind": kind}

        if kind == "coverage":
            metric_names = [str(name) for name in constraint["measured_metrics"]]
            if len(metric_names) != 2:
                raise ValueError(
                    f"coverage constraint {constraint_id} requires two metrics"
                )
            unknown = sorted(set(metric_names) - set(behavior_vector))
            if unknown:
                raise ValueError(
                    f"constraint {constraint_id} uses unknown metrics: {unknown}"
                )
            frequency_min = float(behavior_vector[metric_names[0]])
            frequency_max = float(behavior_vector[metric_names[1]])
            target = float(resolve_reference(references, str(constraint["target_ref"])))
            tolerance = float(
                resolve_reference(references, str(constraint["tolerance_ref"]))
            )
            if tolerance < 0.0:
                raise ValueError(f"constraint {constraint_id} has negative tolerance")
            lower_target = target - tolerance
            upper_target = target + tolerance
            lower_residual = frequency_min - lower_target
            upper_residual = upper_target - frequency_max
            residual = max(lower_residual, upper_residual)
            passed = lower_residual <= 0.0 and upper_residual <= 0.0
            result.update(
                {
                    "measured": {
                        metric_names[0]: frequency_min,
                        metric_names[1]: frequency_max,
                    },
                    "required_interval_hz": [lower_target, upper_target],
                    "component_residuals": {
                        "lower_coverage_residual_hz": lower_residual,
                        "upper_coverage_residual_hz": upper_residual,
                    },
                }
            )
        elif kind in {"lower_bound", "upper_bound"}:
            metric = str(constraint["measured_metric"])
            if metric not in behavior_vector:
                raise ValueError(
                    f"constraint {constraint_id} uses unknown metric: {metric}"
                )
            value = float(behavior_vector[metric])
            has_reference = constraint.get("limit_ref") is not None
            has_literal = "limit" in constraint
            if has_reference == has_literal:
                raise ValueError(
                    f"constraint {constraint_id} requires exactly one of limit/limit_ref"
                )
            limit = float(
                resolve_reference(references, str(constraint["limit_ref"]))
                if has_reference
                else constraint["limit"]
            )
            operator = str(constraint["operator"])
            allowed = {"lower_bound": {">", ">="}, "upper_bound": {"<", "<="}}
            if operator not in allowed[kind]:
                raise ValueError(
                    f"constraint {constraint_id} kind {kind} cannot use {operator}"
                )
            if operator == ">":
                passed, residual = value > limit, limit - value
            elif operator == ">=":
                passed, residual = value >= limit, limit - value
            elif operator == "<=":
                passed, residual = value <= limit, value - limit
            else:
                passed, residual = value < limit, value - limit
            result.update(
                {
                    "measured_metric": metric,
                    "measured_value": value,
                    "operator": operator,
                    "limit": limit,
                }
            )
        elif kind == "validity" and constraint_id == "finite_behavior_vector":
            non_finite = sorted(
                name
                for name, value in behavior_vector.items()
                if not math.isfinite(float(value))
            )
            passed, residual = not non_finite, None
            result["non_finite_metrics"] = non_finite
        else:
            raise ValueError(f"unsupported BlockTB constraint {constraint_id} ({kind})")

        result["passed"] = passed
        result["residual"] = residual
        results.append(result)
        checks[constraint_id] = passed
        residuals[constraint_id] = residual

    return {
        "passed": all(checks.values()),
        "checks": checks,
        "residuals": residuals,
        "constraint_results": results,
    }


__all__ = [
    "evaluate_block_constraints",
    "resolve_reference",
    "validate_constraint_references",
]
