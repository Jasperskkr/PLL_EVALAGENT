"""Generic DesignVector evaluator using measured Block behavior."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Mapping

from ..model.pll_behavioral import VCOParams
from ..evaluation.system import evaluate_system
from ..specs import SystemSpec, VCORequirement
from ..api.verification import VerificationRequest
from ..verification.service import verify_block_assignment
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
        verification = verify_block_assignment(
            VerificationRequest(
                system_spec=system_spec,
                block_spec=requirement,
                realized_instance=vco,
                operating_context=block_context,
                block_id="VCO",
                request_id=f"design-vector:{design_vector.source}",
                keep_raw=keep_raw,
            )
        )
        output["block_evaluation"] = verification["block_tb"]
        output["verification_system_tb"] = verification["system_tb"]
        output["verification_report"] = verification
    return output
