"""Operating-context coverage checks shared by BlockTB and SystemTB."""

from __future__ import annotations

from typing import Any, Mapping


def evaluate_context_coverage(
    characterization_window: Mapping[str, Any],
    trajectory_envelope: Mapping[str, Any],
) -> dict[str, Any]:
    """Check that the observed trajectory stayed inside characterization."""

    tolerance = 1.0e-12
    checks = {
        "vctrl_min": float(trajectory_envelope["vctrl_min_v"])
        >= float(characterization_window["vctrl_min_v"]) - tolerance,
        "vctrl_max": float(trajectory_envelope["vctrl_max_v"])
        <= float(characterization_window["vctrl_max_v"]) + tolerance,
        "temperature": set(
            float(value) for value in trajectory_envelope["temperature_points_c"]
        ).issubset(
            set(
                float(value)
                for value in characterization_window["temperature_points_c"]
            )
        ),
        "vdd": abs(
            float(trajectory_envelope["vdd_v"])
            - float(characterization_window["vdd_v"])
        )
        <= tolerance,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "contract_context_id": characterization_window.get("context_id"),
        "characterization_window": dict(characterization_window),
        "trajectory_envelope": dict(trajectory_envelope),
        # Compatibility field for historical artifact consumers.
        "actual_context": dict(trajectory_envelope),
    }


__all__ = ["evaluate_context_coverage"]
