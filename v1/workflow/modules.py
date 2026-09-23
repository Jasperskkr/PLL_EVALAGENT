"""Reusable block-agnostic workflow modules."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..api.workflow import SpecClosureRequest
from ..graph.audit_workflow import audit_spec_closure_graph
from ..graph.compiler_workflow import build_spec_closure_graph


class StaticBlockDefinitionProvider:
    """Use the request's validated block definition unchanged."""

    module_id = "static_validated_block_definition_v1"

    def resolve(self, request: SpecClosureRequest) -> Mapping[str, Any]:
        return dict(request.block_definition)


class StaticCandidateProvider:
    """Use deterministic or Agent proposals carried by the request."""

    module_id = "static_candidate_proposal_provider_v1"

    def propose(
        self,
        request: SpecClosureRequest,
        allocation: Mapping[str, Any],
    ) -> Sequence[Mapping[str, Any]]:
        return [dict(item) for item in request.candidate_proposals]


class MinimumCostPassingSelector:
    """Choose the least-cost candidate whose deterministic verification passed."""

    module_id = "minimum_cost_passing_selector_v1"

    def select(
        self,
        request: SpecClosureRequest,
        candidate_evaluations: Sequence[Mapping[str, Any]],
    ) -> Mapping[str, Any]:
        feasible = [item for item in candidate_evaluations if item.get("passed")]
        if not feasible:
            return {
                "selected": False,
                "selected_candidate_id": None,
                "method": self.module_id,
                "eligible_candidate_ids": [],
            }
        ranked = sorted(
            feasible,
            key=lambda item: (
                float(item["proposal"].get("engineering_cost", 0.0)),
                str(item["candidate_id"]),
            ),
        )
        return {
            "selected": True,
            "selected_candidate_id": str(ranked[0]["candidate_id"]),
            "method": self.module_id,
            "eligible_candidate_ids": [str(item["candidate_id"]) for item in ranked],
            "ranking": [
                {
                    "candidate_id": str(item["candidate_id"]),
                    "engineering_cost": float(
                        item["proposal"].get("engineering_cost", 0.0)
                    ),
                }
                for item in ranked
            ],
        }


class GraphEvidenceFinalizer:
    """Compile and audit the canonical TypedGraph after numerical closure."""

    module_id = "typed_graph_v2_evidence_finalizer_v1"

    def finalize(
        self,
        request: SpecClosureRequest,
        block_definition: Mapping[str, Any],
        baseline: Mapping[str, Any],
        operating_context: Mapping[str, Any],
        allocation: Mapping[str, Any],
        candidate_evaluations: Sequence[Mapping[str, Any]],
        selection: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        graph = build_spec_closure_graph(
            workflow_id=request.workflow_id,
            block_definition=block_definition,
            baseline=baseline,
            operating_context=operating_context,
            allocation=allocation,
            candidate_evaluations=candidate_evaluations,
            selection=selection,
        )
        audit = audit_spec_closure_graph(
            graph,
            selected_candidate_id=selection.get("selected_candidate_id"),
        )
        return {
            "passed": bool(audit["passed"]),
            "graph": graph,
            "audit": audit,
        }


__all__ = [
    "GraphEvidenceFinalizer",
    "MinimumCostPassingSelector",
    "StaticBlockDefinitionProvider",
    "StaticCandidateProvider",
]
