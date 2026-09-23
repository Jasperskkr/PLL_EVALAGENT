"""Deterministic evaluation of declarative V1.5 BlockTB constraints."""

from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Sequence


def resolve_case_reference(case: Mapping[str, Any], reference: str) -> Any:
    current: Any = case
    for part in reference.split("."):
        if not isinstance(current, Mapping) or part not in current:
            raise ValueError(f"case reference does not resolve: {reference}")
        current = current[part]
    return current


def evaluate_block_constraints(
    case: Mapping[str, Any],
    behavior_vector: Mapping[str, float],
    constraints: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Return checks/residuals for a measured behavior vector."""

    results: list[Dict[str, Any]] = []
    residuals: Dict[str, float | None] = {}
    checks: Dict[str, bool] = {}

    for constraint in constraints:
        constraint_id = str(constraint["constraint_id"])
        kind = str(constraint["kind"])
        result: Dict[str, Any] = {"constraint_id": constraint_id, "kind": kind}

        if kind == "coverage":
            metric_names = list(constraint["measured_metrics"])
            if len(metric_names) != 2:
                raise ValueError(
                    f"coverage constraint {constraint_id} requires two metrics"
                )
            frequency_min = float(behavior_vector[str(metric_names[0])])
            frequency_max = float(behavior_vector[str(metric_names[1])])
            target = float(resolve_case_reference(case, str(constraint["target_ref"])))
            tolerance = float(
                resolve_case_reference(case, str(constraint["tolerance_ref"]))
            )
            lower_target = target - tolerance
            upper_target = target + tolerance
            lower_residual = frequency_min - lower_target
            upper_residual = upper_target - frequency_max
            residual = max(lower_residual, upper_residual)
            passed = lower_residual <= 0.0 and upper_residual <= 0.0
            result.update(
                {
                    "measured": {
                        str(metric_names[0]): frequency_min,
                        str(metric_names[1]): frequency_max,
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
            value = float(behavior_vector[metric])
            limit = float(
                resolve_case_reference(case, str(constraint["limit_ref"]))
                if constraint.get("limit_ref") is not None
                else constraint["limit"]
            )
            operator = str(constraint["operator"])
            if operator == ">":
                passed, residual = value > limit, limit - value
            elif operator == ">=":
                passed, residual = value >= limit, limit - value
            elif operator == "<=":
                passed, residual = value <= limit, value - limit
            elif operator == "<":
                passed, residual = value < limit, value - limit
            else:
                raise ValueError(
                    f"unsupported operator for {constraint_id}: {operator}"
                )
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


__all__ = ["evaluate_block_constraints", "resolve_case_reference"]
