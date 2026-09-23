"""Compile V1.5 multidimensional evaluation evidence into TypedGraph v2."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .model import TypedGraph
from .validators import validate_graph_v2_artifact
from .factors import Factor, add_factor_to_graph


SYSTEM_REQUIREMENT_CHECKS = {
    "SystemSpec.integrated_jitter": ("integrated_jitter",),
    "SystemSpec.lock_time": ("lock_time", "locked"),
    "SystemSpec.output_frequency": ("output_frequency",),
    "SystemSpec.power": ("power",),
}


def _requirement_verdicts(checks: Mapping[str, bool]) -> dict[str, bool]:
    return {
        requirement_id: all(bool(checks.get(check, False)) for check in names)
        for requirement_id, names in SYSTEM_REQUIREMENT_CHECKS.items()
    }


def build_v15_graph_artifact(
    *,
    case: Mapping[str, Any],
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
) -> dict[str, Any]:
    """Compile sampled points, system boundaries, regions and replay evidence."""

    case_id = str(case["case_id"])
    context_contract = dict(case["block_context"])
    selected_point_id = str(selection_decision["selected_candidate"]["point_id"])
    capability_ids = {
        str(member["point_id"]) for member in capability_region["members"]
    }
    system_feasible_ids = {
        str(member["point_id"])
        for member in system_feasible_region["members"]
    }
    graph = TypedGraph(
        graph_id=f"{case_id}:vco_pll_graph_v2",
        graph_version="2.0",
        metadata={
            "artifact_profile": "v1_5_multidim",
            "case_id": case_id,
            "schema": "TypedGraph v2",
            "semantic_role_model": [
                "architecture",
                "behavior",
                "influence",
                "evidence",
            ],
            "plane_model": (
                "implementation_metadata_schema_contract_realization_evidence"
            ),
            "planes": ["schema", "contract", "realization", "evidence"],
            "allocation_outcome": conditional_candidate_validation[
                "workflow_outcome"
            ],
            "block_spec_mapping_status": conditional_candidate_validation[
                "block_spec_mapping_status"
            ],
            "boundary_block_contract_status": boundary_block_contract["status"],
            "conditional_candidate_validation_status": (
                conditional_candidate_validation["status"]
            ),
            "conditional_contract_prediction_status": (
                conditional_contract_prediction["status"]
            ),
            "block_context_id": context_contract["context_id"],
            "deterministic": True,
            "random_seed": None,
            "sample_set_sha256": sample_set_sha256,
            "system_boundary_map_sha256": system_boundary_map[
                "boundary_map_sha256"
            ],
            "boundary_block_contract_sha256": boundary_block_contract[
                "contract_sha256"
            ],
            "conditional_block_spec_map_sha256": conditional_block_spec_map[
                "block_spec_map_sha256"
            ],
            "conditional_candidate_validation_sha256": (
                conditional_candidate_validation["validation_sha256"]
            ),
            "conditional_contract_prediction_sha256": (
                conditional_contract_prediction["prediction_sha256"]
            ),
            "capability_region_sha256": capability_region["region_sha256"],
            "system_feasible_region_sha256": system_feasible_region[
                "region_sha256"
            ],
            "selection_sha256": selection_decision["selection_sha256"],
            "replay_sha256": replay_evidence["replay_sha256"],
            "agent_policy": "propose_only; deterministic_tools_validate",
            "claim_boundary": case.get("claim_boundary"),
            "factor_schema_version": "1.0",
            "factor_ids": [
                "pll_jitter_response",
                "conditional_pn_allocation",
            ],
        },
    )

    def node(
        node_id: str,
        node_type: str,
        semantic_role: str | None,
        properties: Mapping[str, Any] | None = None,
        *,
        owner: str | None = None,
        status: str | None = None,
    ) -> None:
        graph.add_node(
            node_id,
            node_type,
            properties,
            semantic_role=semantic_role,
            owner=owner,
            status=status,
        )

    def edge(
        source: str,
        target: str,
        edge_type: str,
        properties: Mapping[str, Any] | None = None,
        *,
        status: str = "validated",
    ) -> None:
        graph.add_edge(source, target, edge_type, properties, status=status)

    # Frozen architecture and public Block Graph semantics.
    node("PLL", "architecture_block", "architecture", {"architecture": "integer_n_cppll"})
    node("VCO", "architecture_block", "architecture", {"target_block": True})
    node("PLL.control_voltage", "port", "architecture", {"direction": "out", "unit": "V"}, owner="PLL")
    node("PLL.oscillation", "port", "architecture", {"direction": "in", "unit": "Hz"}, owner="PLL")
    node("VCO.vctrl", "port", "architecture", {"direction": "in", "unit": "V"}, owner="VCO")
    node("VCO.oscillation", "port", "architecture", {"direction": "out", "unit": "Hz"}, owner="VCO")
    node("Environment.temperature", "context_variable", "architecture", {"unit": "degC"})
    node("Environment.vdd", "context_variable", "architecture", {"unit": "V"})
    edge("PLL.control_voltage", "VCO.vctrl", "connects_to", {"signal": "control_voltage"})
    edge("VCO.oscillation", "PLL.oscillation", "connects_to", {"signal": "oscillation"})
    edge("VCO", "PLL", "signal_flow", {"signal": "oscillation"})
    edge("PLL", "VCO.vctrl", "feedback", {"signal": "control_voltage"})
    edge("Environment.temperature", "VCO", "requires", {"role": "system_context"})
    edge("Environment.vdd", "VCO", "requires", {"role": "system_context"})

    node("VCO.phase_noise_1mhz", "behavioral_output", "behavior", {"metric_name": "phase_noise_1mhz_dbc_hz", "unit": "dBc/Hz"}, owner="VCO")
    node("VCO.frequency", "behavioral_output", "behavior", {"metric_name": "frequency_hz", "unit": "Hz"}, owner="VCO")
    node("VCO.kvco", "behavioral_output", "behavior", {"metric_name": "kvco_hz_per_v", "unit": "Hz/V"}, owner="VCO")
    node("VCO.power", "behavioral_output", "behavior", {"metric_name": "power_w", "unit": "W"}, owner="VCO")
    node("VCO.pn_anchor_1mhz", "candidate_knob", None, {"parameter_identity": "internal_model_knob", "knob_name": "pn_anchor_1mhz_dbc_hz", "unit": "dBc/Hz"}, owner="VCO")
    node("VCO.k1_hz_per_v", "candidate_knob", None, {"parameter_identity": "internal_model_knob", "knob_name": "k1_hz_per_v", "unit": "Hz/V"}, owner="VCO")
    edge("VCO.pn_anchor_1mhz", "VCO.phase_noise_1mhz", "behavioral_dependency", {"mechanism": "parameterizes_context_dependent_profile"})
    edge("VCO.k1_hz_per_v", "VCO.kvco", "behavioral_dependency", {"mechanism": "parameterizes_nonlinear_tuning_slope"})
    edge("VCO.k1_hz_per_v", "VCO.frequency", "behavioral_dependency", {"mechanism": "parameterizes_linear_tuning_term"})
    edge("VCO.vctrl", "VCO.frequency", "behavioral_dependency", {"equation_ref": "frequency_hz(Vctrl,T)"})
    edge("VCO.vctrl", "VCO.kvco", "behavioral_dependency", {"equation_ref": "kvco_hz_per_v(Vctrl)"})
    edge("VCO.vctrl", "VCO.phase_noise_1mhz", "behavioral_dependency", {"equation_ref": "phase_noise_dbc_hz(offset,Vctrl,T,power)"})
    edge("VCO.vctrl", "VCO.power", "behavioral_dependency", {"equation_ref": "power_w(Vctrl,T)"})

    node("operator.VCO_Noise_TF", "operator", "influence", {"operator": "vco_noise_transfer", "model_ref": "behavioral_vco_noise_v1"})
    node("operator.Noise_Integration", "operator", "influence", {"operator": "psd_to_integrated_jitter", "aggregation": "quadrature_psd_integral"})
    node("operator.PLL_Dynamics", "operator", "influence", {"operator": "closed_loop_dynamics", "model_ref": "averaged_cppll_v1"})
    node("PLL.integrated_jitter", "system_metric", "influence", {"metric_name": "integrated_jitter_s", "unit": "s"}, owner="PLL")
    node("PLL.lock_time", "system_metric", "influence", {"metric_name": "lock_time_s", "unit": "s"}, owner="PLL")
    node("PLL.output_frequency", "system_metric", "influence", {"metric_name": "output_frequency_hz", "unit": "Hz"}, owner="PLL")
    node("PLL.power", "system_metric", "influence", {"metric_name": "power_w", "unit": "W"}, owner="PLL")
    edge("VCO.phase_noise_1mhz", "operator.VCO_Noise_TF", "input_to", {"context_ref": context_contract["context_id"]})
    edge("operator.VCO_Noise_TF", "operator.Noise_Integration", "input_to", {"transfer": "high_pass_locked_loop"})
    edge("operator.Noise_Integration", "PLL.integrated_jitter", "produces", {"equation_ref": "integrated_vco_jitter_s"})
    edge("VCO.phase_noise_1mhz", "PLL.integrated_jitter", "system_influence", {"source_behavior_metric": "phase_noise_1mhz_dbc_hz", "target_system_metric": "integrated_jitter_s", "mechanism": "noise_transfer_and_integration", "evidence_refs": ["Evidence.V1_5.sample_set"], "validity_domain": context_contract["context_id"]})
    edge("VCO.kvco", "operator.PLL_Dynamics", "input_to", {"context_ref": context_contract["context_id"]})
    edge("operator.PLL_Dynamics", "PLL.lock_time", "produces", {"equation_ref": "lock_time_from_reference_cycles"})
    edge("VCO.kvco", "PLL.integrated_jitter", "system_influence", {"source_behavior_metric": "kvco_hz_per_v", "target_system_metric": "integrated_jitter_s", "mechanism": "loop_bandwidth_change", "evidence_refs": ["Evidence.V1_5.sample_set"], "validity_domain": context_contract["context_id"]})
    edge("VCO.kvco", "PLL.lock_time", "system_influence", {"source_behavior_metric": "kvco_hz_per_v", "target_system_metric": "lock_time_s", "mechanism": "closed_loop_dynamics", "evidence_refs": ["Evidence.V1_5.sample_set"], "validity_domain": context_contract["context_id"]})
    edge("VCO.frequency", "PLL.output_frequency", "system_influence", {"source_behavior_metric": "frequency_hz", "target_system_metric": "output_frequency_hz", "mechanism": "divider_feedback", "evidence_refs": ["Evidence.V1_5.sample_set"], "validity_domain": context_contract["context_id"]})
    edge("VCO.power", "PLL.power", "system_influence", {"source_behavior_metric": "power_w", "target_system_metric": "power_w", "mechanism": "block_power_aggregation", "evidence_refs": ["Evidence.V1_5.sample_set"], "validity_domain": context_contract["context_id"]})

    # Immutable SystemSpec and region workflow objects.
    limits = case["system_spec"]["limits"]
    requirement_nodes = {
        "SystemSpec.integrated_jitter": ("PLL.integrated_jitter", limits["integrated_jitter_max_s"], "upper_bound"),
        "SystemSpec.lock_time": ("PLL.lock_time", limits["lock_time_max_s"], "upper_bound"),
        "SystemSpec.output_frequency": ("PLL.output_frequency", limits["output_frequency_tolerance_hz"], "tolerance"),
        "SystemSpec.power": ("PLL.power", limits["power_max_w"], "upper_bound"),
    }
    for requirement_id, (metric_id, limit, direction) in requirement_nodes.items():
        node(requirement_id, "system_requirement", None, {"source": "immutable SystemSpec", "parameter_identity": "requirement", "requirement_id": requirement_id, "metric": metric_id, "limit": limit, "direction": direction})
        edge(requirement_id, metric_id, "constrains", {"direction": direction, "value": limit})

    node("VCORequirement.conditional_phase_noise", "block_requirement", None, {"source": "conditional_block_spec_map.json", "parameter_identity": "conditional_block_requirement", "metric": "phase_noise_1mhz_max_dbc_hz", "measured_metric": "worst_phase_noise_1mhz_dbc_hz", "representation": "discrete_conditional_table", "condition_axis": conditional_block_spec_map["condition_axis"], "entry_count": conditional_block_spec_map["entry_count"], "engineering_margin": conditional_block_spec_map["engineering_margin"], "interpolation_allowed": False, "block_spec_map_sha256": conditional_block_spec_map["block_spec_map_sha256"], "artifact_ref": "conditional_block_spec_map.json"}, owner="VCO", status="validated")
    edge("SystemSpec.integrated_jitter", "VCORequirement.conditional_phase_noise", "allocates", {"mapping": "PN_spec(k1)", "entry_count": conditional_block_spec_map["entry_count"], "block_spec_map_sha256": conditional_block_spec_map["block_spec_map_sha256"]})
    edge("SystemSpec.lock_time", "VCORequirement.conditional_phase_noise", "constrains", {"role": "condition_axis_feasibility", "condition_axis": conditional_block_spec_map["condition_axis"], "unallocated_slice_count": conditional_block_spec_map["validation"]["unallocated_slice_count"]})

    node("VCO.design_space", "design_space", None, {"representation": "candidate_knobs", "dimensions": list(case["design_space"]["axis_order"]), "sample_count": len(records), "includes_infeasible": True, "artifact_ref": "design_space.json"}, owner="VCO", status="validated")
    node("VCO.capability_region", "capability_region", None, {"representation": "measured_behavior", "dimensions": list(capability_region["axes"]), "member_count": capability_region["member_count"], "region_sha256": capability_region["region_sha256"], "formal_status": capability_region["formal_status"], "artifact_ref": "capability_region.json"}, owner="VCO", status="validated")
    node("PLL.system_feasible_region", "system_feasible_region", None, {"representation": system_feasible_region["representation_space"], "dimensions": list(system_feasible_region["design_axes"]), "member_count": system_feasible_region["member_count"], "region_sha256": system_feasible_region["region_sha256"], "formal_status": system_feasible_region["formal_status"], "artifact_ref": "system_feasible_region.json"}, owner="PLL", status="validated")
    for requirement_id in requirement_nodes:
        edge(requirement_id, "PLL.system_feasible_region", "constrains", {"membership_requires_pass": True, "check_names": list(SYSTEM_REQUIREMENT_CHECKS[requirement_id])})

    node("Context.VCO.contract.v1_5", "context", "architecture", context_contract, owner="VCO", status="validated")
    node("Measurement.VCO.behavior_vector", "measurement_contract", None, {"metrics": list(case["measurement_contract"]["behavior_vector"]), "method": "frozen_context_behavioral_sweep", "context_source": context_contract["context_id"]}, owner="VCO", status="validated")
    node("Contract.VCO.boundary_behavior.v1_5", "contract", None, {"contract_id": boundary_block_contract["contract_id"], "contract_type": boundary_block_contract["contract_type"], "contract_form": boundary_block_contract["contract_form"], "condition_axis": boundary_block_contract["condition_axis"], "search_axis": boundary_block_contract["search_axis"], "entry_count": boundary_block_contract["entry_count"], "interpolation_allowed": boundary_block_contract["interpolation_allowed"], "contract_sha256": boundary_block_contract["contract_sha256"], "block_spec_mapping_status": boundary_block_contract["block_spec_mapping_status"], "source": "v1.allocation.boundary_contract", "artifact_ref": "boundary_block_contract.json"}, owner="VCO", status="validated")
    node("Validity.VCO.boundary_behavior.v1_5", "validity_domain", None, {"declared_domain": dict(boundary_block_contract["validity_domain"]), "validated_domain": dict(boundary_block_contract["validity_domain"]), "fidelity": boundary_block_contract["validity_domain"]["model_fidelity"], "source": "boundary_block_contract.json"}, owner="VCO", status="validated")
    edge("Contract.VCO.boundary_behavior.v1_5", "Validity.VCO.boundary_behavior.v1_5", "valid_in", {"only_listed_condition_values_validated": True, "interpolation_allowed": False})
    for behavior_node in (
        "VCO.phase_noise_1mhz",
        "VCO.frequency",
        "VCO.kvco",
        "VCO.power",
    ):
        edge(
            behavior_node,
            "Measurement.VCO.behavior_vector",
            "measured_by",
            {"context_source": context_contract["context_id"]},
        )

    # Run-level evidence.
    node("Evidence.V1_5.sample_set", "evidence", "evidence", {"kind": "deterministic_multidimensional_sample_set", "sample_count": len(records), "sample_set_sha256": sample_set_sha256, "measurement_method": "deterministic_cartesian_grid_BlockTB_SystemTB", "artifact_ref": "sampled_points.jsonl"}, status="validated")
    node("Evidence.V1_5.system_boundary_map", "evidence", "evidence", {"kind": "conditional_system_spec_boundary_map", "condition_axis": system_boundary_map["condition_axis"], "search_axis": system_boundary_map["search_axis"], "slice_count": system_boundary_map["slice_count"], "mapped_boundary_count": system_boundary_map["mapped_boundary_count"], "block_spec_mapping_status": system_boundary_map["block_spec_mapping_status"], "boundary_map_sha256": system_boundary_map["boundary_map_sha256"], "measurement_method": "sampled_bracket_then_deterministic_bisection", "artifact_ref": "system_boundary_map.json"}, status="validated")
    node("Evidence.V1_5.boundary_block_contract", "evidence", "evidence", {"kind": "conditional_boundary_block_contract_extraction", "entry_count": boundary_block_contract["entry_count"], "validation_passed": boundary_block_contract["validation"]["passed"], "contract_sha256": boundary_block_contract["contract_sha256"], "source_boundary_map_sha256": boundary_block_contract["source_boundary_map_sha256"], "measurement_method": boundary_block_contract["measurement_method"], "artifact_ref": "boundary_block_contract.json"}, status="validated")
    node("Evidence.V1_5.conditional_block_spec_map", "evidence", "evidence", {"kind": "conditional_block_spec_allocation", "entry_count": conditional_block_spec_map["entry_count"], "unallocated_slice_count": conditional_block_spec_map["validation"]["unallocated_slice_count"], "engineering_margin": conditional_block_spec_map["engineering_margin"], "interpolation_allowed": False, "validation_passed": conditional_block_spec_map["validation"]["passed"], "block_spec_map_sha256": conditional_block_spec_map["block_spec_map_sha256"], "measurement_method": conditional_block_spec_map["method"], "artifact_ref": "conditional_block_spec_map.json"}, status="validated")
    node("Evidence.V1_5.conditional_candidate_validation", "evaluation", "evidence", {"result_identity": "per_condition_BlockSpec_and_SystemSpec_validation", "passed": conditional_candidate_validation["validation"]["passed"], "validated_condition_count": conditional_candidate_validation["validation"]["validated_condition_count"], "unallocated_slice_count": conditional_candidate_validation["validation"]["unallocated_slice_count"], "validation_sha256": conditional_candidate_validation["validation_sha256"], "source_block_spec_map_sha256": conditional_candidate_validation["source_block_spec_map_sha256"], "measurement_method": conditional_candidate_validation["method"], "artifact_ref": "conditional_candidate_validation.json"}, status="validated")
    node("Evidence.V1_5.conditional_contract_prediction", "evaluation", "evidence", {"result_identity": "conditional_contract_prediction", "passed": conditional_contract_prediction["validation"]["passed"], "condition_count": conditional_contract_prediction["validation"]["condition_count"], "candidate_count": conditional_contract_prediction["validation"]["candidate_count"], "certified_candidate_count": conditional_contract_prediction["validation"]["certified_candidate_count"], "false_positive_count": conditional_contract_prediction["validation"]["false_positive_count"], "prediction_sha256": conditional_contract_prediction["prediction_sha256"], "source_block_spec_map_sha256": conditional_contract_prediction["source_block_spec_map_sha256"], "measurement_method": conditional_contract_prediction["method"], "artifact_ref": "conditional_contract_prediction.json"}, status="validated")
    node("Evidence.V1_5.regions", "evidence", "evidence", {"kind": "sampled_region_construction", "capability_region_sha256": capability_region["region_sha256"], "system_feasible_region_sha256": system_feasible_region["region_sha256"], "measurement_method": "deterministic_region_membership_classification", "artifact_ref": "capability_region.json;system_feasible_region.json"}, status="validated")
    node("Evidence.V1_5.selection", "evidence", "evidence", {"kind": "deterministic_selection_decision", "selected_point_id": selected_point_id, "selection_sha256": selection_decision["selection_sha256"], "method": selection_decision["method"], "pareto_claimed": False, "measurement_method": "lexicographic_interior_min_cost", "artifact_ref": "selection_decision.json"}, status="validated")
    edge("Evidence.V1_5.sample_set", "operator.VCO_Noise_TF", "supports", {"sample_set_sha256": sample_set_sha256})
    edge("Evidence.V1_5.sample_set", "operator.PLL_Dynamics", "supports", {"sample_set_sha256": sample_set_sha256})
    edge("Evidence.V1_5.system_boundary_map", "Evidence.V1_5.sample_set", "derived_from", {"source_sample_set_sha256": sample_set_sha256})
    edge("Evidence.V1_5.system_boundary_map", "PLL.system_feasible_region", "supports", {"boundary_map_sha256": system_boundary_map["boundary_map_sha256"]})
    edge("Evidence.V1_5.boundary_block_contract", "Evidence.V1_5.system_boundary_map", "derived_from", {"source_boundary_map_sha256": system_boundary_map["boundary_map_sha256"]})
    edge("Evidence.V1_5.boundary_block_contract", "Contract.VCO.boundary_behavior.v1_5", "supports", {"contract_sha256": boundary_block_contract["contract_sha256"], "validation_passed": boundary_block_contract["validation"]["passed"]})
    edge("Contract.VCO.boundary_behavior.v1_5", "Evidence.V1_5.boundary_block_contract", "supported_by", {"contract_sha256": boundary_block_contract["contract_sha256"]})
    edge("Evidence.V1_5.conditional_block_spec_map", "Evidence.V1_5.boundary_block_contract", "derived_from", {"source_contract_sha256": boundary_block_contract["contract_sha256"]})
    edge("Evidence.V1_5.conditional_block_spec_map", "VCORequirement.conditional_phase_noise", "supports", {"block_spec_map_sha256": conditional_block_spec_map["block_spec_map_sha256"]})
    edge("VCORequirement.conditional_phase_noise", "Evidence.V1_5.conditional_block_spec_map", "supported_by", {"block_spec_map_sha256": conditional_block_spec_map["block_spec_map_sha256"]})
    edge("Evidence.V1_5.conditional_candidate_validation", "Evidence.V1_5.conditional_block_spec_map", "derived_from", {"source_block_spec_map_sha256": conditional_block_spec_map["block_spec_map_sha256"]})
    edge("Evidence.V1_5.conditional_candidate_validation", "VCORequirement.conditional_phase_noise", "verifies_requirement", {"passed": conditional_candidate_validation["validation"]["passed"]})
    edge("Evidence.V1_5.conditional_contract_prediction", "Evidence.V1_5.conditional_candidate_validation", "derived_from", {"source_validation_sha256": conditional_candidate_validation["validation_sha256"]})
    edge("Evidence.V1_5.conditional_contract_prediction", "VCORequirement.conditional_phase_noise", "verifies_requirement", {"passed": conditional_contract_prediction["validation"]["passed"]})
    edge("Evidence.V1_5.regions", "VCO.capability_region", "supports", {"region_sha256": capability_region["region_sha256"]})
    edge("Evidence.V1_5.regions", "PLL.system_feasible_region", "supports", {"region_sha256": system_feasible_region["region_sha256"]})
    edge("Evidence.V1_5.selection", "Evidence.V1_5.sample_set", "derived_from", {"selection_sha256": selection_decision["selection_sha256"]})

    # Factorization upgrade: these are additional canonical nodes and typed
    # links.  The legacy pairwise influence/allocation edges above remain the
    # compatibility and human-readable query path.
    allocated_condition_values = [
        float(entry["condition"]["value"])
        for entry in conditional_block_spec_map.get("entries", [])
    ]
    unallocated_condition_values = [
        float(entry["condition"]["value"])
        for entry in conditional_block_spec_map.get("unallocated_slices", [])
    ]
    factor_context_id = "Context.VCO.contract.v1_5"
    add_factor_to_graph(
        graph,
        Factor(
            factor_id="pll_jitter_response",
            factor_type="system_response",
            name="PLL_JITTER_RESPONSE_FACTOR",
            input_refs=(
                "VCO.pn_anchor_1mhz",
                "VCO.k1_hz_per_v",
                factor_context_id,
            ),
            output_refs=("PLL.integrated_jitter",),
            relation_kind="joint_system_response",
            model_kind="deterministic_behavioral_response",
            model_ref="averaged_cppll_v1",
            artifact_ref="sampled_points.jsonl",
            validity_domain={
                "context_id": context_contract["context_id"],
                "condition_axis": "k1_hz_per_v",
                "interpolation_allowed": False,
            },
            context_refs=(factor_context_id,),
            evidence_refs=("Evidence.V1_5.sample_set",),
            uncertainty={"status": "not_modeled", "claim": "verified sampled response"},
            verification_status="validated",
            source_run_ids=(case_id,),
            artifact_hashes={"sample_set_sha256": sample_set_sha256},
            metadata={"joint_dependency": True},
        ),
        status="validated",
    )
    add_factor_to_graph(
        graph,
        Factor(
            factor_id="conditional_pn_allocation",
            factor_type="allocation",
            name="PN_CONDITIONAL_ALLOCATION_FACTOR",
            input_refs=(
                "SystemSpec.integrated_jitter",
                "SystemSpec.lock_time",
                "SystemSpec.output_frequency",
                "SystemSpec.power",
                "VCO.k1_hz_per_v",
                factor_context_id,
            ),
            output_refs=("VCORequirement.conditional_phase_noise",),
            relation_kind="conditional_allocation",
            model_kind="discrete_conditional_map",
            model_ref="conditional_block_spec_map",
            artifact_ref="conditional_block_spec_map.json",
            validity_domain={
                "context_id": context_contract["context_id"],
                "condition_axis": dict(conditional_block_spec_map["condition_axis"]),
                "validated_condition_values": allocated_condition_values,
                "unallocated_condition_values": unallocated_condition_values,
                "interpolation_allowed": False,
            },
            context_refs=(factor_context_id,),
            evidence_refs=(
                "Evidence.V1_5.system_boundary_map",
                "Evidence.V1_5.boundary_block_contract",
                "Evidence.V1_5.conditional_block_spec_map",
                "Evidence.V1_5.conditional_candidate_validation",
                "Evidence.V1_5.conditional_contract_prediction",
            ),
            uncertainty={
                "status": "not_modeled",
                "claim": "discrete table only; no interpolation",
            },
            verification_status="validated",
            source_run_ids=(case_id,),
            artifact_hashes={
                "system_boundary_map_sha256": system_boundary_map["boundary_map_sha256"],
                "boundary_block_contract_sha256": boundary_block_contract["contract_sha256"],
                "conditional_block_spec_map_sha256": conditional_block_spec_map["block_spec_map_sha256"],
                "conditional_candidate_validation_sha256": conditional_candidate_validation["validation_sha256"],
                "conditional_contract_prediction_sha256": conditional_contract_prediction["prediction_sha256"],
            },
            metadata={
                "engineering_margin": dict(conditional_block_spec_map["engineering_margin"]),
                "invalid_slices_remain_unallocated": True,
            },
        ),
        status="validated",
    )

    for record in records:
        point_id = str(record["point_id"])
        candidate_id = f"Candidate.{point_id}"
        instance_id = f"Instance.{point_id}"
        block_id = f"BlockTB.{point_id}"
        system_id = f"SystemTB.{point_id}"
        actual_context_id = f"Context.SystemTB.{point_id}"
        selected = point_id == selected_point_id
        candidate_status = "validated" if selected else "tested"
        design_values = dict(record["design_vector"]["values"])

        node(candidate_id, "candidate", None, {"parameter_identity": "candidate", "point_id": point_id, "ordinal": record["ordinal"], "design_vector": design_values, "selected": selected}, owner="VCO", status=candidate_status)
        node(instance_id, "realized_instance", None, {"parameter_identity": "realized_instance", "source_point_id": point_id, "parameters": record["realized_instance"]["parameters"], "model_ref": record["realized_instance"]["model"]}, owner="VCO", status=candidate_status)
        for knob_name, knob_value in sorted(design_values.items()):
            knob_id = f"Knob.{point_id}.{knob_name}"
            node(knob_id, "candidate_knob", None, {"parameter_identity": "candidate_knob", "point_id": point_id, "knob_name": knob_name, "value": knob_value}, owner="VCO", status=candidate_status)
            edge(candidate_id, knob_id, "contains", {"point_id": point_id, "knob_name": knob_name}, status=candidate_status)

        block_passed = bool(record["block_tb"]["passed"])
        system_passed = bool(record["system_tb"]["passed"])
        context_passed = bool(record["context_coverage"]["passed"])
        node(block_id, "evaluation", "evidence", {"result_identity": "measured_result", "point_id": point_id, "realized_instance_id": instance_id, "passed": block_passed, "checks": record["block_tb"]["checks"], "residuals": record["block_tb"]["residuals"], "behavior_vector": record["behavior_vector"], "context": record["block_tb"]["context"], "measurement_method": record["block_tb"]["measurement_method"], "artifact_ref": f"sampled_points.jsonl#point_id={point_id}"}, status="validated" if block_passed else "rejected")
        node(system_id, "evaluation", "evidence", {"result_identity": "measured_result", "point_id": point_id, "realized_instance_id": instance_id, "passed": system_passed, "checks": record["system_tb"]["checks"], "metrics": record["system_tb"]["metrics"], "residuals": record["system_tb"]["residuals"], "context": record["system_tb"]["context"], "measurement_method": record["system_tb"]["measurement_method"], "artifact_ref": f"sampled_points.jsonl#point_id={point_id}"}, status="validated" if system_passed else "rejected")
        node(actual_context_id, "context", "evidence", {**dict(record["system_tb"]["context"]), "coverage": record["context_coverage"]}, status="validated" if context_passed else "rejected")

        edge(candidate_id, instance_id, "realizes", {"point_id": point_id, "model_ref": record["realized_instance"]["model"]}, status=candidate_status)
        edge(instance_id, block_id, "evaluates", {"passed": block_passed}, status="validated" if block_passed else "rejected")
        edge(instance_id, system_id, "evaluates", {"passed": system_passed}, status="validated" if system_passed else "rejected")
        edge(instance_id, block_id, "validated_by", {"passed": block_passed, "test": "V1.5 BlockTB"}, status="validated" if block_passed else "rejected")
        edge(instance_id, system_id, "validated_by", {"passed": system_passed, "test": "V1.5 SystemTB"}, status="validated" if system_passed else "rejected")
        edge(candidate_id, "VCO.design_space", "candidate_of", {"point_id": point_id}, status="tested")
        edge("VCO.design_space", candidate_id, "provides", {"relationship": "sampled_candidate"}, status="tested")
        if point_id in capability_ids:
            edge(candidate_id, "VCO.capability_region", "candidate_of", {"point_id": point_id}, status="validated")
            edge("VCO.capability_region", candidate_id, "provides", {"relationship": "BlockTB_pass_member"}, status="validated")
        if point_id in system_feasible_ids:
            edge(candidate_id, "PLL.system_feasible_region", "candidate_of", {"point_id": point_id}, status="validated")
            edge("PLL.system_feasible_region", candidate_id, "provides", {"relationship": "jointly_feasible_member"}, status="validated")

        edge(block_id, "Context.VCO.contract.v1_5", "uses_context", {"source": "frozen_before_search"})
        edge(system_id, actual_context_id, "uses_context", {"source": "actual_simulated_context"})
        edge("Context.VCO.contract.v1_5", actual_context_id, "covers", {"passed": context_passed, "checks": record["context_coverage"]["checks"]}, status="validated" if context_passed else "rejected")
        for requirement_id, passed in _requirement_verdicts(record["system_tb"]["checks"]).items():
            edge(system_id, requirement_id, "verifies_requirement", {"passed": passed}, status="validated" if passed else "rejected")

    for validation_entry in conditional_candidate_validation["entries"]:
        validated_point_id = str(
            validation_entry["selected_validation_candidate"]["point_id"]
        )
        edge(f"Candidate.{validated_point_id}", "Evidence.V1_5.conditional_candidate_validation", "validated_by", {"passed": validation_entry["passed"], "condition": validation_entry["condition"]}, status="validated" if validation_entry["passed"] else "rejected")

    selected_candidate_id = f"Candidate.{selected_point_id}"
    selected_instance_id = f"Instance.{selected_point_id}"
    node("Candidate.selected", "candidate", None, {"point_id": selected_point_id, "candidate_id": selection_decision["selected_candidate"]["candidate_id"], "selection_basis": selection_decision["method"], "selection_sha256": selection_decision["selection_sha256"]}, owner="VCO", status="validated")
    edge(selected_candidate_id, "Candidate.selected", "selected_for", {"point_id": selected_point_id})
    edge("Candidate.selected", selected_instance_id, "realizes", {"point_id": selected_point_id})
    edge("Evidence.V1_5.selection", "Candidate.selected", "supports", {"selection_sha256": selection_decision["selection_sha256"]})

    replay_passed = bool(
        replay_evidence["identical_to_sampled_evaluation"]
        and replay_evidence["replay_jointly_feasible"]
    )
    replay_record = replay_evidence["replay_record"]
    node("Evidence.V1_5.selected_replay", "evaluation", "evidence", {"result_identity": "independent_replay", "point_id": selected_point_id, "passed": replay_passed, "comparisons": replay_evidence["comparisons"], "metrics": replay_record["system_tb"]["metrics"], "residuals": replay_record["system_tb"]["residuals"], "checks": replay_record["system_tb"]["checks"], "replay_sha256": replay_evidence["replay_sha256"], "measurement_method": "independent_recompile_BlockTB_SystemTB_replay", "artifact_ref": "selected_candidate_replay.json"}, status="validated" if replay_passed else "rejected")
    node("SystemSpec.verdict", "evaluation", "evidence", {"passed": replay_passed, "checks": _requirement_verdicts(replay_record["system_tb"]["checks"]), "residuals": replay_record["system_tb"]["residuals"], "source": "independent_selected_candidate_replay", "measurement_method": "requirement_verdict_from_independent_replay"}, status="validated" if replay_passed else "rejected")
    edge(selected_instance_id, "Evidence.V1_5.selected_replay", "evaluates", {"passed": replay_passed, "independent_replay": True}, status="validated" if replay_passed else "rejected")
    edge("Evidence.V1_5.selection", "Evidence.V1_5.selected_replay", "supported_by", {"passed": replay_passed}, status="validated" if replay_passed else "rejected")
    edge("Evidence.V1_5.selected_replay", "SystemSpec.verdict", "yields_verdict", {"passed": replay_passed}, status="validated" if replay_passed else "rejected")
    for requirement_id, passed in _requirement_verdicts(replay_record["system_tb"]["checks"]).items():
        edge("Evidence.V1_5.selected_replay", requirement_id, "verifies_requirement", {"passed": passed}, status="validated" if passed else "rejected")
        edge("SystemSpec.verdict", requirement_id, "verifies_requirement", {"passed": passed}, status="validated" if passed else "rejected")

    graph.validate()
    artifact = graph.to_dict()
    validate_graph_v2_artifact(artifact)
    return artifact


__all__ = ["build_v15_graph_artifact"]
