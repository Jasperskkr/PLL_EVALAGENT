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


LEGACY_VCO_PARAMETER_ALIASES = {
    "pn_1mhz_dbc_hz": "pn_anchor_1mhz_dbc_hz",
}


def canonical_vco_parameter(name: str) -> str:
    return LEGACY_VCO_PARAMETER_ALIASES.get(str(name), str(name))


def normalize_vco_overrides(overrides: Mapping[str, Any] | None) -> Dict[str, Any]:
    """Normalize legacy case names at the loading boundary."""

    normalized: Dict[str, Any] = {}
    for name, value in dict(overrides or {}).items():
        canonical = canonical_vco_parameter(str(name))
        if canonical in normalized and normalized[canonical] != value:
            raise ValueError(f"conflicting VCO override aliases for {canonical}")
        normalized[canonical] = value
    return normalized


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
    overrides = normalize_vco_overrides(overrides)
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

    parameter = canonical_vco_parameter(parameter)
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


def abstract_pn_evaluation(
    system_spec: SystemSpec,
    base_vco: VCOParams,
    pn_anchor_1mhz_dbc_hz: float,
    model_overrides: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Evaluate an abstract VCO capability envelope for allocation.

    The phase-noise scalar is used as an allocation knob.  This is explicitly
    *not* a realized candidate: candidate feasibility is checked separately by
    :func:`validate_vco_spec`.
    """

    abstract_vco = replace(
        base_vco, pn_anchor_1mhz_dbc_hz=float(pn_anchor_1mhz_dbc_hz)
    )
    evaluation = evaluate_system(
        system_spec, abstract_vco, model_overrides=model_overrides, keep_raw=False
    )
    return {
        "search_knob": "pn_anchor_1mhz_dbc_hz",
        "search_knob_value": float(pn_anchor_1mhz_dbc_hz),
        "pn_anchor_1mhz_dbc_hz": float(pn_anchor_1mhz_dbc_hz),
        "target_system_metric": "integrated_jitter_s",
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
        failed_checks = sorted(
            {
                str(name)
                for context in tight["system_evaluation"].get("per_context", [])
                for name, passed in context.get("checks", {}).items()
                if not passed
            }
        )
        non_pn_failures = [
            name for name in failed_checks if name != "integrated_jitter"
        ]
        if non_pn_failures:
            raise ValueError(
                "PN-only allocation infeasible; non-PN SystemSpec checks still "
                f"fail at the tight bound: {', '.join(non_pn_failures)}"
            )
        raise ValueError("tight PN search bound still fails; increase search range")

    history: List[Dict[str, Any]] = [
        {
            "phase": "bracket",
            "value": loose_bound_dbc_hz,
            "target_passed": False,
            "system_passed": bool(loose["system_evaluation"]["passed"]),
            "metrics": _metric_snapshot(loose["system_evaluation"]),
            "residuals": loose["system_evaluation"]["residuals"],
        },
        {
            "phase": "bracket",
            "value": tight_bound_dbc_hz,
            "target_passed": True,
            "system_passed": bool(tight["system_evaluation"]["passed"]),
            "metrics": _metric_snapshot(tight["system_evaluation"]),
            "residuals": tight["system_evaluation"]["residuals"],
        },
    ]
    passing = float(tight_bound_dbc_hz)
    failing = float(loose_bound_dbc_hz)
    passing_evaluation = tight["system_evaluation"]
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
                "value": midpoint,
                "target_passed": passed,
                "system_passed": bool(trial["system_evaluation"]["passed"]),
                "metrics": _metric_snapshot(trial["system_evaluation"]),
                "residuals": trial["system_evaluation"]["residuals"],
            }
        )
        if passed:
            passing = midpoint
            passing_evaluation = trial["system_evaluation"]
        else:
            failing = midpoint
    return {
        "search_knob": "pn_anchor_1mhz_dbc_hz",
        "search_knob_boundary": passing,
        "target_system_metric": "integrated_jitter_s",
        "target_system_metric_at_boundary": passing_evaluation["metrics"].get(
            "integrated_jitter_s"
        ),
        "block_metric_at_boundary": None,
        "validity_domain": {
            "search_knob_min": min(float(loose_bound_dbc_hz), float(tight_bound_dbc_hz)),
            "search_knob_max": max(float(loose_bound_dbc_hz), float(tight_bound_dbc_hz)),
        },
        "direction": "upper_bound; more_negative_is_tighter",
        "nearest_failing_search_knob": failing,
        "bracket_width": failing - passing,
        "iterations": iterations,
        "history": history,
    }


SYSTEM_CHECK_RESIDUALS = {
    "integrated_jitter": "integrated_jitter_residual_s_max",
    "lock_time": "lock_time_residual_s_max",
    "output_frequency": "output_frequency_residual_hz_max",
    "power": "power_residual_w_max",
}


def _aggregate_checks(evaluation: Mapping[str, Any]) -> Dict[str, bool]:
    """Normalize the per-context SystemTB checks used by an allocation proof."""

    contexts = list(evaluation.get("per_context", []))
    if contexts:
        names = {
            str(name)
            for context in contexts
            for name in context.get("checks", {})
        }
        return {
            name: all(bool(context.get("checks", {}).get(name, False)) for context in contexts)
            for name in sorted(names)
        }
    return {
        str(name): bool(passed)
        for name, passed in evaluation.get("checks", {}).items()
    }


def _target_check_passes(evaluation: Mapping[str, Any], target_check: str) -> bool:
    checks = _aggregate_checks(evaluation)
    if target_check not in checks:
        raise ValueError(f"unknown SystemTB target check: {target_check}")
    if target_check == "lock_time":
        return bool(checks[target_check] and checks.get("locked", False))
    return bool(checks[target_check])


def abstract_vco_parameter_evaluation(
    system_spec: SystemSpec,
    base_vco: VCOParams,
    parameter: str,
    value: float,
    *,
    model_overrides: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Run SystemTB with one behavioral VCO parameter changed.

    This is the scalar seam used by the multi-mapping proof suite.  The
    returned object is an abstract allocation trial, not evidence that a
    physical VCO can realize the value; a BlockTB must check that separately.
    """

    parameter = canonical_vco_parameter(parameter)
    abstract_vco = build_vco_instance(base_vco, {parameter: float(value)})
    return {
        "parameter": parameter,
        "value": float(value),
        "system_evaluation": evaluate_system(
            system_spec,
            abstract_vco,
            model_overrides=model_overrides,
            keep_raw=False,
        ),
    }


def search_required_scalar_boundary(
    system_spec: SystemSpec,
    base_vco: VCOParams,
    *,
    parameter: str,
    target_check: str,
    failing_bound: float,
    passing_bound: float,
    iterations: int = 24,
    model_overrides: Optional[Mapping[str, Any]] = None,
    require_other_checks: bool = True,
) -> Dict[str, Any]:
    """Search one local fail/pass boundary for a VCO behavioral parameter.

    A valid one-dimensional allocation requires an explicit bracket and a
    monotonic target check over that bracket.  The function deliberately does
    not infer which side is physically "better" from the parameter name.
    ``failing_bound`` and ``passing_bound`` encode the proved local direction.
    Other SystemSpec checks must already pass at the passing endpoint unless
    the caller explicitly disables that guard for a diagnostic experiment.
    """

    parameter = canonical_vco_parameter(parameter)
    if iterations < 1:
        raise ValueError("scalar boundary search requires at least one iteration")
    if float(failing_bound) == float(passing_bound):
        raise ValueError("scalar boundary search requires distinct bounds")

    failing_trial = abstract_vco_parameter_evaluation(
        system_spec,
        base_vco,
        parameter,
        failing_bound,
        model_overrides=model_overrides,
    )
    passing_trial = abstract_vco_parameter_evaluation(
        system_spec,
        base_vco,
        parameter,
        passing_bound,
        model_overrides=model_overrides,
    )
    if _target_check_passes(failing_trial["system_evaluation"], target_check):
        raise ValueError("declared failing scalar bound already passes target check")
    if not _target_check_passes(passing_trial["system_evaluation"], target_check):
        raise ValueError("declared passing scalar bound still fails target check")

    passing_checks = _aggregate_checks(passing_trial["system_evaluation"])
    if require_other_checks:
        ignored = {target_check}
        if target_check == "lock_time":
            ignored.add("locked")
        blocking = sorted(
            name for name, passed in passing_checks.items()
            if name not in ignored and not passed
        )
        if blocking:
            raise ValueError(
                f"{parameter}-only allocation infeasible; non-target checks fail "
                f"at passing bound: {', '.join(blocking)}"
            )

    history: List[Dict[str, Any]] = []
    for phase, trial in (("failing_bracket", failing_trial), ("passing_bracket", passing_trial)):
        evaluation = trial["system_evaluation"]
        history.append(
            {
                "phase": phase,
                "value": trial["value"],
                "target_passed": _target_check_passes(evaluation, target_check),
                "system_passed": bool(evaluation["passed"]),
                "metrics": _metric_snapshot(evaluation),
                "residuals": evaluation["residuals"],
            }
        )

    failing = float(failing_bound)
    passing = float(passing_bound)
    target_sequence = [False, True]
    for index in range(iterations):
        midpoint = 0.5 * (failing + passing)
        trial = abstract_vco_parameter_evaluation(
            system_spec,
            base_vco,
            parameter,
            midpoint,
            model_overrides=model_overrides,
        )
        evaluation = trial["system_evaluation"]
        target_passed = _target_check_passes(evaluation, target_check)
        target_sequence.append(target_passed)
        history.append(
            {
                "phase": "bisection",
                "iteration": index,
                "value": midpoint,
                "target_passed": target_passed,
                "system_passed": bool(evaluation["passed"]),
                "metrics": _metric_snapshot(evaluation),
                "residuals": evaluation["residuals"],
            }
        )
        if target_passed:
            passing = midpoint
        else:
            failing = midpoint

    return {
        "parameter": parameter,
        "target_check": target_check,
        "target_residual": SYSTEM_CHECK_RESIDUALS[target_check],
        "direction": (
            "increasing_parameter_moves_fail_to_pass"
            if passing_bound > failing_bound
            else "decreasing_parameter_moves_fail_to_pass"
        ),
        "search_knob": parameter,
        "search_knob_boundary": passing,
        "target_system_metric": target_check,
        "target_system_metric_at_boundary": history[-1]["metrics"].get(
            "integrated_jitter_s"
            if target_check == "integrated_jitter"
            else "lock_time_s"
            if target_check == "lock_time"
            else "output_frequency_hz"
            if target_check == "output_frequency"
            else "power_w"
        ) if history else None,
        "block_metric_at_boundary": None,
        "nearest_failing_search_knob": failing,
        "bracket_width": abs(passing - failing),
        "iterations": iterations,
        "history": history,
        "deterministic": True,
        "random_seed": None,
        "scope": "local_one_dimensional_bracket",
        "validity_domain": {
            "parameter_min": min(float(failing_bound), float(passing_bound)),
            "parameter_max": max(float(failing_bound), float(passing_bound)),
            "target_check": target_check,
        },
        "monotonic_target_assumption": True,
    }


def _sample_points(lower: float, upper: float, count: int) -> List[float]:
    if count < 2:
        return [lower]
    return [lower + (upper - lower) * index / (count - 1) for index in range(count)]


def measure_vco_behavior(
    system_spec: SystemSpec,
    vco: VCOParams,
    system_context: Mapping[str, Any],
    vctrl_points: int = 11,
) -> Dict[str, Any]:
    """Measure VCO behavior over the frozen VCOBlockContext."""

    context_vctrl_min = float(system_context["vctrl_min_v"])
    context_vctrl_max = float(system_context["vctrl_max_v"])
    if context_vctrl_min > context_vctrl_max:
        raise ValueError("invalid system Vctrl context")
    vctrl_values = _sample_points(context_vctrl_min, context_vctrl_max, vctrl_points)
    temperatures = [
        float(value)
        for value in system_context.get(
            "temperature_points_c", system_spec.temperature_points_c
        )
    ]
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

    worst_pn = max(item["phase_noise_1mhz_dbc_hz"] for item in observations)
    frequencies = [item["fosc_hz"] for item in observations]
    frequency_span = max(frequencies) - min(frequencies)
    result = {
        "measurement_method": "context_sweep_behavioral_vco",
        "provenance": {
            "source": "v1.pipeline.measure_vco_behavior",
            "model": "synthetic_behavioral_vco_v1",
        },
        "context": {
            "vctrl_min_v": context_vctrl_min,
            "vctrl_max_v": context_vctrl_max,
            "temperature_points_c": temperatures,
            "vdd_v": float(system_context.get("vdd_v", system_spec.vdd_v)),
            "source": system_context.get("source", "frozen VCOBlockContext"),
            "context_id": system_context.get("context_id", "VCOBlockContext.v1"),
        },
        "worst_case": {
            "worst_phase_noise_1mhz_dbc_hz": worst_pn,
            "worst_frequency_hz": max(frequencies),
            "frequency_min_hz": min(frequencies),
            "frequency_max_hz": max(frequencies),
            "tuning_range_hz": frequency_span,
            "kvco_min_hz_per_v": min(item["kvco_hz_per_v"] for item in observations),
            "kvco_max_hz_per_v": max(item["kvco_hz_per_v"] for item in observations),
            "power_min_w": min(item["power_w"] for item in observations),
            "worst_power_w": max(item["power_w"] for item in observations),
        },
        "observations": observations,
    }
    result["measured"] = {
        "phase_noise_1mhz_dbc_hz": [
            float(item["phase_noise_1mhz_dbc_hz"]) for item in observations
        ],
        "frequency_hz": [float(item["fosc_hz"]) for item in observations],
        "kvco_hz_per_v": [float(item["kvco_hz_per_v"]) for item in observations],
        "power_w": [float(item["power_w"]) for item in observations],
    }
    return result


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


def strip_raw_results(evaluation: Mapping[str, Any]) -> Dict[str, Any]:
    """Remove large histories before writing compact evaluation summaries."""

    return {key: value for key, value in evaluation.items() if key != "raw_results"}
