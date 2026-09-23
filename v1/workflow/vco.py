"""VCO adapters for the block-agnostic spec-closure workflow."""

from __future__ import annotations

from typing import Any, Mapping

from ..allocation.service import allocate_system_spec
from ..api.allocation import SpecAllocationRequest
from ..api.verification import VerificationRequest
from ..api.workflow import SpecClosureRequest
from ..backends.synthetic import SyntheticVCOBackend
from ..model.pll_behavioral import VCOParams
from ..pipeline import build_vco_instance, evaluate_system
from ..specs import VCORequirement
from ..verification.service import verify_block_assignment


class VCOBaselineEvaluator:
    module_id = "synthetic_vco_baseline_system_tb_v1"

    def evaluate(self, request: SpecClosureRequest) -> Mapping[str, Any]:
        if not isinstance(request.base_instance, VCOParams):
            raise TypeError("VCO workflow expects a VCOParams base instance")
        return evaluate_system(
            request.system_spec,
            request.base_instance,
            keep_raw=False,
        )


class VCOContextBuilder:
    module_id = "initial_system_tb_vco_context_builder_v1"

    def build(
        self,
        request: SpecClosureRequest,
        baseline: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if request.declared_operating_context:
            return dict(request.declared_operating_context)
        actual = baseline["context"]
        guard_v = float(request.policy.get("context_guard_v", 0.01))
        system_spec = request.system_spec
        return {
            "vctrl_min_v": max(
                system_spec.vctrl_min_v,
                float(actual["vctrl_min_v"]) - guard_v,
            ),
            "vctrl_max_v": min(
                system_spec.vctrl_max_v,
                float(actual["vctrl_max_v"]) + guard_v,
            ),
            "temperature_points_c": list(system_spec.temperature_points_c),
            "vdd_v": system_spec.vdd_v,
            "context_id": f"{request.block_definition['block_id']}BlockContext.workflow",
            "source": "initial_system_tb_plus_declared_guard",
            "guard_v": guard_v,
        }


class VCOAllocationModule:
    module_id = "synthetic_vco_spec_allocator_v1"

    def allocate(
        self,
        request: SpecClosureRequest,
        baseline: Mapping[str, Any],
        operating_context: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        problem = dict(request.allocation_problem)
        return allocate_system_spec(
            SpecAllocationRequest(
                system_spec=request.system_spec,
                base_instance=request.base_instance,
                operating_context=operating_context,
                allocation_problem=problem,
                block_id=str(request.block_definition["block_id"]),
                request_id=f"{request.workflow_id}:allocation",
            )
        )


class VCOCandidateRealizer:
    module_id = "synthetic_vco_candidate_realizer_v1"

    def realize(
        self,
        request: SpecClosureRequest,
        proposal: Mapping[str, Any],
    ) -> VCOParams:
        if not isinstance(request.base_instance, VCOParams):
            raise TypeError("VCO workflow expects a VCOParams base instance")
        return build_vco_instance(
            request.base_instance,
            dict(proposal["design_vector"]),
        )


class VCOAssignmentVerifier:
    module_id = "synthetic_vco_assignment_verifier_v1"

    def verify(
        self,
        request: SpecClosureRequest,
        allocation: Mapping[str, Any],
        proposal: Mapping[str, Any],
        realized_instance: Any,
        operating_context: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        spec_kind = str(request.policy.get("verification_block_spec", "allocated"))
        spec_field = (
            "recommended_block_spec"
            if spec_kind == "recommended"
            else "allocated_block_spec"
        )
        block_spec = allocation.get(spec_field)
        if not isinstance(block_spec, Mapping):
            raise ValueError(f"allocation did not produce {spec_field}")
        return verify_block_assignment(
            VerificationRequest(
                system_spec=request.system_spec,
                block_spec=VCORequirement.from_dict(block_spec),
                realized_instance=realized_instance,
                operating_context=operating_context,
                block_id=str(request.block_definition["block_id"]),
                request_id=(
                    f"{request.workflow_id}:verification:{proposal['candidate_id']}"
                ),
                keep_raw=bool(request.policy.get("keep_raw", False)),
            ),
            backend=SyntheticVCOBackend(),
        )


__all__ = [
    "VCOAllocationModule",
    "VCOAssignmentVerifier",
    "VCOBaselineEvaluator",
    "VCOCandidateRealizer",
    "VCOContextBuilder",
]
