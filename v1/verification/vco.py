"""VCO requirement judgment using shared deterministic measurements."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, Mapping

from ..evaluation.vco import measure_vco_behavior
from ..model.instances import canonical_vco_parameter
from ..model.pll_behavioral import VCOParams
from ..specs import SystemSpec, VCORequirement


def validate_vco_spec(
    system_spec: SystemSpec,
    requirement: VCORequirement,
    vco: VCOParams,
    system_context: Mapping[str, Any],
    vctrl_points: int = 11,
) -> Dict[str, Any]:
    """Context-aware VCO BlockTB for a realized candidate."""

    measurement = measure_vco_behavior(
        system_spec,
        vco,
        system_context,
        vctrl_points=vctrl_points,
    )
    return check_vco_spec(system_spec, requirement, measurement)


def check_vco_spec(
    system_spec: SystemSpec,
    requirement: VCORequirement,
    measurement: Mapping[str, Any],
) -> Dict[str, Any]:
    """Judge measured behavior without remeasuring or mutating the observation."""

    worst = measurement["worst_case"]
    checks: Dict[str, bool] = {}
    worst_pn = float(worst["worst_phase_noise_1mhz_dbc_hz"])
    checks["phase_noise_1mhz"] = (
        worst_pn <= requirement.phase_noise_1mhz_max_dbc_hz
    )
    target_low = system_spec.target_frequency_hz - system_spec.output_frequency_tolerance_hz
    target_high = system_spec.target_frequency_hz + system_spec.output_frequency_tolerance_hz
    checks["target_frequency_covered"] = (
        float(worst["frequency_min_hz"]) <= target_low
        and float(worst["frequency_max_hz"]) >= target_high
    )
    if requirement.tuning_range_min_hz is not None:
        checks["tuning_range_min"] = (
            float(worst["tuning_range_hz"]) >= requirement.tuning_range_min_hz
        )
    if requirement.kvco_min_hz_per_v is not None:
        checks["kvco_min"] = (
            float(worst["kvco_min_hz_per_v"]) >= requirement.kvco_min_hz_per_v
        )
    if requirement.kvco_max_hz_per_v is not None:
        checks["kvco_max"] = (
            float(worst["kvco_max_hz_per_v"]) <= requirement.kvco_max_hz_per_v
        )
    if requirement.power_max_w is not None:
        checks["power"] = float(worst["worst_power_w"]) <= requirement.power_max_w

    result = {
        **measurement,
        "passed": all(checks.values()),
        "checks": checks,
        "requirement": requirement.to_dict(),
    }
    result["worst_case"] = {
        **dict(worst),
        "phase_noise_margin_db": requirement.phase_noise_1mhz_max_dbc_hz - worst_pn,
    }
    return result


def validate_vco_scalar_requirement(
    system_spec: SystemSpec,
    *,
    parameter: str,
    relation: str,
    required_value: float,
    vco: VCOParams,
    system_context: Mapping[str, Any],
    validity_min: float | None = None,
    validity_max: float | None = None,
    vctrl_points: int = 11,
) -> Dict[str, Any]:
    """Context-aware BlockTB for one allocated behavioral VCO requirement.

    The internal scalar is only the search knob that produced the candidate.
    Requirement verdicts are computed from measured Block behavior under the
    frozen VCOBlockContext.
    """

    parameter = canonical_vco_parameter(parameter)
    if relation not in {"min", "max"}:
        raise ValueError("scalar VCO requirement relation must be min or max")
    realized_parameters = asdict(vco)
    if parameter not in realized_parameters:
        raise ValueError(f"unknown scalar VCO requirement parameter: {parameter}")

    measurement = measure_vco_behavior(
        system_spec,
        vco,
        system_context,
        vctrl_points=vctrl_points,
    )
    worst = measurement["worst_case"]
    if parameter == "pn_anchor_1mhz_dbc_hz":
        measured_metric = "worst_phase_noise_1mhz_dbc_hz"
        behavior_metric = "phase_noise_1mhz_dbc_hz"
    elif parameter == "k1_hz_per_v":
        measured_metric = "kvco_min_hz_per_v" if relation == "min" else "kvco_max_hz_per_v"
        behavior_metric = "kvco_hz_per_v"
    elif parameter == "nominal_power_w":
        measured_metric = "power_min_w" if relation == "min" else "worst_power_w"
        behavior_metric = "power_w"
    elif parameter == "f0_hz":
        measured_metric = "frequency_max_hz" if relation == "min" else "frequency_min_hz"
        behavior_metric = "frequency_hz"
    else:
        raise ValueError(
            f"no measured behavior mapping for scalar VCO requirement: {parameter}"
        )

    measured_value = float(worst[measured_metric])
    requirement_passed = (
        measured_value >= float(required_value)
        if relation == "min"
        else measured_value <= float(required_value)
    )
    checks: Dict[str, bool] = {
        f"{behavior_metric}_{relation}": requirement_passed
    }

    design_knob_value = float(realized_parameters[parameter])
    allocation_domain_checks: Dict[str, bool] = {}
    if validity_min is not None or validity_max is not None:
        lower = float("-inf") if validity_min is None else float(validity_min)
        upper = float("inf") if validity_max is None else float(validity_max)
        allocation_domain_checks["within_allocation_search_domain"] = (
            lower <= design_knob_value <= upper
        )
    if parameter == "f0_hz":
        target_low = system_spec.target_frequency_hz - system_spec.output_frequency_tolerance_hz
        target_high = system_spec.target_frequency_hz + system_spec.output_frequency_tolerance_hz
        checks["target_frequency_covered"] = (
            float(worst["frequency_min_hz"]) <= target_low
            and float(worst["frequency_max_hz"]) >= target_high
        )

    return {
        **measurement,
        "passed": all(checks.values()) and all(allocation_domain_checks.values()),
        "checks": checks,
        "allocation_domain_checks": allocation_domain_checks,
        "requirement": {
            "search_knob": parameter,
            "relation": relation,
            "required_value": float(required_value),
            "behavior_metric": behavior_metric,
            "measured_metric": measured_metric,
            "validity_domain": {
                "parameter_min": validity_min,
                "parameter_max": validity_max,
            },
        },
        "measured_requirement": {
            "metric": measured_metric,
            "value": measured_value,
            "required_value": float(required_value),
            "relation": relation,
            "passed": requirement_passed,
        },
        "design_knob": {
            "parameter": parameter,
            "value": design_knob_value,
            "used_for_requirement_verdict": False,
        },
    }
