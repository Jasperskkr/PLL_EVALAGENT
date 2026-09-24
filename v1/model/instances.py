"""Deterministic VCO instance construction and legacy parameter normalization."""

from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any, Dict, Mapping

from .pll_behavioral import VCOParams
from ..specs import CandidateDefinition


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
