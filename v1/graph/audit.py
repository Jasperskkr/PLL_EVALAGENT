"""Goal-driven semantic audit for Agent-ready allocation graphs."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Sequence

from .queries import trace_paths
from .validators import validate_graph_v2_artifact


def _node_map(graph: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    return {str(node["id"]): node for node in graph.get("nodes", [])}


def _edges(graph: Mapping[str, Any], edge_type: str | None = None) -> list[Mapping[str, Any]]:
    return [edge for edge in graph.get("edges", []) if edge_type is None or edge.get("type") == edge_type]


def _close(a: Any, b: Any, tolerance: float = 1e-15) -> bool:
    try:
        return abs(float(a) - float(b)) <= tolerance * max(1.0, abs(float(a)), abs(float(b)))
    except (TypeError, ValueError):
        return a == b


def _candidate_id(node_id: str) -> str:
    return node_id.split(".", 1)[1]


def audit_allocation_graph(
    graph: Mapping[str, Any],
    *,
    expected: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Audit closure, status, evidence and optional artifact consistency.

    Generic checks depend only on graph roles. VCO-specific numeric semantics
    are isolated in the optional expected payload assembled by the VCO runner.
    """

    checks: Dict[str, bool] = {}
    diagnostics: list[str] = []
    try:
        validate_graph_v2_artifact(graph)
        checks["schema_and_semantics"] = True
    except ValueError as exc:
        checks["schema_and_semantics"] = False
        diagnostics.append(str(exc))

    nodes = _node_map(graph)
    outcome = graph.get("metadata", {}).get("allocation_outcome")
    checks["outcome_declared"] = outcome in {"allocated", "rejected"}
    if outcome == "rejected":
        checks["rejection_evidence_present"] = "Evidence.PN.rejection" in nodes
        checks["no_false_allocation_claim"] = not _edges(graph, "allocates")
        checks["rejected_requirements_have_no_value"] = all(
            nodes.get(node_id, {}).get("properties", {}).get("value") is None
            and nodes.get(node_id, {}).get("status") == "rejected"
            for node_id in ("VCORequirement.required", "VCORequirement.recommended")
        )
        blocking = set(nodes.get("Evidence.PN.rejection", {}).get("properties", {}).get("blocking_checks", []))
        requirement_for_check = {
            "lock_time": "SystemSpec.lock_time",
            "locked": "SystemSpec.lock_time",
            "power": "SystemSpec.power",
            "output_frequency": "SystemSpec.output_frequency",
        }
        supported = {
            (str(edge.get("source")), str(edge.get("properties", {}).get("blocking_check")))
            for edge in _edges(graph, "supported_by")
            if edge.get("target") == "Evidence.PN.rejection"
        }
        checks["blocking_checks_trace_to_systemspec"] = all(
            (requirement_for_check[check], check) in supported
            for check in blocking
            if check in requirement_for_check
        )
        checks["rejected_graph_keeps_initial_systemtb"] = "Evidence.SystemTB.initial" in nodes
        checks["rejected_graph_keeps_sensitivity"] = "Evidence.sensitivity" in nodes
        checks["no_candidate_claim_in_rejected_graph"] = not any(
            node.get("type") in {"candidate", "realized_instance"} for node in nodes.values()
        )
        if expected is not None:
            checks["blocking_checks_match_artifact"] = blocking == set(expected.get("blocking_checks", []))
        return {"passed": all(checks.values()), "outcome": outcome, "checks": checks, "diagnostics": diagnostics}

    selected_markers = [edge for edge in _edges(graph, "selected_for") if edge.get("target") == "Candidate.selected"]
    checks["exactly_one_selected_candidate"] = len(selected_markers) == 1
    selected_id = _candidate_id(str(selected_markers[0]["source"])) if selected_markers else None
    instance_id = None if selected_id is None else f"Instance.{selected_id}"
    block_id = None if selected_id is None else f"BlockTB.{selected_id}"
    system_id = None if selected_id is None else f"SystemTB.{selected_id}"
    required_nodes = ["SystemSpec.integrated_jitter", "VCORequirement.required", "VCORequirement.recommended", "VCO.design_space", "VCO.capability_region", "Context.VCO.contract", "Evidence.boundary_search", "Evidence.SystemTB.final", "SystemSpec.verdict"]
    if selected_id is not None:
        required_nodes.extend([f"Candidate.{selected_id}", instance_id, block_id, system_id, "Candidate.selected"])
    checks["required_closure_nodes_exist"] = all(node_id in nodes for node_id in required_nodes)

    if selected_id is not None:
        try:
            checks["requirement_to_candidate_path"] = bool(trace_paths(graph, "SystemSpec.integrated_jitter", f"Candidate.{selected_id}", max_depth=8))
        except (KeyError, ValueError) as exc:
            checks["requirement_to_candidate_path"] = False
            diagnostics.append(f"path query failed: {exc}")
        checks["candidate_realizes_instance"] = any(edge.get("source") == f"Candidate.{selected_id}" and edge.get("target") == instance_id and edge.get("type") == "realizes" for edge in _edges(graph))
        checks["instance_to_blocktb"] = any(edge.get("source") == instance_id and edge.get("target") == block_id and edge.get("type") == "evaluates" for edge in _edges(graph))
        checks["instance_to_systemtb"] = any(edge.get("source") == instance_id and edge.get("target") == system_id and edge.get("type") == "evaluates" for edge in _edges(graph))
        checks["selected_instance_to_final_systemtb"] = any(edge.get("source") == instance_id and edge.get("target") == "Evidence.SystemTB.final" and edge.get("type") == "evaluates" for edge in _edges(graph))
        checks["blocktb_verifies_requirement"] = any(edge.get("source") == block_id and edge.get("target") == "VCORequirement.recommended" and edge.get("type") == "verifies_requirement" and edge.get("properties", {}).get("passed") is True for edge in _edges(graph))
        checks["final_systemtb_yields_verdict"] = any(edge.get("source") == "Evidence.SystemTB.final" and edge.get("target") == "SystemSpec.verdict" and edge.get("type") == "yields_verdict" and edge.get("properties", {}).get("passed") is True for edge in _edges(graph))
        verified_requirements = {
            str(edge.get("target"))
            for edge in _edges(graph, "verifies_requirement")
            if edge.get("source") == "SystemSpec.verdict"
            and edge.get("properties", {}).get("passed") is True
        }
        checks["final_verdict_verifies_all_requirements"] = verified_requirements == {
            "SystemSpec.integrated_jitter",
            "SystemSpec.lock_time",
            "SystemSpec.output_frequency",
            "SystemSpec.power",
        }
        checks["selected_blocktb_passed"] = nodes.get(block_id, {}).get("properties", {}).get("passed") is True
        checks["selected_systemtb_passed"] = nodes.get(system_id, {}).get("properties", {}).get("passed") is True
        checks["selected_candidate_in_capability_region"] = any(edge.get("source") == f"Candidate.{selected_id}" and edge.get("target") == "VCO.capability_region" and edge.get("type") == "candidate_of" and edge.get("status") == "validated" for edge in _edges(graph))

    capability_members = {str(edge["source"]) for edge in _edges(graph, "candidate_of") if edge.get("target") == "VCO.capability_region"}
    checks["capability_region_contains_only_blocktb_pass"] = all(nodes.get(f"BlockTB.{_candidate_id(candidate)}", {}).get("properties", {}).get("passed") is True for candidate in capability_members)
    candidates = {node_id for node_id, node in nodes.items() if node.get("type") == "candidate" and node_id != "Candidate.selected"}
    design_space_members = {str(edge["source"]) for edge in _edges(graph, "candidate_of") if edge.get("target") == "VCO.design_space"}
    checks["design_space_contains_every_candidate"] = candidates == design_space_members
    realized_by_candidate = {
        str(edge.get("source")): str(edge.get("target"))
        for edge in _edges(graph, "realizes")
        if edge.get("source") in candidates
    }
    checks["candidate_instance_mapping_is_one_to_one"] = (
        set(realized_by_candidate) == candidates
        and len(set(realized_by_candidate.values())) == len(realized_by_candidate)
    )

    validation_edges = [edge for edge in _edges(graph) if edge.get("type") in {"validated_by", "evaluates", "covers", "verifies_requirement"}]
    checks["evaluation_status_consistent"] = all((edge.get("properties", {}).get("passed") is not False or edge.get("status") == "rejected") and (edge.get("properties", {}).get("passed") is not True or edge.get("status") != "rejected") for edge in validation_edges)
    evidence_ids = {node_id for node_id, node in nodes.items() if node.get("type") == "evidence"}
    evidence_refs = [edge.get("properties", {}).get("evidence_id") for edge in _edges(graph) if edge.get("properties", {}).get("evidence_id") is not None]
    checks["evidence_references_resolve"] = all(ref in evidence_ids for ref in evidence_refs)
    checks["selected_context_is_covered"] = any(edge.get("source") == "Context.VCO.contract" and edge.get("target") == "Context.SystemTB.final" and edge.get("type") == "covers" and edge.get("properties", {}).get("passed") is True for edge in _edges(graph))

    if expected is not None and selected_id is not None:
        checks["selected_candidate_matches_artifact"] = selected_id == expected.get("selected_candidate")
        checks["required_pn_matches_artifact"] = _close(nodes["VCORequirement.required"]["properties"].get("value"), expected.get("required_pn"))
        checks["recommended_pn_matches_artifact"] = _close(nodes["VCORequirement.recommended"]["properties"].get("value"), expected.get("recommended_pn"))
        block_props = nodes[block_id]["properties"]
        system_props = nodes[system_id]["properties"]
        checks["blocktb_matches_artifact"] = block_props.get("checks") == expected.get("block_tb", {}).get("checks") and block_props.get("worst_case") == expected.get("block_tb", {}).get("worst_case")
        checks["systemtb_matches_artifact"] = system_props.get("metrics") == expected.get("candidate_system", {}).get("metrics") and system_props.get("residuals") == expected.get("candidate_system", {}).get("residuals")
        final_props = nodes["Evidence.SystemTB.final"]["properties"]
        checks["final_systemtb_matches_artifact"] = final_props.get("metrics") == expected.get("final_system", {}).get("metrics") and final_props.get("residuals") == expected.get("final_system", {}).get("residuals")
        checks["final_context_coverage_matches_artifact"] = nodes["Context.SystemTB.final"]["properties"].get("coverage") == expected.get("final_context_coverage")

    return {"passed": all(checks.values()), "outcome": outcome, "selected_candidate": selected_id, "checks": checks, "diagnostics": diagnostics}


