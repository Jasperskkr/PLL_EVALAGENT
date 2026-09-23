"""Operating-context coverage checks shared by BlockTB and SystemTB."""

from __future__ import annotations

from typing import Any, Mapping


def evaluate_context_coverage(
    contract: Mapping[str, Any], actual: Mapping[str, Any]
) -> dict[str, Any]:
    """Check that SystemTB stayed inside the frozen BlockTB context."""

    tolerance = 1.0e-12
    checks = {
        "vctrl_min": float(actual["vctrl_min_v"])
        >= float(contract["vctrl_min_v"]) - tolerance,
        "vctrl_max": float(actual["vctrl_max_v"])
        <= float(contract["vctrl_max_v"]) + tolerance,
        "temperature": set(float(value) for value in actual["temperature_points_c"])
        .issubset(set(float(value) for value in contract["temperature_points_c"])),
        "vdd": abs(float(actual["vdd_v"]) - float(contract["vdd_v"]))
        <= tolerance,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "contract_context_id": contract.get("context_id"),
        "actual_context": dict(actual),
    }


__all__ = ["evaluate_context_coverage"]
