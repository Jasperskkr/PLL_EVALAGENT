"""Compile one modular spec-closure run into a TypedGraph v2 artifact."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .model import TypedGraph
from .validators import validate_graph_v2_artifact


def _metric_node(block_id: str, metric_name: str) -> str:
    return f"{block_id}.behavior.{metric_name}"


def _system_metric_node(metric_name: str) -> str:
    return f"SystemMetric.{metric_name}"


def build_spec_closure_graph(
    *,
    workflow_id: str,
    block_definition: Mapping[str, Any],
    baseline: Mapping[str, Any],
    operating_context: Mapping[str, Any],
    allocation: Mapping[str, Any],
    candidate_evaluations: Sequence[Mapping[str, Any]],
    selection: Mapping[str, Any],
) -> dict[str, Any]:
    """Create a block-agnostic trace from requirements to verified candidate."""

    block_id = str(block_definition["block_id"])
    requirement_mapping = dict(block_definition["requirement_mapping"])
    context_id = str(
        operating_context.get("context_id", f"{block_id}BlockContext.workflow")
    )
    selected_id = selection.get("selected_candidate_id")
    graph = TypedGraph(
        graph_id=f"{workflow_id}:spec-closure",
        graph_version="2.0",
        metadata={
            "artifact_profile": "spec_closure_workflow",
            "workflow_id": workflow_id,
            "block_id": block_id,
            "block_context_id": context_id,
            "semantic_role_model": [
                "architecture",
                "behavior",
                "influence",
                "evidence",
            ],
            "allocation_outcome": (
                "allocated" if allocation.get("allocated") else "rejected"
            ),
            "workflow_status": "passed" if selected_id is not None else "failed",
            "candidate_count": len(candidate_evaluations),
            "agent_policy": "propose_only; deterministic_tools_validate",
            "deterministic": True,
        },
    )

    def node(
        node_id: str,
        node_type: str,
        semantic_role: str | None,
        properties: Mapping[str, Any],
        *,
        status: str | None = None,
    ) -> None:
        graph.add_node(
            node_id,
            node_type,
            properties,
            semantic_role=semantic_role,
            owner=block_id if node_id.startswith(block_id) else None,
            status=status,
        )

    def edge(
        source: str,
        target: str,
        edge_type: str,
        properties: Mapping[str, Any],
        *,
        status: str | None = None,
    ) -> None:
        graph.add_edge(source, target, edge_type, properties, status=status)

    node(
        block_id,
        "architecture_block",
        "architecture",
        {
            "block_type": block_definition["block_type"],
            "definition_schema": block_definition["schema_version"],
        },
    )
    behavior_by_name = {
        str(item["name"]): item for item in block_definition["behavior_metrics"]
    }
    for metric_name, metric in behavior_by_name.items():
        node(
            _metric_node(block_id, metric_name),
            "behavioral_output",
            "behavior",
            {
                "metric_name": metric_name,
                "unit": metric["unit"],
            },
        )
        edge(
            block_id,
            _metric_node(block_id, metric_name),
            "contains",
            {"metric_name": metric_name},
        )

    system_requirement_ids: set[str] = set()
    for influence in block_definition["system_influences"]:
        source_metric = str(influence["source_metric"])
        target_metric = str(influence["target_metric"])
        requirement_id = str(influence["system_requirement_id"])
        system_requirement_ids.add(requirement_id)
        metric_id = _system_metric_node(target_metric)
        node(
            metric_id,
            "system_metric",
            "influence",
            {"metric_name": target_metric, "unit": influence.get("unit")},
        )
        node(
            requirement_id,
            "system_requirement",
            None,
            {
                "source": "immutable SystemSpec",
                "metric": target_metric,
                "limit": influence.get("limit"),
                "check": influence["system_check"],
            },
        )
        edge(
            _metric_node(block_id, source_metric),
            metric_id,
            "system_influence",
            {
                "source_behavior_metric": source_metric,
                "target_system_metric": target_metric,
                "mechanism": influence["mechanism"],
                "evidence_refs": ["Evidence.allocation"],
                "validity_domain": context_id,
            },
        )
        edge(
            requirement_id,
            metric_id,
            "constrains",
            {
                "check": influence["system_check"],
                "limit": influence.get("limit"),
            },
        )

    node(
        "Workflow.design_space",
        "design_space",
        None,
        {
            "source": "validated candidate proposals",
            "dimensions": [
                item["name"] for item in block_definition["design_variables"]
            ],
        },
    )
    node(
        "BlockRequirement.allocated",
        "block_requirement",
        None,
        {
            "source": "allocation service",
            "metric": requirement_mapping["metric"],
            "measured_metric": requirement_mapping["measured_metric"],
            "value": (allocation.get("allocated_block_spec") or {}).get(
                requirement_mapping["metric"]
            ),
            "search_knob": requirement_mapping.get("search_knob"),
            "search_knob_boundary": allocation.get("evidence", {})
            .get("boundary", {})
            .get("search_knob_boundary"),
        },
        status="validated" if allocation.get("allocated") else "rejected",
    )
    node(
        "Evidence.allocation",
        "evidence",
        "evidence",
        {
            "passed": bool(allocation.get("allocated")),
            "measurement_method": "allocation_module_plus_frozen_context_measurement",
            "allocation": dict(allocation),
            "baseline": dict(baseline),
            "source": "v1.workflow.service",
        },
        status="validated" if allocation.get("allocated") else "rejected",
    )
    allocation_requirement = str(requirement_mapping["system_requirement_id"])
    if allocation.get("allocated"):
        edge(
            allocation_requirement,
            "BlockRequirement.allocated",
            "allocates",
            {
                "method": allocation.get("provenance", {}).get("backend"),
                "evidence_id": "Evidence.allocation",
            },
            status="validated",
        )
        edge(
            "BlockRequirement.allocated",
            "Evidence.allocation",
            "supported_by",
            {"passed": True},
            status="validated",
        )

    node(
        "Context.Block.contract",
        "context",
        "architecture",
        dict(operating_context),
        status="validated",
    )

    for record in candidate_evaluations:
        candidate_id = str(record["candidate_id"])
        proposal = dict(record["proposal"])
        verification = dict(record.get("verification", {}))
        passed = bool(record.get("passed", False))
        status = "validated" if passed else "rejected"
        candidate_node = f"Candidate.{candidate_id}"
        instance_node = f"Instance.{candidate_id}"
        block_tb_node = f"BlockTB.{candidate_id}"
        system_tb_node = f"SystemTB.{candidate_id}"
        actual_context_node = f"Context.SystemTB.{candidate_id}"
        block_tb = dict(verification.get("block_tb", {}))
        system_tb = dict(verification.get("system_tb", {}))
        coverage = dict(verification.get("context_coverage", {}))

        node(
            candidate_node,
            "candidate",
            None,
            {
                "source": proposal.get("source"),
                "proposal_id": proposal.get("proposal_id"),
                "design_vector": proposal.get("design_vector", {}),
                "rationale": proposal.get("rationale"),
            },
            status=status,
        )
        node(
            instance_node,
            "realized_instance",
            None,
            {
                "source": "candidate realizer",
                "parameters": record.get("realized_instance"),
                "model_ref": verification.get("provenance", {}).get("backend"),
            },
            status=status,
        )
        node(
            block_tb_node,
            "evaluation",
            "evidence",
            {
                "passed": bool(block_tb.get("passed", False)),
                "checks": block_tb.get("checks", {}),
                "context": block_tb.get("context", operating_context),
                "worst_case": block_tb.get("worst_case", {}),
                "measurement_method": block_tb.get(
                    "measurement_method", "backend.measure_block"
                ),
            },
            status=("validated" if block_tb.get("passed") else "rejected"),
        )
        node(
            system_tb_node,
            "evaluation",
            "evidence",
            {
                "passed": bool(system_tb.get("passed", False)),
                "checks": system_tb.get("checks", {}),
                "metrics": system_tb.get("metrics", {}),
                "residuals": system_tb.get("residuals", {}),
                "measurement_method": system_tb.get(
                    "measurement_method", "backend.evaluate_system"
                ),
            },
            status=("validated" if system_tb.get("passed") else "rejected"),
        )
        node(
            actual_context_node,
            "context",
            "evidence",
            {
                **dict(system_tb.get("context", {})),
                "coverage": coverage,
                "measurement_method": "system_tb_context_capture",
            },
            status=("validated" if coverage.get("passed") else "rejected"),
        )
        edge(candidate_node, "Workflow.design_space", "candidate_of", {}, status="tested")
        edge(candidate_node, instance_node, "realizes", {}, status=status)
        edge(instance_node, block_tb_node, "evaluates", {"passed": block_tb.get("passed")}, status=("validated" if block_tb.get("passed") else "rejected"))
        edge(instance_node, system_tb_node, "evaluates", {"passed": system_tb.get("passed")}, status=("validated" if system_tb.get("passed") else "rejected"))
        edge(block_tb_node, "BlockRequirement.allocated", "verifies_requirement", {"passed": block_tb.get("passed")}, status=("validated" if block_tb.get("passed") else "rejected"))
        edge(block_tb_node, "Context.Block.contract", "uses_context", {"source": "frozen_contract"})
        edge(system_tb_node, actual_context_node, "uses_context", {"source": "actual_system_tb"})
        edge("Context.Block.contract", actual_context_node, "covers", {"passed": coverage.get("passed"), "checks": coverage.get("checks", {})}, status=("validated" if coverage.get("passed") else "rejected"))
        for influence in block_definition["system_influences"]:
            check = str(influence["system_check"])
            requirement_id = str(influence["system_requirement_id"])
            check_passed = bool(system_tb.get("checks", {}).get(check, False))
            edge(system_tb_node, requirement_id, "verifies_requirement", {"passed": check_passed, "check": check}, status=("validated" if check_passed else "rejected"))

    if selected_id is not None:
        selected_node = f"Candidate.{selected_id}"
        selected_system_tb = f"SystemTB.{selected_id}"
        node(
            "Candidate.selected",
            "candidate",
            None,
            {
                "source": "deterministic selector",
                "candidate_id": selected_id,
                "selection_policy": selection.get("method"),
            },
            status="validated",
        )
        node(
            "SystemSpec.verdict",
            "evaluation",
            "evidence",
            {
                "passed": True,
                "selected_candidate_id": selected_id,
                "measurement_method": "selected_candidate_verification_projection",
            },
            status="validated",
        )
        edge(selected_node, "Candidate.selected", "selected_for", {}, status="validated")
        edge(selected_system_tb, "SystemSpec.verdict", "yields_verdict", {"passed": True}, status="validated")
        for requirement_id in sorted(system_requirement_ids):
            edge("SystemSpec.verdict", requirement_id, "verifies_requirement", {"passed": True}, status="validated")

    graph.validate()
    artifact = graph.to_dict()
    validate_graph_v2_artifact(artifact)
    return artifact


__all__ = ["build_spec_closure_graph"]
