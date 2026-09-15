"""Deterministic V1 SystemSpec-to-VCO-Spec pipeline.

This module deliberately keeps the orchestration small and explicit.  The
existing :func:`simulate_cppll` remains the canonical system simulator.  The
new code adds the missing seams around it:

* SystemSpec and VCO requirement evaluation;
* VCO characterization and finite-difference sweeps;
* a one-dimensional required phase-noise boundary search;
* context-aware VCO BlockTB validation;
* independent synthetic candidate construction.

The functions return JSON-serialisable dictionaries so a run can be replayed
without importing an agent or relying on hidden state.
"""

from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
import csv
import json
import math

from .model.pll_behavioral import CPPLLParams, VCOParams, simulate_cppll
from .specs import CandidateDefinition, SystemSpec, VCORequirement


def _jsonable(value: Any) -> Any:
    """Convert dataclasses and non-finite values to strict JSON values."""

    if hasattr(value, "__dataclass_fields__"):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def write_json(value: Any, path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(_jsonable(value), indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


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


def build_vco_instance(
    base_vco: VCOParams, candidate: CandidateDefinition | Mapping[str, Any] | None = None
) -> VCOParams:
    """Create a realized behavioral instance from a candidate source."""

    if candidate is None:
        return base_vco
    overrides = (
        candidate.overrides
        if isinstance(candidate, CandidateDefinition)
        else dict(candidate)
    )
    valid_names = set(asdict(base_vco))
    unknown = set(overrides) - valid_names
    if unknown:
        raise ValueError(f"unknown VCO parameter(s): {sorted(unknown)}")
    return replace(base_vco, **overrides)


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


def _aggregate_context(contexts: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    if not contexts:
        return {}
    return {
        "vctrl_min_v": min(float(item["vctrl_min_v"]) for item in contexts),
        "vctrl_max_v": max(float(item["vctrl_max_v"]) for item in contexts),
        "fosc_min_hz": min(float(item["fosc_min_hz"]) for item in contexts),
        "fosc_max_hz": max(float(item["fosc_max_hz"]) for item in contexts),
        "temperature_points_c": sorted(
            {float(item["temperature_c"]) for item in contexts}
        ),
        "vdd_v": contexts[0]["vdd_v"],
        "divider_n": contexts[0]["divider_n"],
        "f_ref_hz": contexts[0]["f_ref_hz"],
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
                "context": raw["context"],
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
    result: Dict[str, Any] = {
        "passed": aggregate_pass,
        "metrics": aggregate_metrics,
        "residuals": aggregate_residuals,
        "context": _aggregate_context([item["context"] for item in per_context]),
        "per_context": per_context,
    }
    if keep_raw:
        result["raw_results"] = raw_results
    return result


def characterize_vco(
    vco: VCOParams,
    vctrl_points_v: Iterable[float],
    temperature_points_c: Iterable[float],
    offset_points_hz: Iterable[float] = (1.0e6,),
) -> List[Dict[str, float]]:
    """Generate deterministic VCO observation data for the prove step."""

    rows: List[Dict[str, float]] = []
    for temperature_c in temperature_points_c:
        for vctrl_v in vctrl_points_v:
            power_w = vco.power_w(vctrl_v, temperature_c)
            for offset_hz in offset_points_hz:
                rows.append(
                    {
                        "temperature_c": float(temperature_c),
                        "vctrl_v": float(vctrl_v),
                        "offset_hz": float(offset_hz),
                        "fosc_hz": vco.frequency_hz(vctrl_v, temperature_c),
                        "kvco_hz_per_v": vco.kvco_hz_per_v(vctrl_v),
                        "power_w": power_w,
                        "phase_noise_dbc_hz": vco.phase_noise_dbc_hz(
                            offset_hz, vctrl_v, temperature_c, power_w
                        ),
                    }
                )
    return rows


def write_csv(rows: Sequence[Mapping[str, Any]], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        output_path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _metric_snapshot(evaluation: Mapping[str, Any]) -> Dict[str, Any]:
    metrics = evaluation["metrics"]
    return {
        "output_frequency_hz": metrics["output_frequency_hz"],
        "integrated_jitter_s": metrics["integrated_jitter_s"],
        "lock_time_s": metrics["lock_time_s"],
        "power_w": metrics["power_w"],
        "kvco_hz_per_v": metrics["kvco_hz_per_v"],
        "loop_bandwidth_hz": metrics["loop_bandwidth_hz"],
        "passed": evaluation["passed"],
    }


def run_parameter_sweep(
    system_spec: SystemSpec,
    base_vco: VCOParams,
    parameter: str,
    values: Sequence[float],
    model_overrides: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Sweep one realized VCO parameter and record top-level metrics."""

    if not values:
        raise ValueError(f"empty sweep for {parameter}")
    rows: List[Dict[str, Any]] = []
    for value in values:
        vco = build_vco_instance(base_vco, {parameter: value})
        evaluation = evaluate_system(system_spec, vco, model_overrides, keep_raw=False)
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
    results = {
        parameter: run_parameter_sweep(
            system_spec, base_vco, parameter, values, model_overrides
        )
        for parameter, values in sweeps.items()
    }
    return {
        "method": "deterministic_finite_difference_and_grid_sweep",
        "base_vco": asdict(base_vco),
        "sweeps": results,
    }


def abstract_pn_evaluation(
    system_spec: SystemSpec,
    base_vco: VCOParams,
    phase_noise_1mhz_max_dbc_hz: float,
    model_overrides: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Evaluate an abstract VCO capability envelope for allocation.

    The phase-noise scalar is used as an allocation knob.  This is explicitly
    *not* a realized candidate: candidate feasibility is checked separately by
    :func:`validate_vco_spec`.
    """

    abstract_vco = replace(
        base_vco, pn_1mhz_dbc_hz=float(phase_noise_1mhz_max_dbc_hz)
    )
    evaluation = evaluate_system(
        system_spec, abstract_vco, model_overrides=model_overrides, keep_raw=False
    )
    return {
        "phase_noise_1mhz_max_dbc_hz": phase_noise_1mhz_max_dbc_hz,
        "system_evaluation": evaluation,
    }


def search_required_pn_boundary(
    system_spec: SystemSpec,
    base_vco: VCOParams,
    loose_bound_dbc_hz: float,
    tight_bound_dbc_hz: float,
    iterations: int = 24,
    model_overrides: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Find the least-stringent passing PN upper bound by bisection."""

    if loose_bound_dbc_hz <= tight_bound_dbc_hz:
        raise ValueError("loose PN bound must be numerically greater than tight bound")
    loose = abstract_pn_evaluation(
        system_spec, base_vco, loose_bound_dbc_hz, model_overrides
    )
    tight = abstract_pn_evaluation(
        system_spec, base_vco, tight_bound_dbc_hz, model_overrides
    )
    if loose["system_evaluation"]["passed"]:
        raise ValueError("loose PN search bound already passes; no boundary bracket")
    if not tight["system_evaluation"]["passed"]:
        raise ValueError("tight PN search bound still fails; increase search range")

    history: List[Dict[str, Any]] = [
        {"phase": "bracket", "bound": loose_bound_dbc_hz, "passed": False},
        {"phase": "bracket", "bound": tight_bound_dbc_hz, "passed": True},
    ]
    passing = float(tight_bound_dbc_hz)
    failing = float(loose_bound_dbc_hz)
    for index in range(iterations):
        midpoint = 0.5 * (passing + failing)
        trial = abstract_pn_evaluation(
            system_spec, base_vco, midpoint, model_overrides
        )
        passed = bool(trial["system_evaluation"]["passed"])
        history.append(
            {
                "phase": "bisection",
                "iteration": index,
                "bound": midpoint,
                "passed": passed,
                "residuals": trial["system_evaluation"]["residuals"],
            }
        )
        if passed:
            passing = midpoint
        else:
            failing = midpoint
    return {
        "metric": "phase_noise_1mhz_dbc_hz",
        "direction": "upper_bound; more_negative_is_tighter",
        "required_boundary": passing,
        "nearest_failing_bound": failing,
        "bracket_width": failing - passing,
        "iterations": iterations,
        "history": history,
    }


def _sample_points(lower: float, upper: float, count: int) -> List[float]:
    if count < 2:
        return [lower]
    return [lower + (upper - lower) * index / (count - 1) for index in range(count)]


def validate_vco_spec(
    system_spec: SystemSpec,
    requirement: VCORequirement,
    vco: VCOParams,
    system_context: Mapping[str, Any],
    vctrl_points: int = 11,
) -> Dict[str, Any]:
    """Context-aware VCO BlockTB for a realized candidate."""

    context_vctrl_min = float(system_context["vctrl_min_v"])
    context_vctrl_max = float(system_context["vctrl_max_v"])
    if context_vctrl_min > context_vctrl_max:
        raise ValueError("invalid system Vctrl context")
    vctrl_values = _sample_points(context_vctrl_min, context_vctrl_max, vctrl_points)
    temperatures = list(system_spec.temperature_points_c)
    observations: List[Dict[str, Any]] = []
    for temperature_c in temperatures:
        for vctrl_v in vctrl_values:
            power_w = vco.power_w(vctrl_v, temperature_c)
            observations.append(
                {
                    "temperature_c": temperature_c,
                    "vctrl_v": vctrl_v,
                    "fosc_hz": vco.frequency_hz(vctrl_v, temperature_c),
                    "kvco_hz_per_v": vco.kvco_hz_per_v(vctrl_v),
                    "phase_noise_1mhz_dbc_hz": vco.phase_noise_dbc_hz(
                        1.0e6, vctrl_v, temperature_c, power_w
                    ),
                    "power_w": power_w,
                }
            )

    checks: Dict[str, bool] = {}
    worst_pn = max(item["phase_noise_1mhz_dbc_hz"] for item in observations)
    checks["phase_noise_1mhz"] = (
        worst_pn <= requirement.phase_noise_1mhz_max_dbc_hz
    )
    frequencies = [item["fosc_hz"] for item in observations]
    frequency_span = max(frequencies) - min(frequencies)
    target_low = system_spec.target_frequency_hz - system_spec.output_frequency_tolerance_hz
    target_high = system_spec.target_frequency_hz + system_spec.output_frequency_tolerance_hz
    checks["target_frequency_covered"] = min(frequencies) <= target_low and max(frequencies) >= target_high
    if requirement.tuning_range_min_hz is not None:
        checks["tuning_range_min"] = frequency_span >= requirement.tuning_range_min_hz
    if requirement.kvco_min_hz_per_v is not None:
        checks["kvco_min"] = min(item["kvco_hz_per_v"] for item in observations) >= requirement.kvco_min_hz_per_v
    if requirement.kvco_max_hz_per_v is not None:
        checks["kvco_max"] = max(item["kvco_hz_per_v"] for item in observations) <= requirement.kvco_max_hz_per_v
    if requirement.power_max_w is not None:
        checks["power"] = max(item["power_w"] for item in observations) <= requirement.power_max_w

    pn_margin = requirement.phase_noise_1mhz_max_dbc_hz - worst_pn
    result = {
        "passed": all(checks.values()),
        "checks": checks,
        "requirement": requirement.to_dict(),
        "context": {
            "vctrl_min_v": context_vctrl_min,
            "vctrl_max_v": context_vctrl_max,
            "temperature_points_c": temperatures,
            "source": "SystemTB operating envelope",
        },
        "worst_case": {
            "phase_noise_1mhz_dbc_hz": worst_pn,
            "phase_noise_margin_db": pn_margin,
            "fosc_min_hz": min(frequencies),
            "fosc_max_hz": max(frequencies),
            "tuning_range_hz": frequency_span,
            "kvco_min_hz_per_v": min(item["kvco_hz_per_v"] for item in observations),
            "kvco_max_hz_per_v": max(item["kvco_hz_per_v"] for item in observations),
            "power_max_w": max(item["power_w"] for item in observations),
        },
        "observations": observations,
    }
    return result


def strip_raw_results(evaluation: Mapping[str, Any]) -> Dict[str, Any]:
    """Remove large histories before writing compact evaluation summaries."""

    return {key: value for key, value in evaluation.items() if key != "raw_results"}
