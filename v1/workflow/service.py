"""Block-agnostic orchestration for allocation, verification and evidence."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from ..api.workflow import SpecClosureReport, SpecClosureRequest, jsonable
from ..schema.workflow import (
    validate_block_definition,
    validate_candidate_proposal,
    validate_spec_closure_request,
)
from .protocols import (
    AllocationModule,
    AssignmentVerifier,
    BaselineEvaluator,
    BlockDefinitionProvider,
    CandidateProvider,
    CandidateRealizer,
    CandidateSelector,
    ContextBuilder,
    EvidenceFinalizer,
)


@dataclass(frozen=True)
class WorkflowModules:
    """Dependency-injected stages; the workflow core knows no VCO details."""

    block_definition_provider: BlockDefinitionProvider
    baseline_evaluator: BaselineEvaluator
    context_builder: ContextBuilder
    allocator: AllocationModule
    candidate_provider: CandidateProvider
    candidate_realizer: CandidateRealizer
    verifier: AssignmentVerifier
    selector: CandidateSelector
    evidence_finalizer: EvidenceFinalizer

    def provenance(self) -> dict[str, str]:
        return {
            field: str(getattr(getattr(self, field), "module_id", "unknown"))
            for field in self.__dataclass_fields__
        }


def run_spec_closure(
    request: SpecClosureRequest,
    modules: WorkflowModules,
) -> dict[str, Any]:
    """Run one deterministic, modular SystemSpec/BlockSpec closure.

    Agent-provided block/candidate objects remain proposals.  The core validates
    them before realization and accepts PASS only from the verifier and graph
    audit stages.
    """

    validate_spec_closure_request(request)
    block_definition = dict(modules.block_definition_provider.resolve(request))
    validate_block_definition(block_definition)
    active_request = replace(request, block_definition=block_definition)

    baseline = dict(modules.baseline_evaluator.evaluate(active_request))
    operating_context = dict(modules.context_builder.build(active_request, baseline))
    allocation = dict(
        modules.allocator.allocate(active_request, baseline, operating_context)
    )
    failure_reasons: list[str] = []
    if not allocation.get("allocated", False):
        failure_reasons.extend(
            str(reason) for reason in allocation.get("failure_reasons", [])
        )

    proposals = list(modules.candidate_provider.propose(active_request, allocation))
    block_id = str(block_definition["block_id"])
    design_names = {
        str(item["name"]) for item in block_definition["design_variables"]
    }
    if allocation.get("allocated", False) and not proposals:
        raise ValueError("allocated workflow requires candidate proposals")
    candidate_ids: set[str] = set()
    evaluations: list[dict[str, Any]] = []
    if allocation.get("allocated", False):
        for proposal_value in proposals:
            proposal = dict(proposal_value)
            validate_candidate_proposal(proposal, block_id=block_id)
            candidate_id = str(proposal["candidate_id"])
            if candidate_id in candidate_ids:
                raise ValueError(f"duplicate candidate_id: {candidate_id}")
            candidate_ids.add(candidate_id)
            unknown = set(str(name) for name in proposal["design_vector"]) - design_names
            if unknown:
                raise ValueError(
                    f"candidate {candidate_id} uses undeclared design variable(s): "
                    f"{sorted(unknown)}"
                )
            try:
                instance = modules.candidate_realizer.realize(active_request, proposal)
                verification = dict(
                    modules.verifier.verify(
                        active_request,
                        allocation,
                        proposal,
                        instance,
                        operating_context,
                    )
                )
                evaluations.append(
                    {
                        "candidate_id": str(proposal["candidate_id"]),
                        "proposal": proposal,
                        "realized_instance": jsonable(instance),
                        "verification": verification,
                        "passed": bool(verification.get("passed", False)),
                        "failure_reasons": list(
                            verification.get("failure_reasons", [])
                        ),
                    }
                )
            except (TypeError, ValueError) as exc:
                evaluations.append(
                    {
                        "candidate_id": str(proposal["candidate_id"]),
                        "proposal": proposal,
                        "realized_instance": None,
                        "verification": {},
                        "passed": False,
                        "failure_reasons": [
                            f"CandidateEvaluation:{type(exc).__name__}:{exc}"
                        ],
                    }
                )

    selection = dict(modules.selector.select(active_request, evaluations))
    if not selection.get("selected", False):
        failure_reasons.append("Selection:no_verified_candidate")
    evidence = dict(
        modules.evidence_finalizer.finalize(
            active_request,
            block_definition,
            baseline,
            operating_context,
            allocation,
            evaluations,
            selection,
        )
    )
    if not evidence.get("passed", False):
        failure_reasons.append("Evidence:graph_or_schema_audit_failed")

    selected_id = selection.get("selected_candidate_id")
    selected_record = next(
        (
            item
            for item in evaluations
            if item.get("candidate_id") == selected_id
        ),
        None,
    )
    passed = bool(
        allocation.get("allocated", False)
        and selected_record is not None
        and selected_record.get("passed", False)
        and evidence.get("passed", False)
    )
    report = SpecClosureReport(
        workflow_id=request.workflow_id,
        status="passed" if passed else "failed",
        block_definition=block_definition,
        baseline=baseline,
        operating_context=operating_context,
        allocation=allocation,
        candidate_evaluations=evaluations,
        selection=selection,
        evidence=evidence,
        failure_reasons=tuple(failure_reasons),
        provenance={
            "service": "v1.workflow.service.run_spec_closure",
            "modules": modules.provenance(),
            "agent_authority": "proposal_only",
            "verdict_authority": "deterministic_verifier_and_graph_audit",
        },
    )
    return report.to_dict()


__all__ = ["WorkflowModules", "run_spec_closure"]
