"""Backward-compatible envelopes around existing V1 objects.

The first V1 implementation writes flat JSON files.  These envelopes add
identity, version and provenance without changing the old payload shape or
the numerical pipeline that produces it.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional


def make_envelope(
    object_type: str,
    object_id: str,
    payload: Mapping[str, Any],
    *,
    run_id: Optional[str] = None,
    provenance: Optional[Mapping[str, Any]] = None,
    schema_version: str = "1.1",
    created_at_utc: Optional[str] = None,
) -> Dict[str, Any]:
    """Return a canonical envelope while leaving the supplied payload intact."""

    envelope = {
        "schema_version": schema_version,
        "object_type": object_type,
        "object_id": object_id,
        "run_id": run_id,
        "provenance": dict(provenance or {}),
        "payload": dict(payload),
    }
    # Timestamps are optional because deterministic replay should not depend
    # on wall-clock time.  A production runner may supply one explicitly.
    if created_at_utc is not None:
        envelope["created_at_utc"] = created_at_utc
    return envelope
