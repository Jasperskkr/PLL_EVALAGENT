"""Deterministic system metrics, context and immutable SystemSpec residuals.

No boundary search, candidate selection or BlockSpec judgment belongs here.
The historical SystemTB checks are retained as part of the evaluation result."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List, Mapping, Optional, Sequence

from ..model.pll_behavioral import CPPLLParams, VCOParams, simulate_cppll
from ..specs import SystemSpec


def build_pll_params(
    system_spec: SystemSpec,
    temperature_c: float,
    model_overrides: Optional[Mapping[str, Any]] = None,
) -> CPPLLParams:
    """Build a simulator configuration from an immutable SystemSpec."""

    defaults = asdict(CPPLLParams())
    defaults.update(
        {
            "f_ref_hz": system_spec.f_ref_hz,
            "divider_n": system_spec.divider_n,
            "vdd_v": system_spec.vdd_v,
            "temperature_c": temperature_c,
            "vctrl_initial_v": system_spec.vctrl_initial_v,
            "vctrl_min_v": system_spec.vctrl_min_v,
            "vctrl_max_v": system_spec.vctrl_max_v,
            "jitter_f_low_hz": system_spec.jitter_f_low_hz,
            "jitter_f_high_hz": system_spec.jitter_f_high_hz,
            "jitter_points": system_spec.jitter_points,
        }
    )
    if model_overrides:
        valid_names = set(defaults)
        unknown = set(model_overrides) - valid_names
        if unknown:
            raise ValueError(f"unknown CPPLL parameter(s): {sorted(unknown)}")
        defaults.update(model_overrides)
    # The SystemSpec is authoritative for these values.  A case cannot change
    # pass criteria by passing a simulator override.
    defaults.update(
        {
            "f_ref_hz": system_spec.f_ref_hz,
            "divider_n": system_spec.divider_n,
            "vdd_v": system_spec.vdd_v,
            "temperature_c": temperature_c,
            "vctrl_initial_v": system_spec.vctrl_initial_v,
            "vctrl_min_v": system_spec.vctrl_min_v,
            "vctrl_max_v": system_spec.vctrl_max_v,
            "jitter_f_low_hz": system_spec.jitter_f_low_hz,
            "jitter_f_high_hz": system_spec.jitter_f_high_hz,
            "jitter_points": system_spec.jitter_points,
        }
    )
    return CPPLLParams(**defaults)


def evaluate_system_residuals(
    system_spec: SystemSpec, raw_result: Mapping[str, Any]
) -> Dict[str, Any]:
    """Evaluate immutable SystemSpec pass criteria against one raw run."""

    metrics = raw_result["metrics"]
    output_error = abs(float(metrics["output_frequency_hz"]) - system_spec.target_frequency_hz)
    jitter_residual = float(metrics["integrated_jitter_s"]) - system_spec.integrated_jitter_max_s
    lock_time = metrics.get("lock_time_s")
    lock_residual = None if lock_time is None else float(lock_time) - system_spec.lock_time_max_s
    power = float(metrics["power_w"])
    power_residual = None if system_spec.power_max_w is None else power - system_spec.power_max_w
    residuals = {
        "output_frequency_error_hz": output_error,
        "output_frequency_residual_hz": output_error
        - system_spec.output_frequency_tolerance_hz,
        "integrated_jitter_residual_s": jitter_residual,
        "lock_time_residual_s": lock_residual,
        "power_residual_w": power_residual,
    }
    checks = {
        "output_frequency": output_error <= system_spec.output_frequency_tolerance_hz,
        "integrated_jitter": jitter_residual <= 0.0,
        "lock_time": lock_time is not None and lock_residual is not None and lock_residual <= 0.0,
        "power": power_residual is None or power_residual <= 0.0,
        "locked": bool(raw_result.get("locked", False)),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "residuals": residuals,
    }


def _aggregate_trajectory_envelope(
    envelopes: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Aggregate observed SystemTB trajectories without implying capability."""

    if not envelopes:
        return {}
    return {
        "vctrl_min_v": min(float(item["vctrl_min_v"]) for item in envelopes),
        "vctrl_max_v": max(float(item["vctrl_max_v"]) for item in envelopes),
        "fosc_min_hz": min(float(item["fosc_min_hz"]) for item in envelopes),
        "fosc_max_hz": max(float(item["fosc_max_hz"]) for item in envelopes),
        "temperature_points_c": sorted(
            {float(item["temperature_c"]) for item in envelopes}
        ),
        "vdd_v": envelopes[0]["vdd_v"],
        "divider_n": envelopes[0]["divider_n"],
        "f_ref_hz": envelopes[0]["f_ref_hz"],
        "reached_lower_rail": any(
            bool(item.get("reached_lower_rail", False)) for item in envelopes
        ),
        "reached_upper_rail": any(
            bool(item.get("reached_upper_rail", False)) for item in envelopes
        ),
        "settled_from": [dict(item["settled_from"]) for item in envelopes],
        "semantics": "observed_simulation_trajectory_envelope",
    }


