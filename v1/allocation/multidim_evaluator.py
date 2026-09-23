"""Joint BlockTB/SystemTB evaluation for one V1.5 design point."""

from __future__ import annotations

from dataclasses import asdict
import math
from typing import Any, Dict, Mapping, Sequence

from ..model.pll_behavioral import VCOParams
from ..pipeline import evaluate_system, measure_vco_behavior, strip_raw_results
from ..specs import SystemSpec
from ..api.verification import VerificationRequest
from ..backends.synthetic import SyntheticVCOConstraintBackend
from ..verification.service import verify_block_assignment
from .design_space import DesignPointDefinition
from .design_vector import DesignVector, compile_design_vector_to_vco


BEHAVIOR_VECTOR_FIELDS = (
    "worst_phase_noise_1mhz_dbc_hz",
    "kvco_min_hz_per_v",
    "kvco_max_hz_per_v",
    "frequency_min_hz",
    "frequency_max_hz",
    "worst_power_w",
)


def _resolve_reference(case: Mapping[str, Any], reference: str) -> Any:
    current: Any = case
    for part in reference.split("."):
        if not isinstance(current, Mapping) or part not in current:
            raise ValueError(f"case reference does not resolve: {reference}")
        current = current[part]
    return current


def _aggregate_system_checks(evaluation: Mapping[str, Any]) -> Dict[str, bool]:
    contexts = list(evaluation.get("per_context", []))
    names = sorted(
        {
            str(name)
            for context in contexts
            for name in context.get("checks", {})
        }
    )
    return {
        name: all(
            bool(context.get("checks", {}).get(name, False))
            for context in contexts
        )
        for name in names
    }


def evaluate_context_coverage(
    contract: Mapping[str, Any], actual: Mapping[str, Any]
) -> Dict[str, Any]:
    """Check whether actual SystemTB operation stays in the frozen contract."""

    tolerance = 1.0e-12
    checks = {
        "vctrl_min": float(actual["vctrl_min_v"])
        >= float(contract["vctrl_min_v"]) - tolerance,
        "vctrl_max": float(actual["vctrl_max_v"])
        <= float(contract["vctrl_max_v"]) + tolerance,
        "temperature": set(float(value) for value in actual["temperature_points_c"])
        .issubset(
            set(float(value) for value in contract["temperature_points_c"])
        ),
        "vdd": abs(float(actual["vdd_v"]) - float(contract["vdd_v"]))
        <= tolerance,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "contract_context_id": contract.get("context_id"),
        "actual_context": dict(actual),
    }


def _behavior_vector(measurement: Mapping[str, Any]) -> Dict[str, float]:
    worst = measurement["worst_case"]
    return {name: float(worst[name]) for name in BEHAVIOR_VECTOR_FIELDS}


