"""Deterministic V1 scalar allocation trials and bracketed boundary search."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, List, Mapping, Optional

from ..evaluation import system as system_evaluation
from ..model.instances import build_vco_instance, canonical_vco_parameter
from ..model.pll_behavioral import VCOParams
from ..specs import SystemSpec


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
    evaluation = system_evaluation.evaluate_system(
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
        "system_evaluation": system_evaluation.evaluate_system(
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
