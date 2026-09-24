"""Joint BlockTB/SystemTB evaluation for one V1.5 design point."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, Mapping

from ..model.pll_behavioral import VCOParams
from ..specs import SystemSpec
from ..api.verification import VerificationRequest
from ..verification.service import verify_block_assignment
from .design_space import DesignPointDefinition
from .design_vector import DesignVector, compile_design_vector_to_vco



def evaluate_design_point(
    case: Mapping[str, Any],
    system_spec: SystemSpec,
    base_vco: VCOParams,
    point: DesignPointDefinition,
) -> Dict[str, Any]:
    """Evaluate one point through one realized instance and both TBs."""

    case_id = str(case["case_id"])
    instance_id = f"Instance.{point.point_id}"
    design_vector = DesignVector(
        values=dict(point.values),
        source=f"{case_id}.design_space",
        version="1.5",
    )
    realized_vco = compile_design_vector_to_vco(base_vco, design_vector)

    block_context = dict(case["block_context"])
    verification = verify_block_assignment(
        VerificationRequest(
            system_spec=system_spec,
            block_spec={
                "kind": "constraint_set",
                "constraints": list(case["block_constraints"]),
            },
            realized_instance=realized_vco,
            operating_context=block_context,
            block_id="VCO",
            backend_id="synthetic_vco_v1_constraint_set",
            request_id=f"{case_id}:{point.point_id}",
            keep_raw=False,
        ),
    )
    block_tb = dict(verification["block_tb"])
    block_tb["realized_instance_id"] = instance_id
    system_tb = dict(verification["system_tb"])
    system_tb["realized_instance_id"] = instance_id
    context_coverage = verification["context_coverage"]
    behavior_vector = dict(block_tb["behavior_vector"])
    system_checks = dict(system_tb["checks"])

    block_failed = sorted(
        name for name, passed in block_tb["checks"].items() if not passed
    )
    system_failed = sorted(
        name for name, passed in system_checks.items() if not passed
    )
    context_failed = sorted(
        name
        for name, passed in context_coverage["checks"].items()
        if not passed
    )
    jointly_feasible = bool(
        block_tb["passed"]
        and system_tb["passed"]
        and context_coverage["passed"]
    )
    failure_reasons = (
        [f"BlockTB:{name}" for name in block_failed]
        + [f"SystemTB:{name}" for name in system_failed]
        + [f"Context:{name}" for name in context_failed]
    )

    return {
        "schema_version": "v1.5-sampled-design-point-1.0",
        "case_id": case_id,
        "point_id": point.point_id,
        "ordinal": point.ordinal,
        "design_vector": design_vector.to_dict(),
        "realized_instance": {
            "instance_id": instance_id,
            "model": "synthetic_behavioral_vco_v1",
            "parameters": asdict(realized_vco),
        },
        "behavior_vector": behavior_vector,
        "block_tb": block_tb,
        "system_tb": system_tb,
        "context_coverage": context_coverage,
        "constraint_residual_vector": {
            "block": dict(block_tb["residuals"]),
            "system": dict(system_tb["residuals"]),
        },
        "status": {
            "block_feasible": bool(block_tb["passed"]),
            "system_constraints_passed": bool(system_tb["passed"]),
            "context_covered": bool(context_coverage["passed"]),
            "jointly_feasible": jointly_feasible,
            "failure_reasons": failure_reasons,
        },
        "provenance": {
            "evaluator": "v1.allocation.multidim_evaluator.evaluate_design_point",
            "system_model": "averaged_integer_n_cppll_v1",
            "block_model": "synthetic_behavioral_vco_v1",
            "deterministic": True,
            "random_seed": None,
        },
    }


__all__ = ["evaluate_design_point"]
