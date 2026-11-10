from __future__ import annotations

import math


class ContractError(ValueError):
    pass


def finite(value, name, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ContractError(f"{name}: finite numeric value required")
    if positive and value <= 0:
        raise ContractError(f"{name}: positive value required")
    return float(value)


METRICS = {
    "mean_phase_abs_deg": ("deg", "<=", "final_50_complete_reference_cycles"),
    "tail_max_abs_frequency_error_ppm": ("ppm", "<=", "final_50_complete_reference_cycles"),
    "lock_status": ("1", "==", "frozen_lock_protocol_v1"),
}


def metric_contract(item):
    if not isinstance(item, dict) or item.get("metric") not in METRICS:
        raise ContractError(f"UNSUPPORTED_METRIC: {item.get('metric') if isinstance(item, dict) else item}")
    unit, operator, measurement = METRICS[item["metric"]]
    if (item.get("unit"), item.get("operator"), item.get("measurement")) != (unit, operator, measurement):
        raise ContractError(f"{item['metric']}: unit/operator/measurement contract mismatch")
    if item["metric"] == "lock_status":
        if item.get("value") != "LOCKED":
            raise ContractError("lock_status requires LOCKED")
    else:
        finite(item.get("value"), item["metric"], positive=True)
        if item["metric"] == "mean_phase_abs_deg" and item["value"] >= 180:
            raise ContractError("local phase specification must be below 180 deg")
