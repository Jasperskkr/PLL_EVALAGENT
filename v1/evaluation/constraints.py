"""Measured behavior-vector projection for declarative V1.5 constraints."""

from __future__ import annotations

from typing import Any, Dict, Mapping


BEHAVIOR_VECTOR_FIELDS = (
    "worst_phase_noise_1mhz_dbc_hz",
    "kvco_min_hz_per_v",
    "kvco_max_hz_per_v",
    "frequency_min_hz",
    "frequency_max_hz",
    "worst_power_w",
)


def behavior_vector(measurement: Mapping[str, Any]) -> Dict[str, float]:
    """Project one measurement onto the declarative constraint vocabulary."""

    worst = measurement["worst_case"]
    return {name: float(worst[name]) for name in BEHAVIOR_VECTOR_FIELDS}


__all__ = [
    "BEHAVIOR_VECTOR_FIELDS",
    "behavior_vector",
]
