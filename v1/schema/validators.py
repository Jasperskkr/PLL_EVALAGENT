"""Small deterministic validators for the additive V1 schema layer."""

from __future__ import annotations

from typing import Any, Mapping


def validate_envelope(value: Mapping[str, Any]) -> None:
    required = ("schema_version", "object_type", "object_id", "payload")
    missing = [name for name in required if name not in value]
    if missing:
        raise ValueError(f"envelope missing required field(s): {missing}")
    if not isinstance(value["payload"], Mapping):
        raise ValueError("envelope payload must be an object")


def validate_system_spec_payload(payload: Mapping[str, Any]) -> None:
    """Check the immutable requirements needed by the current SystemTB."""

    for section in ("pll", "limits", "operating_context", "jitter"):
        if section not in payload or not isinstance(payload[section], Mapping):
            raise ValueError(f"system spec missing object section: {section}")
    pll = payload["pll"]
    limits = payload["limits"]
    if float(pll["f_ref_hz"]) <= 0.0 or int(pll["divider_n"]) <= 0:
        raise ValueError("SystemSpec f_ref_hz and divider_n must be positive")
    if float(limits["integrated_jitter_max_s"]) <= 0.0:
        raise ValueError("integrated jitter limit must be positive")
    if float(limits["lock_time_max_s"]) <= 0.0:
        raise ValueError("lock-time limit must be positive")

