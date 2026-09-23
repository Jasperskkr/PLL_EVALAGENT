"""Closure audit for V1.5 multidimensional allocation graphs."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Sequence

from .queries import trace_paths
from .validators import validate_graph_v2_artifact
from .factors import audit_factor_graph


REQUIREMENT_IDS = {
    "SystemSpec.integrated_jitter",
    "SystemSpec.lock_time",
    "SystemSpec.output_frequency",
    "SystemSpec.power",
}


def _nodes(graph: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {str(node["id"]): node for node in graph.get("nodes", [])}


def _edges(
    graph: Mapping[str, Any], edge_type: str | None = None
) -> list[Mapping[str, Any]]:
    return [
        edge
        for edge in graph.get("edges", [])
        if edge_type is None or edge.get("type") == edge_type
    ]


def _point_id(candidate_node_id: str) -> str:
    return candidate_node_id.split(".", 1)[1]


def audit_v15_graph(
    graph: Mapping[str, Any],
    *,
    records: Sequence[Mapping[str, Any]],
    sample_set_sha256: str,
    system_boundary_map: Mapping[str, Any],
    boundary_block_contract: Mapping[str, Any],
    conditional_block_spec_map: Mapping[str, Any],
    conditional_candidate_validation: Mapping[str, Any],
    conditional_contract_prediction: Mapping[str, Any],
    capability_region: Mapping[str, Any],
    system_feasible_region: Mapping[str, Any],
    selection_decision: Mapping[str, Any],
    replay_evidence: Mapping[str, Any],
) -> Dict[str, Any]:
    """Audit exact point membership, TB closure, selection and replay trace."""

    checks: Dict[str, bool] = {}
    diagnostics: list[str] = []
    try:
        validate_graph_v2_artifact(graph)
        checks["schema_and_semantics"] = True
    except ValueError as exc:
        checks["schema_and_semantics"] = False
        diagnostics.append(str(exc))

    nodes = _nodes(graph)
    metadata = graph.get("metadata", {})
    factor_audit = audit_factor_graph(
        graph,
        required_factor_ids=(
            "pll_jitter_response",
            "conditional_pn_allocation",
        ),
    )
    # Factor checks are gated by the explicit schema marker so pre-factor V1.5
    # artifacts remain readable/auditable for backward compatibility.
    factorized = metadata.get("factor_schema_version") is not None
    if factorized:
        checks["factor_schema_and_closure"] = factor_audit["passed"]
        diagnostics.extend(factor_audit.get("diagnostics", []))
        factor_nodes = {
            str(node["id"]): node for node in graph.get("nodes", []) if node.get("type") == "factor"
        }
        response_props = factor_nodes.get("Factor.pll_jitter_response", {}).get("properties", {})
        allocation_props = factor_nodes.get("Factor.conditional_pn_allocation", {}).get("properties", {})
        checks["system_response_factor_semantics"] = (
            response_props.get("factor_type") == "system_response"
            and response_props.get("input_refs") == [
                "VCO.pn_anchor_1mhz",
                "VCO.k1_hz_per_v",
                "Context.VCO.contract.v1_5",
            ]
            and response_props.get("output_refs") == ["PLL.integrated_jitter"]
            and response_props.get("verification_status") == "validated"
            and response_props.get("model_kind") == "deterministic_behavioral_response"
        )
        allocation_domain = allocation_props.get("validity_domain", {})
        allocated_values = {
            float(entry["condition"]["value"])
            for entry in conditional_block_spec_map.get("entries", [])
        }
        unallocated_values = {
            float(entry["condition"]["value"])
            for entry in conditional_block_spec_map.get("unallocated_slices", [])
        }
        checks["allocation_factor_semantics"] = (
            allocation_props.get("factor_type") == "allocation"
            and allocation_props.get("model_kind") == "discrete_conditional_map"
            and allocation_props.get("input_refs") == [
                "SystemSpec.integrated_jitter",
                "SystemSpec.lock_time",
                "SystemSpec.output_frequency",
                "SystemSpec.power",
                "VCO.k1_hz_per_v",
                "Context.VCO.contract.v1_5",
            ]
            and allocation_props.get("output_refs") == [
                "VCORequirement.conditional_phase_noise"
            ]
            and allocation_props.get("verification_status") == "validated"
            and allocation_domain.get("interpolation_allowed") is False
            and set(float(value) for value in allocation_domain.get("validated_condition_values", []))
            == allocated_values
            and set(float(value) for value in allocation_domain.get("unallocated_condition_values", []))
            == unallocated_values
        )
        checks["allocation_factor_margin_traceable"] = (
            allocation_props.get("metadata", {}).get("engineering_margin")
            == conditional_block_spec_map.get("engineering_margin")
            and allocation_domain.get("interpolation_allowed") is False
            and allocated_values.isdisjoint(unallocated_values)
        )
        checks["allocation_factor_has_complete_evidence_chain"] = set(
            allocation_props.get("evidence_refs", [])
        ) == {
            "Evidence.V1_5.system_boundary_map",
            "Evidence.V1_5.boundary_block_contract",
            "Evidence.V1_5.conditional_block_spec_map",
            "Evidence.V1_5.conditional_candidate_validation",
            "Evidence.V1_5.conditional_contract_prediction",
        }
    checks["v15_profile_declared"] = metadata.get("artifact_profile") == "v1_5_multidim"
    checks["graph_remains_v2"] = graph.get("graph_version") == "2.0"
    checks["sample_hash_matches"] = (
        metadata.get("sample_set_sha256") == sample_set_sha256
    )
    checks["allocation_outcome_is_conditional_and_validated"] = (
        metadata.get("allocation_outcome")
        == "conditional_block_spec_allocated_and_validated_on_mapped_slices"
        and metadata.get("block_spec_mapping_status")
        == "allocated_on_mapped_slices"
        and metadata.get("boundary_block_contract_status")
        == "validated_boundary_block_contract"
        and metadata.get("conditional_candidate_validation_status")
        == "validated_on_all_allocated_slices"
    )
    checks["system_boundary_hash_matches"] = metadata.get(
        "system_boundary_map_sha256"
    ) == system_boundary_map.get("boundary_map_sha256")
    checks["boundary_block_contract_hash_matches"] = metadata.get(
        "boundary_block_contract_sha256"
    ) == boundary_block_contract.get("contract_sha256")
    checks["boundary_contract_derives_from_boundary_map"] = (
        boundary_block_contract.get("source_boundary_map_sha256")
        == system_boundary_map.get("boundary_map_sha256")
    )
    checks["conditional_block_spec_hash_matches"] = metadata.get(
        "conditional_block_spec_map_sha256"
    ) == conditional_block_spec_map.get("block_spec_map_sha256")
    checks["conditional_validation_hash_matches"] = metadata.get(
        "conditional_candidate_validation_sha256"
    ) == conditional_candidate_validation.get("validation_sha256")
    checks["conditional_prediction_hash_matches"] = metadata.get(
        "conditional_contract_prediction_sha256"
    ) == conditional_contract_prediction.get("prediction_sha256")
    checks["conditional_allocation_derives_from_contract"] = (
        conditional_block_spec_map.get(
            "source_boundary_block_contract_sha256"
        )
        == boundary_block_contract.get("contract_sha256")
        and conditional_candidate_validation.get(
            "source_block_spec_map_sha256"
        )
        == conditional_block_spec_map.get("block_spec_map_sha256")
    )
    checks["capability_hash_matches"] = metadata.get(
        "capability_region_sha256"
    ) == capability_region.get("region_sha256")
    checks["system_region_hash_matches"] = metadata.get(
        "system_feasible_region_sha256"
    ) == system_feasible_region.get("region_sha256")
    checks["selection_hash_matches"] = metadata.get(
        "selection_sha256"
    ) == selection_decision.get("selection_sha256")
    checks["replay_hash_matches"] = metadata.get("replay_sha256") == replay_evidence.get(
        "replay_sha256"
    )
    boundary_node = nodes.get("Evidence.V1_5.system_boundary_map", {}).get(
        "properties", {}
    )
    checks["system_boundary_node_matches_artifact"] = (
        boundary_node.get("boundary_map_sha256")
        == system_boundary_map.get("boundary_map_sha256")
        and boundary_node.get("mapped_boundary_count")
        == system_boundary_map.get("mapped_boundary_count")
        and boundary_node.get("block_spec_mapping_status") == "pending"
    )
    contract_node = nodes.get(
        "Contract.VCO.boundary_behavior.v1_5", {}
    ).get("properties", {})
    contract_evidence_node = nodes.get(
        "Evidence.V1_5.boundary_block_contract", {}
    ).get("properties", {})
    checks["boundary_contract_nodes_match_artifact"] = (
        contract_node.get("contract_sha256")
        == boundary_block_contract.get("contract_sha256")
        and contract_node.get("entry_count")
        == boundary_block_contract.get("entry_count")
        and contract_node.get("interpolation_allowed") is False
        and contract_node.get("block_spec_mapping_status") == "pending"
        and contract_evidence_node.get("contract_sha256")
        == boundary_block_contract.get("contract_sha256")
        and contract_evidence_node.get("validation_passed") is True
    )
    conditional_requirement = nodes.get(
        "VCORequirement.conditional_phase_noise", {}
    )
    allocation_edges = [
        edge
        for edge in _edges(graph, "allocates")
        if edge.get("source") == "SystemSpec.integrated_jitter"
        and edge.get("target") == "VCORequirement.conditional_phase_noise"
    ]
    checks["conditional_allocation_has_typed_requirement"] = (
        conditional_requirement.get("type") == "block_requirement"
        and conditional_requirement.get("properties", {}).get(
            "measured_metric"
        )
        == "worst_phase_noise_1mhz_dbc_hz"
        and conditional_requirement.get("properties", {}).get(
            "block_spec_map_sha256"
        )
        == conditional_block_spec_map.get("block_spec_map_sha256")
        and len(allocation_edges) == 1
    )
    refined_slices = [
        item
        for item in system_boundary_map.get("slices", [])
        if item.get("status") == "refined_system_boundary"
    ]
    checks["system_boundary_slices_are_closed"] = (
        len(refined_slices) == system_boundary_map.get("mapped_boundary_count")
        and all(
            item["refined_boundary"]["passing_evidence"]["system_passed"]
            and not item["refined_boundary"]["nearest_failing_evidence"][
                "system_passed"
            ]
            and item["refined_boundary"]["passing_value"]
            < item["refined_boundary"]["nearest_failing_value"]
            and item["refined_boundary"]["bracket_width"] > 0.0
            for item in refined_slices
        )
    )
    refined_by_condition = {
        float(item["condition"]["value"]): item
        for item in refined_slices
    }
    contract_entries = list(boundary_block_contract.get("entries", []))
    contract_by_condition = {
        float(item["condition"]["value"]): item for item in contract_entries
    }
    checks["boundary_contract_entries_are_closed"] = (
        len(contract_entries) == boundary_block_contract.get("entry_count")
        == system_boundary_map.get("mapped_boundary_count")
        and set(contract_by_condition) == set(refined_by_condition)
        and all(
            entry["source_system_boundary"]["passing_value"]
            == refined_by_condition[condition]["refined_boundary"][
                "passing_value"
            ]
            and entry["source_system_boundary"]["nearest_failing_value"]
            == refined_by_condition[condition]["refined_boundary"][
                "nearest_failing_value"
            ]
            and entry["measured_block_behavior"]
            == refined_by_condition[condition]["refined_boundary"][
                "passing_evidence"
            ]["behavior_vector"]
            and entry["block_tb"]["passed"]
            and entry["system_boundary_confirmation"]["passed"]
            and entry["independent_replay_validation"]["passed"]
            for condition, entry in contract_by_condition.items()
        )
    )
    contract_validation_checks = boundary_block_contract.get(
        "validation", {}
    ).get("checks", {})
    checks["boundary_contract_validation_passes"] = bool(
        boundary_block_contract.get("validation", {}).get("passed")
        and contract_validation_checks
        and all(contract_validation_checks.values())
        and boundary_block_contract.get("interpolation_allowed") is False
        and boundary_block_contract.get("block_spec_mapping_status") == "pending"
    )
    allocation_entries = list(conditional_block_spec_map.get("entries", []))
    allocation_by_condition = {
        float(item["condition"]["value"]): item
        for item in allocation_entries
    }
    margin_db = float(
        conditional_block_spec_map.get("engineering_margin", {}).get(
            "value_db", 0.0
        )
    )
    checks["conditional_block_spec_map_is_closed"] = (
        bool(conditional_block_spec_map.get("validation", {}).get("passed"))
        and len(allocation_entries)
        == conditional_block_spec_map.get("entry_count")
        == boundary_block_contract.get("entry_count")
        and set(allocation_by_condition) == set(contract_by_condition)
        and conditional_block_spec_map.get("interpolation_allowed") is False
        and margin_db > 0.0
        and all(
            entry["source_boundary_behavior"]
            == contract_by_condition[condition]["measured_block_behavior"]
            and entry["allocated_block_spec"][
                "phase_noise_1mhz_max_dbc_hz"
            ]
            == entry["source_boundary_behavior"][
                "worst_phase_noise_1mhz_dbc_hz"
            ]
            - margin_db
            for condition, entry in allocation_by_condition.items()
        )
    )
    allocation_evidence_node = nodes.get(
        "Evidence.V1_5.conditional_block_spec_map", {}
    ).get("properties", {})
    checks["conditional_allocation_node_matches_artifact"] = (
        allocation_evidence_node.get("block_spec_map_sha256")
        == conditional_block_spec_map.get("block_spec_map_sha256")
        and allocation_evidence_node.get("entry_count")
        == conditional_block_spec_map.get("entry_count")
        and allocation_evidence_node.get("validation_passed") is True
        and allocation_evidence_node.get("interpolation_allowed") is False
    )
    candidate_validation_entries = list(
        conditional_candidate_validation.get("entries", [])
    )
    boundary_point_ids: set[str] = set()
    for slice_item in system_boundary_map.get("slices", []):
        initial = slice_item.get("initial_bracket", {})
        for key in ("passing_point_id", "failing_point_id"):
            if initial.get(key) is not None:
                boundary_point_ids.add(str(initial[key]))
        refined = slice_item.get("refined_boundary", {})
        for evidence_key in ("passing_evidence", "nearest_failing_evidence"):
            evidence = refined.get(evidence_key, {})
            if evidence.get("point_id") is not None:
                boundary_point_ids.add(str(evidence["point_id"]))
        for trial in slice_item.get("refinement_history", []):
            if trial.get("point_id") is not None:
                boundary_point_ids.add(str(trial["point_id"]))
    validation_node = nodes.get(
        "Evidence.V1_5.conditional_candidate_validation", {}
    ).get("properties", {})
    prediction_node = nodes.get(
        "Evidence.V1_5.conditional_contract_prediction", {}
    ).get("properties", {})
    checks["all_conditional_allocations_are_candidate_validated"] = (
        bool(
            conditional_candidate_validation.get("validation", {}).get(
                "passed"
            )
        )
        and len(candidate_validation_entries)
        == conditional_candidate_validation.get("validation", {}).get(
            "validated_condition_count"
        )
        == conditional_block_spec_map.get("entry_count")
        and all(item.get("passed") for item in candidate_validation_entries)
        and all(
            str(item["selected_validation_candidate"]["point_id"])
            not in boundary_point_ids
            and item["checks"].get(
                "candidate_not_used_for_boundary_extraction"
            )
            is True
            for item in candidate_validation_entries
        )
        and conditional_candidate_validation.get("boundary_extraction_point_count")
        == len(boundary_point_ids)
        and validation_node.get("passed") is True
        and validation_node.get("validation_sha256")
        == conditional_candidate_validation.get("validation_sha256")
    )
    checks["conditional_contract_prediction_passes"] = (
        bool(conditional_contract_prediction.get("validation", {}).get("passed"))
        and conditional_contract_prediction.get("validation", {}).get(
            "false_positive_count"
        )
        == 0
        and prediction_node.get("passed") is True
        and prediction_node.get("prediction_sha256")
        == conditional_contract_prediction.get("prediction_sha256")
    )

    expected_point_ids = {str(record["point_id"]) for record in records}
    candidate_nodes = {
        node_id
        for node_id, node in nodes.items()
        if node.get("type") == "candidate" and node_id != "Candidate.selected"
    }
    graph_point_ids = {_point_id(node_id) for node_id in candidate_nodes}
    checks["one_candidate_per_sampled_point"] = graph_point_ids == expected_point_ids

    design_members = {
        _point_id(str(edge["source"]))
        for edge in _edges(graph, "candidate_of")
        if edge.get("target") == "VCO.design_space"
    }
    capability_members = {
        _point_id(str(edge["source"]))
        for edge in _edges(graph, "candidate_of")
        if edge.get("target") == "VCO.capability_region"
    }
    system_members = {
        _point_id(str(edge["source"]))
        for edge in _edges(graph, "candidate_of")
        if edge.get("target") == "PLL.system_feasible_region"
    }
    expected_capability = {
        str(member["point_id"]) for member in capability_region["members"]
    }
    expected_system = {
        str(member["point_id"]) for member in system_feasible_region["members"]
    }
    checks["design_space_membership_exact"] = design_members == expected_point_ids
    checks["capability_membership_exact"] = capability_members == expected_capability
    checks["system_feasible_membership_exact"] = system_members == expected_system
    checks["system_region_is_capability_subset"] = system_members.issubset(
        capability_members
    )

    records_by_id = {str(record["point_id"]): record for record in records}
    checks["capability_contains_only_blocktb_pass"] = all(
        records_by_id[point_id]["status"]["block_feasible"]
        for point_id in capability_members
    )
    checks["system_region_contains_only_joint_pass"] = all(
        records_by_id[point_id]["status"]["jointly_feasible"]
        for point_id in system_members
    )

    realized_edges = [
        edge
        for edge in _edges(graph, "realizes")
        if str(edge.get("source")) in candidate_nodes
    ]
    realized_map = {
        str(edge["source"]): str(edge["target"]) for edge in realized_edges
    }
    checks["candidate_instance_mapping_one_to_one"] = (
        set(realized_map) == candidate_nodes
        and len(set(realized_map.values())) == len(realized_map)
    )

    all_point_evidence_matches = True
    all_instances_have_both_tbs = True
    all_system_requirements_traced = True
    all_context_edges_match = True
    graph_edges = _edges(graph)
    for point_id, record in records_by_id.items():
        instance_id = f"Instance.{point_id}"
        block_id = f"BlockTB.{point_id}"
        system_id = f"SystemTB.{point_id}"
        context_id = f"Context.SystemTB.{point_id}"
        block_node = nodes.get(block_id, {}).get("properties", {})
        system_node = nodes.get(system_id, {}).get("properties", {})
        all_point_evidence_matches = all_point_evidence_matches and (
            block_node.get("passed") == record["block_tb"]["passed"]
            and block_node.get("behavior_vector") == record["behavior_vector"]
            and system_node.get("passed") == record["system_tb"]["passed"]
            and system_node.get("metrics") == record["system_tb"]["metrics"]
            and system_node.get("residuals") == record["system_tb"]["residuals"]
        )
        evaluation_targets = {
            str(edge["target"])
            for edge in graph_edges
            if edge.get("source") == instance_id and edge.get("type") == "evaluates"
        }
        all_instances_have_both_tbs = all_instances_have_both_tbs and {
            block_id,
            system_id,
        }.issubset(evaluation_targets)
        requirement_targets = {
            str(edge["target"])
            for edge in _edges(graph, "verifies_requirement")
            if edge.get("source") == system_id
        }
        all_system_requirements_traced = all_system_requirements_traced and (
            requirement_targets == REQUIREMENT_IDS
        )
        coverage_edges = [
            edge
            for edge in _edges(graph, "covers")
            if edge.get("source") == "Context.VCO.contract.v1_5"
            and edge.get("target") == context_id
        ]
        all_context_edges_match = all_context_edges_match and (
            len(coverage_edges) == 1
            and coverage_edges[0].get("properties", {}).get("passed")
            == record["context_coverage"]["passed"]
        )
    checks["sampled_evidence_matches_artifacts"] = all_point_evidence_matches
    checks["every_instance_has_blocktb_and_systemtb"] = all_instances_have_both_tbs
    checks["every_systemtb_verifies_all_requirements"] = all_system_requirements_traced
    checks["every_context_coverage_edge_matches"] = all_context_edges_match

    selected_point_id = str(selection_decision["selected_candidate"]["point_id"])
    selected_edges = [
        edge
        for edge in _edges(graph, "selected_for")
        if edge.get("target") == "Candidate.selected"
    ]
    checks["exactly_one_selected_candidate"] = len(selected_edges) == 1
    checks["selected_candidate_matches_decision"] = bool(selected_edges) and (
        str(selected_edges[0]["source"]) == f"Candidate.{selected_point_id}"
    )
    checks["selected_candidate_is_system_feasible"] = selected_point_id in system_members
    checks["selection_node_matches_hash"] = nodes.get(
        "Evidence.V1_5.selection", {}
    ).get("properties", {}).get("selection_sha256") == selection_decision.get(
        "selection_sha256"
    )
    replay_props = nodes.get("Evidence.V1_5.selected_replay", {}).get(
        "properties", {}
    )
    checks["replay_node_matches_hash"] = replay_props.get(
        "replay_sha256"
    ) == replay_evidence.get("replay_sha256")
    checks["replay_is_identical_and_jointly_feasible"] = bool(
        replay_evidence.get("identical_to_sampled_evaluation")
        and replay_evidence.get("replay_jointly_feasible")
        and replay_props.get("passed")
    )
    checks["selected_instance_drives_replay"] = any(
        edge.get("source") == f"Instance.{selected_point_id}"
        and edge.get("target") == "Evidence.V1_5.selected_replay"
        and edge.get("type") == "evaluates"
        and edge.get("properties", {}).get("passed") is True
        for edge in graph_edges
    )
    final_verdict_requirements = {
        str(edge["target"])
        for edge in _edges(graph, "verifies_requirement")
        if edge.get("source") == "SystemSpec.verdict"
        and edge.get("properties", {}).get("passed") is True
    }
    checks["final_verdict_verifies_all_requirements"] = (
        final_verdict_requirements == REQUIREMENT_IDS
    )

    path_checks: list[bool] = []
    for requirement_id in sorted(REQUIREMENT_IDS):
        try:
            path_checks.append(
                bool(
                    trace_paths(
                        graph,
                        requirement_id,
                        "Candidate.selected",
                        max_depth=4,
                    )
                )
            )
        except (KeyError, ValueError) as exc:
            diagnostics.append(f"trace failed for {requirement_id}: {exc}")
            path_checks.append(False)
    checks["all_systemspec_paths_reach_selected_candidate"] = all(path_checks)

    return {
        "schema_version": "v1.5-graph-audit-1.2",
        "passed": all(checks.values()),
        "case_id": metadata.get("case_id"),
        "selected_point_id": selected_point_id,
        "counts": {
            "nodes": len(graph.get("nodes", [])),
            "edges": len(graph.get("edges", [])),
            "sampled_candidates": len(candidate_nodes),
            "capability_members": len(capability_members),
            "system_feasible_members": len(system_members),
            "boundary_contract_entries": len(contract_entries),
            "conditional_block_spec_entries": len(allocation_entries),
            "conditionally_validated_candidates": len(
                candidate_validation_entries
            ),
            "contract_prediction_candidates": conditional_contract_prediction[
                "validation"
            ]["candidate_count"],
            "factors": factor_audit["counts"]["factors"],
        },
        "factor_audit": factor_audit,
        "checks": checks,
        "diagnostics": diagnostics,
    }


__all__ = ["audit_v15_graph"]