def _aggregate_metrics(raw_results: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    if not raw_results:
        raise ValueError("at least one raw system result is required")
    metric_names = [
        "output_frequency_hz",
        "integrated_jitter_s",
        "lock_time_s",
        "power_w",
        "phase_noise_100khz_dbc_hz",
        "phase_noise_1mhz_dbc_hz",
        "phase_noise_10mhz_dbc_hz",
        "kvco_hz_per_v",
        "loop_bandwidth_hz",
        "effective_noise_shaping_bandwidth_hz",
        "final_relative_frequency_error",
        "final_vctrl_v",
    ]
    metrics: Dict[str, Any] = {}
    # Worst-case values for upper-bound requirements; nominal values for the
    # remaining diagnostics are retained from the first context.
    first = raw_results[0]["metrics"]
    for name in metric_names:
        metrics[name] = first.get(name)
    metrics["output_frequency_hz_min"] = min(
        float(item["metrics"]["output_frequency_hz"]) for item in raw_results
    )
    metrics["output_frequency_hz_max"] = max(
        float(item["metrics"]["output_frequency_hz"]) for item in raw_results
    )
    metrics["integrated_jitter_s_worst"] = max(
        float(item["metrics"]["integrated_jitter_s"]) for item in raw_results
    )
    metrics["power_worst_w"] = max(float(item["metrics"]["power_w"]) for item in raw_results)
    lock_times = [item["metrics"].get("lock_time_s") for item in raw_results]
    metrics["lock_time_s_worst"] = (
        None if any(value is None for value in lock_times) else max(float(value) for value in lock_times)
    )
    metrics["locked_all_contexts"] = all(bool(item.get("locked", False)) for item in raw_results)
    # The compact SystemEvaluation exposes worst-case values as its canonical
    # metrics.  The per-context section retains the nominal and corner values.
    metrics["integrated_jitter_s"] = metrics["integrated_jitter_s_worst"]
    metrics["power_w"] = metrics["power_worst_w"]
    metrics["lock_time_s"] = metrics["lock_time_s_worst"]
    return metrics


def evaluate_system(
    system_spec: SystemSpec,
    vco: VCOParams,
    model_overrides: Optional[Mapping[str, Any]] = None,
    keep_raw: bool = True,
) -> Dict[str, Any]:
    """Run SystemTB in all configured temperature contexts."""

    raw_results: List[Dict[str, Any]] = []
    per_context: List[Dict[str, Any]] = []
    for temperature_c in system_spec.temperature_points_c:
        pll = build_pll_params(system_spec, temperature_c, model_overrides)
        raw = simulate_cppll(pll, vco)
        raw_results.append(raw)
        residual = evaluate_system_residuals(system_spec, raw)
        per_context.append(
            {
                "temperature_c": temperature_c,
                "metrics": raw["metrics"],
                "trajectory_envelope": raw["trajectory_envelope"],
                "context": raw["trajectory_envelope"],
                **residual,
            }
        )

    aggregate_metrics = _aggregate_metrics(raw_results)
    # Evaluate pass/fail per context, then retain a compact aggregate residual
    # view for the allocator and report.
    aggregate_pass = all(item["passed"] for item in per_context)
    aggregate_residuals = {
        "output_frequency_error_hz_max": max(
            float(item["residuals"]["output_frequency_error_hz"]) for item in per_context
        ),
        "output_frequency_residual_hz_max": max(
            float(item["residuals"]["output_frequency_residual_hz"]) for item in per_context
        ),
        "integrated_jitter_residual_s_max": max(
            float(item["residuals"]["integrated_jitter_residual_s"]) for item in per_context
        ),
        "lock_time_residual_s_max": (
            None
            if any(item["residuals"]["lock_time_residual_s"] is None for item in per_context)
            else max(float(item["residuals"]["lock_time_residual_s"]) for item in per_context)
        ),
        "power_residual_w_max": (
            None
            if all(item["residuals"]["power_residual_w"] is None for item in per_context)
            else max(
                float(item["residuals"]["power_residual_w"])
                for item in per_context
                if item["residuals"]["power_residual_w"] is not None
            )
        ),
    }
    trajectory_envelope = _aggregate_trajectory_envelope(
        [item["trajectory_envelope"] for item in per_context]
    )
    result: Dict[str, Any] = {
        "passed": aggregate_pass,
        "metrics": aggregate_metrics,
        "residuals": aggregate_residuals,
        "trajectory_envelope": trajectory_envelope,
        # Compatibility alias for pre-refactor artifact readers.
        "context": trajectory_envelope,
        "per_context": per_context,
    }
    if keep_raw:
        result["raw_results"] = raw_results
    return result


def strip_raw_results(evaluation: Mapping[str, Any]) -> Dict[str, Any]:
    """Remove large histories before writing compact evaluation summaries."""

    return {key: value for key, value in evaluation.items() if key != "raw_results"}
