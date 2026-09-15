"""Generic evaluator wrapper that reuses the existing deterministic pipeline."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from ..model.pll_behavioral import VCOParams
from ..pipeline import evaluate_system
from ..specs import SystemSpec
from .spec_vector import SpecVector, compile_spec_vector_to_vco


def evaluate_spec_vector(
    system_spec: SystemSpec,
    base_vco: VCOParams,
    spec_vector: SpecVector,
    *,
    keep_raw: bool = False,
) -> dict[str, Any]:
    """Evaluate an abstract VCO requirement vector using SystemTB.

    This is deliberately an adapter: the current V1 PN search remains the
    canonical implementation, while future multi-parameter search can call a
    stable vector evaluator.
    """

    vco = compile_spec_vector_to_vco(base_vco, spec_vector)
    result = evaluate_system(system_spec, vco, keep_raw=keep_raw)
    return {
        "spec_vector": spec_vector.to_dict(),
        "system_evaluation": result,
    }

