from __future__ import annotations

from copy import deepcopy
import math
from .units import ContractError, METRICS, finite, metric_contract


def validate_request(raw):
    if not isinstance(raw, dict):
        raise ContractError("SystemSpec must be a mapping")
    p = deepcopy(raw)
    if p.get("schema_version") != "1.0" or p.get("topology") != "integer_n_cppll":
        raise ContractError("unsupported schema or topology")
    if not isinstance(p.get("task_id"), str) or not p["task_id"].strip():
        raise ContractError("task_id required")
    c = p.get("operating_context", {})
    fixed = {"fref_Hz": 1e7, "N": 8, "fout_target_Hz": 8e7,
             "VDD_V": 1.8, "temperature_C": 27., "pfd_reset_s": 2e-9}
    for name, expected in fixed.items():
        actual = finite(c.get(name), name)
        if not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=0):
            raise ContractError(f"{name}: outside frozen topology/context ({expected})")
    if c.get("drive_id") != "frozen_mos_buffer" or c.get("measurement_id") != "q_balance_C_after_proxy_load":
        raise ContractError("frozen drive and charge definition required")
    init = p.get("initialization", {})
    for name in ("Vctrl_V", "Vc2_V", "feedback_error_cycles"):
        finite(init.get(name), name)
    if init["Vctrl_V"] != 1.1774 or init["Vc2_V"] != 1.1774 or init["feedback_error_cycles"] != 0:
        raise ContractError("this release supports the approved common initial state only")
    m = p.get("measurement", {})
    expected_measurement = {"duration_s": 4e-5, "tail_cycles": 50, "lock_phase_deg": 5.,
                            "lock_frequency_ppm": 100., "lock_hold_cycles": 20}
    for name, expected in expected_measurement.items():
        if finite(m.get(name), name, positive=True) != expected:
            raise ContractError(f"{name}: frozen measurement protocol requires {expected}")
    items = p.get("system_spec", [])
    if not isinstance(items, list):
        raise ContractError("system_spec must be a list")
    for item in items:
        metric_contract(item)
    names = [i["metric"] for i in items]
    if len(names) != len(set(names)) or set(names) != set(METRICS):
        raise ContractError("all three supported metrics must occur exactly once")
    a = p.get("allocation", {})
    if a.get("mode") not in ("behavioral_target_search", "supported_library_match"):
        raise ContractError("unknown allocation mode")
    joint_grid_size = len(a.get("lf_Rz_Ohm", []))
    for name in ("cp_effective_current_target_A", "cp_balance_charge_target_C"):
        axis = a.get(name, {})
        lo, hi, step = (finite(axis.get(k), f"{name}.{k}") for k in ("min", "max", "step"))
        if step <= 0 or lo > hi or (name.endswith("current_target_A") and lo <= 0):
            raise ContractError(f"{name}: invalid grid")
        if (hi-lo)/step > 10000:
            raise ContractError("grid too large")
        joint_grid_size *= int((hi-lo)/step)+1
        if axis.get("evidence_level") != "DECLARED_PRIOR_ONLY":
            raise ContractError("behavioral search axes must be declared priors, never measured capability")
    if joint_grid_size > 100000:
        raise ContractError("joint declared grid exceeds 100000 points; narrow the explicit search domain")
    choices = a.get("lf_Rz_Ohm", [])
    if not isinstance(choices, list) or not choices or len(set(choices)) != len(choices):
        raise ContractError("nonempty unique LF choices required")
    for x in choices:
        finite(x, "Rz_Ohm", positive=True)
    for name in ("lf_C1_F", "lf_C2_F", "Cload_F", "Rload_Ohm"):
        finite(a.get(name), name, positive=True)
    if a.get("q0_definition") != "net_balance_charge_including_local_proxy_demand":
        raise ContractError("q0 must explicitly include the local proxy load demand")
    for name in ("current_tolerance_relative", "q0_tolerance_C"):
        finite(a.get(name), name, positive=True)
    if a["current_tolerance_relative"] >= 1:
        raise ContractError("current tolerance must be below one")
    if a.get("ranker") != "feasible_then_low_current_then_abs_charge_then_frequency_v1":
        raise ContractError("unsupported ranker")
    v = p.get("validation", {})
    if v.get("accept_model_predicted_as_qualified") is not False or v.get("allow_unknown") is not True:
        raise ContractError("evidence gaps may not be converted to qualified PASS")
    return p


def limits(request):
    return {x["metric"]: x["value"] for x in request["system_spec"]}
