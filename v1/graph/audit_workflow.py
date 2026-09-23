"""Deterministic closure audit for modular workflow graph artifacts."""

from __future__ import annotations

from typing import Any, Mapping

from .validators import validate_graph_v2_artifact


def audit_spec_closure_graph(
    graph: Mapping[str, Any], *, selected_candidate_id: str | None
) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    diagnostics: list[str] = []
    try:
        validate_graph_v2_artifact(graph)
        checks["schema_and_semantics"] = True
    except ValueError as exc:
        checks["schema_and_semantics"] = False
        diagnostics.append(str(exc))
    nodes = {str(node["id"]): node for node in graph.get("nodes", [])}
    edges = list(graph.get("edges", []))
    checks["allocation_evidence_present"] = "Evidence.allocation" in nodes
    checks["allocated_block_requirement_present"] = (
        "BlockRequirement.allocated" in nodes
    )
    candidates = {
        node_id
        for node_id, node in nodes.items()
        if node.get("type") == "candidate" and node_id != "Candidate.selected"
    }
    checks["candidate_proposals_present"] = bool(candidates)
    checks["every_candidate_realized"] = all(
        any(
            edge.get("source") == candidate
            and edge.get("type") == "realizes"
            for edge in edges
        )
        for candidate in candidates
    )
    if selected_candidate_id is None:
        checks["no_false_selected_candidate"] = "Candidate.selected" not in nodes
    else:
        selected_node = f"Candidate.{selected_candidate_id}"
        checks["selected_candidate_exists"] = selected_node in nodes
        checks["selected_marker_exists"] = "Candidate.selected" in nodes
        checks["final_verdict_exists"] = "SystemSpec.verdict" in nodes
        checks["selected_candidate_matches"] = any(
            edge.get("source") == selected_node
            and edge.get("target") == "Candidate.selected"
            and edge.get("type") == "selected_for"
            for edge in edges
        )
        checks["selected_blocktb_passed"] = bool(
            nodes.get(f"BlockTB.{selected_candidate_id}", {})
            .get("properties", {})
            .get("passed")
        )
        checks["selected_systemtb_passed"] = bool(
            nodes.get(f"SystemTB.{selected_candidate_id}", {})
            .get("properties", {})
            .get("passed")
        )
    return {
        "schema_version": "spec-closure-graph-audit-1.0",
        "passed": all(checks.values()),
        "checks": checks,
        "diagnostics": diagnostics,
    }


__all__ = ["audit_spec_closure_graph"]