def _evaluate_block_constraints(
    case: Mapping[str, Any],
    behavior_vector: Mapping[str, float],
    constraints: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    results: list[Dict[str, Any]] = []
    residuals: Dict[str, float | None] = {}
    checks: Dict[str, bool] = {}

    for constraint in constraints:
        constraint_id = str(constraint["constraint_id"])
        kind = str(constraint["kind"])
        result: Dict[str, Any] = {
            "constraint_id": constraint_id,
            "kind": kind,
        }
        residual: float | None

        if kind == "coverage":
            metric_names = list(constraint["measured_metrics"])
            if len(metric_names) != 2:
                raise ValueError(
                    f"coverage constraint {constraint_id} requires two metrics"
                )
            frequency_min = float(behavior_vector[str(metric_names[0])])
            frequency_max = float(behavior_vector[str(metric_names[1])])
            target = float(_resolve_reference(case, str(constraint["target_ref"])))
            tolerance = float(
                _resolve_reference(case, str(constraint["tolerance_ref"]))
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
                _resolve_reference(case, str(constraint["limit_ref"]))
                if constraint.get("limit_ref") is not None
                else constraint["limit"]
            )
            operator = str(constraint["operator"])
            if operator == ">":
                passed = value > limit
                residual = limit - value
            elif operator == ">=":
                passed = value >= limit
                residual = limit - value
            elif operator == "<=":
                passed = value <= limit
                residual = value - limit
            elif operator == "<":
                passed = value < limit
                residual = value - limit
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
            passed = not non_finite
            residual = None
            result["non_finite_metrics"] = non_finite
        else:
            raise ValueError(
                f"unsupported BlockTB constraint {constraint_id} ({kind})"
            )

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


def evaluate_design_point(
    case: Mapping[str, Any],
    system_spec: SystemSpec,
    base_vco: VCOParams,
    point: DesignPointDefinition,
) -> Dict[str, Any]:
    """Evaluate one point through one realized instance and both TBs."""

    case_id = str(case["case_id"])
    instance_id = f"Instance.{point.point_id}"
    design_vector = DesignVector(
        values=dict(point.values),
        source=f"{case_id}.design_space",
        version="1.5",
    )
    realized_vco = compile_design_vector_to_vco(base_vco, design_vector)

    block_context = dict(case["block_context"])
    verification = verify_block_assignment(
        VerificationRequest(
            system_spec=system_spec,
            block_spec={
                "kind": "constraint_set",
                "constraints": list(case["block_constraints"]),
            },
            realized_instance=realized_vco,
            operating_context=block_context,
            block_id="VCO",
            backend_id="synthetic_vco_v1_constraint_set",
            request_id=f"{case_id}:{point.point_id}",
            keep_raw=False,
        ),
        backend=SyntheticVCOConstraintBackend(case),
    )
    block_tb = dict(verification["block_tb"])
    block_tb["realized_instance_id"] = instance_id
    system_tb = dict(verification["system_tb"])
    system_tb["realized_instance_id"] = instance_id
    context_coverage = verification["context_coverage"]
    behavior_vector = dict(block_tb["behavior_vector"])
    system_checks = dict(system_tb["checks"])

    block_failed = sorted(
        name for name, passed in block_tb["checks"].items() if not passed
    )
    system_failed = sorted(
        name for name, passed in system_checks.items() if not passed
    )
    context_failed = sorted(
        name
        for name, passed in context_coverage["checks"].items()
        if not passed
    )
    jointly_feasible = bool(
        block_tb["passed"]
        and system_tb["passed"]
        and context_coverage["passed"]
    )
    failure_reasons = (
        [f"BlockTB:{name}" for name in block_failed]
        + [f"SystemTB:{name}" for name in system_failed]
        + [f"Context:{name}" for name in context_failed]
    )

    return {
        "schema_version": "v1.5-sampled-design-point-1.0",
        "case_id": case_id,
        "point_id": point.point_id,
        "ordinal": point.ordinal,
        "design_vector": design_vector.to_dict(),
        "realized_instance": {
            "instance_id": instance_id,
            "model": "synthetic_behavioral_vco_v1",
            "parameters": asdict(realized_vco),
        },
        "behavior_vector": behavior_vector,
        "block_tb": block_tb,
        "system_tb": system_tb,
        "context_coverage": context_coverage,
        "constraint_residual_vector": {
            "block": dict(block_tb["residuals"]),
            "system": dict(system_tb["residuals"]),
        },
        "status": {
            "block_feasible": bool(block_tb["passed"]),
            "system_constraints_passed": bool(system_tb["passed"]),
            "context_covered": bool(context_coverage["passed"]),
            "jointly_feasible": jointly_feasible,
            "failure_reasons": failure_reasons,
        },
        "provenance": {
            "evaluator": "v1.allocation.multidim_evaluator.evaluate_design_point",
            "system_model": "averaged_integer_n_cppll_v1",
            "block_model": "synthetic_behavioral_vco_v1",
            "deterministic": True,
            "random_seed": None,
        },
    }


__all__ = [
    "BEHAVIOR_VECTOR_FIELDS",
    "evaluate_context_coverage",
    "evaluate_design_point",
]
