"""Generic DesignVector evaluator using measured Block behavior."""

from __future__ import annotations

from dataclasses import asdict
from typing import Mapping

from ..model.pll_behavioral import VCOParams
from ..pipeline import evaluate_system, validate_vco_spec
from ..specs import SystemSpec, VCORequirement
from .design_vector import DesignVector, compile_design_vector_to_vco


def evaluate_design_vector(
    system_spec: SystemSpec,
    base_vco: VCOParams,
    design_vector: DesignVector,
    *,
    block_context: Mapping[str, Any] | None = None,
    requirement: VCORequirement | None = None,
    keep_raw: bool = False,
) -> dict[str, Any]:
    """Evaluate a candidate DesignVector through realized behavior.

    SystemTB remains available for top-level metrics.  When a frozen
    ``block_context`` and requirement are supplied, BlockTB measures the
    realized behavior before checking the requirement.
    """

    vco = compile_design_vector_to_vco(base_vco, design_vector)
    result = evaluate_system(system_spec, vco, keep_raw=keep_raw)
    output: dict[str, Any] = {
        "design_vector": design_vector.to_dict(),
        "realized_vco": asdict(vco),
        "system_evaluation": result,
    }
    if block_context is not None:
        if requirement is None:
            raise ValueError("BlockTB requirement is required with block_context")
        output["block_evaluation"] = validate_vco_spec(
            system_spec, requirement, vco, block_context
        )
    return output