def build_agent_goal_context(graph: Mapping[str, Any]) -> Dict[str, Any]:
    """Build the deterministic context an Agent needs before proposing work."""

    nodes = _node_map(graph)
    initial = nodes.get("Evidence.SystemTB.initial", {}).get("properties", {})
    per_checks = initial.get("checks", {})
    if not per_checks:
        residual_to_check = {
            "integrated_jitter_residual_s_max": "integrated_jitter",
            "lock_time_residual_s_max": "lock_time",
            "power_residual_w_max": "power",
            "output_frequency_residual_hz_max": "output_frequency",
        }
        per_checks = {
            check: initial.get("residuals", {}).get(residual) <= 0
            for residual, check in residual_to_check.items()
            if initial.get("residuals", {}).get(residual) is not None
        }
    failed = sorted(name for name, passed in per_checks.items() if not passed)
    target_metric = {"integrated_jitter": "PLL.integrated_jitter", "lock_time": "PLL.lock_time", "power": "PLL.power", "output_frequency": "PLL.output_frequency"}
    variables = []
    inactive_variables = []
    structural_hypotheses = []
    for check in failed:
        metric = target_metric.get(check)
        if metric is None:
            continue
        for edge in _edges(graph):
            if edge.get("target") != metric or edge.get("type") not in {"sensitivity_evidence", "system_influence", "shortcut"}:
                continue
            source = str(edge["source"])
            source_node = nodes.get(source, {})
            if source_node.get("type") not in {"candidate_knob", "design_variable", "behavioral_output", "port"}:
                continue
            evidence_id = edge.get("properties", {}).get("evidence_id")
            raw_value = edge.get("properties", {}).get("value")
            try:
                sensitivity_magnitude = abs(float(raw_value)) if raw_value is not None else None
            except (TypeError, ValueError):
                sensitivity_magnitude = None
            record = {
                "failed_check": check,
                "system_metric": metric,
                "variable": source,
                "edge_type": edge["type"],
                "evidence_id": evidence_id,
                "evidence_available": evidence_id in nodes,
                "sensitivity_value": raw_value,
                "sensitivity_magnitude": sensitivity_magnitude,
                "observed_metric_span": edge.get("properties", {}).get("observed_metric_span"),
                "recommended_verification": "boundary_search" if check == "integrated_jitter" and "phase_noise" in source else "parameter_sweep",
            }
            if not record["evidence_available"]:
                structural_hypotheses.append(record)
            elif edge.get("properties", {}).get("active_in_sweep") is False:
                inactive_variables.append(record)
            else:
                variables.append(record)
    sort_key = lambda item: (
        item["failed_check"],
        -(item["observed_metric_span"] or 0.0),
        item["variable"],
    )
    variables.sort(key=sort_key)
    inactive_variables.sort(key=sort_key)
    structural_hypotheses.sort(key=sort_key)
    return {
        "failed_checks": failed,
        "candidate_variables": variables,
        "inactive_variables": inactive_variables,
        "structural_hypotheses": structural_hypotheses,
        "policy": "Agent proposes; deterministic tools validate",
    }
