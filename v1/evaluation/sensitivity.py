"""Deterministic parameter sweeps for characterization and sensitivity evidence.

These tools report observations and derivatives; they do not allocate specs."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List, Mapping, Optional, Sequence

from . import system as system_evaluation
from ..model.instances import build_vco_instance, canonical_vco_parameter
from ..model.pll_behavioral import VCOParams
from ..specs import SystemSpec


def run_parameter_sweep(
    system_spec: SystemSpec,
    base_vco: VCOParams,
    parameter: str,
    values: Sequence[float],
    model_overrides: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Sweep one realized VCO parameter and record top-level metrics."""

    parameter = canonical_vco_parameter(parameter)
    if not values:
        raise ValueError(f"empty sweep for {parameter}")
    rows: List[Dict[str, Any]] = []
    for value in values:
        vco = build_vco_instance(base_vco, {parameter: value})
        evaluation = system_evaluation.evaluate_system(system_spec, vco, model_overrides, keep_raw=False)
        metrics = evaluation["metrics"]
        rows.append(
            {
                "parameter": parameter,
                "value": float(value),
                "output_frequency_hz": metrics["output_frequency_hz"],
                "integrated_jitter_s": metrics["integrated_jitter_s"],
                "lock_time_s": metrics["lock_time_s"],
                "power_w": metrics["power_w"],
                "kvco_hz_per_v": metrics["kvco_hz_per_v"],
                "loop_bandwidth_hz": metrics["loop_bandwidth_hz"],
                "passed": evaluation["passed"],
            }
        )
    derivatives: Dict[str, Any] = {}
    if len(rows) >= 3:
        center_index = min(range(len(rows)), key=lambda index: abs(rows[index]["value"] - float(getattr(base_vco, parameter))))
        if 0 < center_index < len(rows) - 1:
            left = rows[center_index - 1]
            center = rows[center_index]
            right = rows[center_index + 1]
            step = float(right["value"]) - float(left["value"])
            if step != 0.0:
                for metric in ("output_frequency_hz", "integrated_jitter_s", "lock_time_s", "power_w"):
                    left_value = left[metric]
                    right_value = right[metric]
                    derivatives[metric] = (
                        None
                        if left_value is None or right_value is None
                        else (float(right_value) - float(left_value)) / step
                    )
            derivatives["center_value"] = center["value"]
    return {"parameter": parameter, "rows": rows, "local_derivatives": derivatives}


def run_sensitivity_suite(
    system_spec: SystemSpec,
    base_vco: VCOParams,
    sweeps: Mapping[str, Sequence[float]],
    model_overrides: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    normalized_sweeps: Dict[str, Sequence[float]] = {}
    for parameter, values in sweeps.items():
        canonical = canonical_vco_parameter(str(parameter))
        if canonical in normalized_sweeps and list(normalized_sweeps[canonical]) != list(values):
            raise ValueError(f"conflicting sweep aliases for {canonical}")
        normalized_sweeps[canonical] = values
    results = {
        parameter: run_parameter_sweep(
            system_spec, base_vco, parameter, values, model_overrides
        )
        for parameter, values in normalized_sweeps.items()
    }
    return {
        "method": "deterministic_finite_difference_and_grid_sweep",
        "base_vco": asdict(base_vco),
        "sweeps": results,
    }
