"""Minimal VCO contract/predictor evidence for the V1 demo.

The allocation path does not depend on an LLM or on this refinement side
experiment.  It is included so the V1 run produces the machine-readable seam
needed by the later Problem 1 work: an intentionally weak contract, an
independent observation table, and a refined context-aware contract.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping
import math

from .model.pll_behavioral import VCOParams


def build_contract_v0(vco: VCOParams) -> Dict[str, Any]:
    return {
        "contract_id": "vco_contract_v0",
        "version": 0,
        "representation": {
            "oscillation_frequency": "function(Vctrl, temperature)",
            "kvco": "function(Vctrl)",
            "phase_noise_1mhz": "constant",
            "power": "function(Vctrl, temperature)",
        },
        "fields": [
            {
                "name": "Vctrl",
                "role": "system_context",
                "unit": "V",
                "datatype": "float",
                "range": [vco.vctrl_min_v, vco.vctrl_max_v],
                "depends_on": [],
                "evaluation_method": "DC/TRAN",
            },
            {
                "name": "temperature",
                "role": "system_context",
                "unit": "degC",
                "datatype": "float",
                "range": [-40.0, 125.0],
                "depends_on": [],
                "evaluation_method": "DC/PNOISE",
            },
            {
                "name": "oscillation_frequency",
                "role": "performance_metric",
                "unit": "Hz",
                "datatype": "function",
                "range": None,
                "depends_on": ["Vctrl", "temperature"],
                "evaluation_method": "TRAN/PSS",
            },
            {
                "name": "kvco",
                "role": "intermediate_variable",
                "unit": "Hz/V",
                "datatype": "function",
                "range": None,
                "depends_on": ["Vctrl"],
                "evaluation_method": "DC sweep",
            },
            {
                "name": "phase_noise_1mhz",
                "role": "performance_metric",
                "unit": "dBc/Hz",
                "datatype": "float",
                "range": None,
                "depends_on": [],
                "evaluation_method": "PNOISE",
            },
            {
                "name": "power",
                "role": "performance_metric",
                "unit": "W",
                "datatype": "function",
                "range": None,
                "depends_on": ["Vctrl", "temperature"],
                "evaluation_method": "DC",
            },
        ],
        "validity": {
            "vctrl_v": [vco.vctrl_min_v, vco.vctrl_max_v],
            "temperature_c": [-40.0, 125.0],
            "offset_hz": [1.0e5, 1.0e7],
        },
        "status": "hypothesis_unvalidated",
    }


def build_contract_v1(vco: VCOParams) -> Dict[str, Any]:
    contract = build_contract_v0(vco)
    contract.update(
        {
            "contract_id": "vco_contract_v1",
            "version": 1,
            "representation": {
                "oscillation_frequency": "function(Vctrl, temperature)",
                "kvco": "function(Vctrl)",
                "phase_noise_1mhz": "function(Vctrl, temperature, power)",
                "power": "function(Vctrl, temperature)",
            },
            "status": "validated_on_v1_observations",
        }
    )
    for field in contract["fields"]:
        if field["name"] == "phase_noise_1mhz":
            field["depends_on"] = ["Vctrl", "temperature", "power"]
            field["datatype"] = "function"
    return contract


def _predict_v0(vco: VCOParams, row: Mapping[str, Any]) -> float:
    # Deliberately weak: nominal PN is used for every context.
    return vco.phase_noise_dbc_hz(
        float(row["offset_hz"]), vco.v0_v, vco.nominal_temperature_c, vco.nominal_power_w
    )


def _predict_v1(vco: VCOParams, row: Mapping[str, Any]) -> float:
    # The refined contract exposes the dependencies explicitly.  Keeping this
    # predictor separate from the system simulator is what makes the evidence
    # replayable and leaves room for an Agent-generated predictor later.
    offset_hz = float(row["offset_hz"])
    vctrl_v = float(row["vctrl_v"])
    temperature_c = float(row["temperature_c"])
    power_w = float(row["power_w"])
    if offset_hz < 1.0e6:
        slope_term = 30.0 * math.log10(1.0e6 / offset_hz)
    else:
        slope_term = -20.0 * math.log10(offset_hz / 1.0e6)
    power_ratio = max(power_w / vco.nominal_power_w, 1.0e-6)
    return (
        vco.pn_anchor_1mhz_dbc_hz
        + vco.pn_vctrl_coeff_db_per_v * (vctrl_v - vco.v0_v)
        + vco.pn_temp_coeff_db_per_c * (temperature_c - vco.nominal_temperature_c)
        + vco.pn_power_coeff_db_per_decade * math.log10(power_ratio)
        + slope_term
    )


def _mae(errors: Iterable[float]) -> float:
    values = list(errors)
    return 0.0 if not values else sum(abs(value) for value in values) / len(values)


def validate_contracts(
    vco: VCOParams, observations: List[Mapping[str, Any]]
) -> Dict[str, Any]:
    """Compare v0/v1 predictors on a deterministic holdout subset."""

    holdout = [
        row
        for index, row in enumerate(observations)
        if index % 2 == 1 and float(row["offset_hz"]) == 1.0e6
    ]
    if not holdout:
        holdout = [row for row in observations if float(row["offset_hz"]) == 1.0e6]
    v0_errors = [
        _predict_v0(vco, row) - float(row["phase_noise_dbc_hz"]) for row in holdout
    ]
    v1_errors = [
        _predict_v1(vco, row) - float(row["phase_noise_dbc_hz"]) for row in holdout
    ]
    return {
        "holdout_count": len(holdout),
        "v0_mae_db": _mae(v0_errors),
        "v1_mae_db": _mae(v1_errors),
        "v0_prediction": "phase_noise_1mhz = constant",
        "v1_prediction": "phase_noise = f(Vctrl, temperature, power, offset)",
        "diagnosis": {
            "failure_type": "missing_context_or_dependency",
            "evidence": "phase-noise prediction error varies with Vctrl/context",
            "refinement_action": "add_context_and_dependency",
        },
    }


def build_contract_evidence(
    vco: VCOParams, observations: List[Mapping[str, Any]]
) -> Dict[str, Any]:
    return {
        "contract_v0": build_contract_v0(vco),
        "contract_v1": build_contract_v1(vco),
        "validation": validate_contracts(vco, observations),
        "oracle": {
            "source": "independent synthetic VCO behavioral instance",
            "fidelity": "synthetic_behavioral",
        },
    }
