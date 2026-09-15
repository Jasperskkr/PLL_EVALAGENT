"""A forward-compatible VCO requirement vector.

The current PN boundary search is intentionally left untouched.  This module
provides the common representation that can later carry PN, Kvco, tuning-range
and power requirements together.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, Mapping, Optional

from ..model.pll_behavioral import VCOParams


@dataclass(frozen=True)
class SpecVector:
    values: Dict[str, Any] = field(default_factory=dict)
    source: str = "deterministic_allocator"
    version: str = "1.0"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "object_type": "vco_spec_vector",
            "version": self.version,
            "source": self.source,
            "values": dict(self.values),
        }


def compile_spec_vector_to_vco(
    base_vco: VCOParams, spec_vector: SpecVector
) -> VCOParams:
    """Compile currently supported allocation knobs into an abstract VCO.

    PN is the only formal allocation knob in V1.0.  Direct behavioral overrides
    are explicit and namespaced so future requirements cannot silently change
    the model.
    """

    values = dict(spec_vector.values)
    unknown_requirements = set(values) - {
        "phase_noise_1mhz_max_dbc_hz",
        "behavioral_overrides",
    }
    if unknown_requirements:
        raise ValueError(
            "spec vector field(s) require a future compiler: "
            f"{sorted(unknown_requirements)}"
        )
    overrides = dict(values.get("behavioral_overrides", {}))
    if "phase_noise_1mhz_max_dbc_hz" in values:
        overrides["pn_1mhz_dbc_hz"] = float(values["phase_noise_1mhz_max_dbc_hz"])
    valid_names = set(base_vco.__dataclass_fields__)
    unknown_overrides = set(overrides) - valid_names
    if unknown_overrides:
        raise ValueError(f"unknown VCO behavioral override(s): {sorted(unknown_overrides)}")
    return replace(base_vco, **overrides)

