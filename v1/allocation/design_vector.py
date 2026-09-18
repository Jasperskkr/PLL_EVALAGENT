"""Deterministic candidate/design-vector compilation.

The vector in this module contains simulator knobs, not requirements.  A
requirement is created only after the realized VCO has been measured by
BlockTB.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Any, Dict

from ..model.pll_behavioral import VCOParams


@dataclass(frozen=True)
class DesignVector:
    """Internal candidate knobs used to build one realized VCO instance."""

    values: Dict[str, Any] = field(default_factory=dict)
    source: str = "deterministic_allocator"
    version: str = "1.0"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "object_type": "vco_design_vector",
            "version": self.version,
            "source": self.source,
            "values": dict(self.values),
        }


def compile_design_vector_to_vco(
    base_vco: VCOParams, design_vector: DesignVector
) -> VCOParams:
    """Compile internal knobs into a realized VCO.

    The compiler accepts only actual :class:`VCOParams` fields.  Requirement
    names such as ``phase_noise_1mhz_max_dbc_hz`` are deliberately rejected.
    """

    values = dict(design_vector.values)
    valid_parameters = set(asdict(base_vco))
    unknown_parameters = set(values) - valid_parameters
    if unknown_parameters:
        raise ValueError(
            "design vector field(s) are not VCO model knobs: "
            f"{sorted(unknown_parameters)}"
        )
    return replace(base_vco, **values)


__all__ = ["DesignVector", "compile_design_vector_to_vco"]
