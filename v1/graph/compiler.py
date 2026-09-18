"""Compile current V1 outputs into replayable Graph v1 and Graph v2 evidence."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .model import TypedGraph
from .validators import validate_graph_v2_artifact
from ..schema.block_schema import build_vco_block_meta_v1


SYSTEM_REQUIREMENT_CHECKS = {
    "SystemSpec.integrated_jitter": ("integrated_jitter",),
    "SystemSpec.lock_time": ("lock_time", "locked"),
    "SystemSpec.output_frequency": ("output_frequency",),
    "SystemSpec.power": ("power",),
}


def _evaluation_checks(evaluation: Mapping[str, Any]) -> dict[str, bool]:
    """Normalize per-context SystemTB checks into one deterministic verdict."""

    contexts = list(evaluation.get("per_context", []))
    if contexts:
        return {
            name: all(bool(context.get("checks", {}).get(name, False)) for context in contexts)
            for name in ("integrated_jitter", "lock_time", "output_frequency", "power", "locked")
        }
    return {
        str(name): bool(passed)
        for name, passed in evaluation.get("checks", {}).items()
    }


def _requirement_verdicts(checks: Mapping[str, bool]) -> dict[str, bool]:
    return {
        requirement_id: all(bool(checks.get(check, False)) for check in check_names)
        for requirement_id, check_names in SYSTEM_REQUIREMENT_CHECKS.items()
    }


def _validated_domain_from_context(
    context_contract: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if context_contract is None:
        return {
            "temperature_c": [25.0],
            "validation_source": "v1_observation_holdout",
        }
    return {
        "vctrl_v": [
            float(context_contract["vctrl_min_v"]),
            float(context_contract["vctrl_max_v"]),
        ],
        "temperature_c": [
            float(value) for value in context_contract["temperature_points_c"]
        ],
        "vdd_v": [float(context_contract["vdd_v"])],
        "validation_source": str(
            context_contract.get("context_id", "VCOBlockContext.v1")
        ),
    }


def build_v1_graph_artifact(
    *,
    contract: Mapping[str, Any],
    sensitivity: Mapping[str, Any],
    system_spec: Mapping[str, Any],
    run_id: str,
) -> dict[str, Any]:
    """Build architecture, dependency, influence and validation edges.

    The graph is intentionally compiled from current deterministic artifacts;
    it does not invent sensitivity values or claim a dependency is validated
    without evidence from the existing pipeline.
    """

    graph = TypedGraph(graph_id=f"{run_id}:vco_pll_graph")
    graph.add_node("PLL", "architecture_block", {"architecture": "integer_n_cppll"})
    graph.add_node("VCO", "architecture_block", {"target_block": True})
    graph.add_node("VCO.vctrl", "context", {"unit": "V"})
    graph.add_node("VCO.temperature", "context", {"unit": "degC"})
    graph.add_node("VCO.phase_noise_1mhz", "behavioral_output", {"unit": "dBc/Hz"})
    graph.add_node("VCO.oscillation_frequency", "behavioral_output", {"unit": "Hz"})
    graph.add_node("VCO.kvco", "behavioral_output", {"unit": "Hz/V"})
    graph.add_node("VCO.power", "behavioral_output", {"unit": "W"})
    graph.add_node("PLL.integrated_jitter", "system_metric", {"unit": "s"})
    graph.add_node("PLL.lock_time", "system_metric", {"unit": "s"})
    graph.add_node("PLL.output_frequency", "system_metric", {"unit": "Hz"})
    graph.add_node("PLL.power", "system_metric", {"unit": "W"})
    graph.add_node("SystemSpec.integrated_jitter", "system_requirement")
    graph.add_node("SystemSpec.lock_time", "system_requirement")
    graph.add_node("SystemSpec.output_frequency", "system_requirement")
    graph.add_node("SystemSpec.power", "system_requirement")

    graph.add_edge("VCO", "PLL", "signal_flow", {"signal": "oscillation"})
    graph.add_edge("PLL", "VCO.vctrl", "feedback", {"signal": "control_voltage"})
    graph.add_edge("VCO.vctrl", "VCO.oscillation_frequency", "behavioral_dependency")
    graph.add_edge("VCO.temperature", "VCO.oscillation_frequency", "behavioral_dependency")
    graph.add_edge("VCO.vctrl", "VCO.phase_noise_1mhz", "behavioral_dependency")
    graph.add_edge("VCO.temperature", "VCO.phase_noise_1mhz", "behavioral_dependency")
    graph.add_edge("VCO.vctrl", "VCO.power", "behavioral_dependency")
    graph.add_edge("VCO.temperature", "VCO.power", "behavioral_dependency")
    graph.add_edge("VCO.power", "VCO.phase_noise_1mhz", "behavioral_dependency")
    graph.add_edge("VCO.vctrl", "VCO.kvco", "behavioral_dependency")
    graph.add_edge("VCO.phase_noise_1mhz", "PLL.integrated_jitter", "noise_transfer")
    graph.add_edge("VCO.kvco", "PLL.lock_time", "system_influence")
    graph.add_edge("VCO.kvco", "PLL.integrated_jitter", "system_influence")
    graph.add_edge("VCO.oscillation_frequency", "PLL.output_frequency", "system_influence")
    graph.add_edge("VCO.power", "PLL.power", "system_influence")
    graph.add_edge(
        "SystemSpec.integrated_jitter",
        "PLL.integrated_jitter",
        "constrains",
        {"direction": "upper_bound", "value": system_spec["limits"]["integrated_jitter_max_s"]},
    )
    graph.add_edge(
        "SystemSpec.lock_time",
        "PLL.lock_time",
        "constrains",
        {"direction": "upper_bound", "value": system_spec["limits"]["lock_time_max_s"]},
    )
    graph.add_edge(
        "SystemSpec.output_frequency",
        "PLL.output_frequency",
        "constrains",
        {"direction": "tolerance", "value": system_spec["limits"]["output_frequency_tolerance_hz"]},
    )
    graph.add_edge(
        "SystemSpec.power",
        "PLL.power",
        "constrains",
        {"direction": "upper_bound", "value": system_spec["limits"].get("power_max_w")},
    )

    for parameter, sweep in sensitivity.get("sweeps", {}).items():
        derivatives = sweep.get("local_derivatives", {})
        parameter_node = {
            "pn_anchor_1mhz_dbc_hz": "VCO.phase_noise_1mhz",
            "k1_hz_per_v": "VCO.kvco",
            "vctrl_max_v": "VCO.vctrl",
        }.get(parameter)
        if parameter_node is None:
            continue
        if derivatives.get("integrated_jitter_s") is not None:
            graph.add_edge(
                parameter_node,
                "PLL.integrated_jitter",
                "sensitivity_evidence",
                {
                    "method": "central_finite_difference",
                    "value": derivatives["integrated_jitter_s"],
                    "evidence_id": f"sensitivity:{parameter}:integrated_jitter",
                },
            )
        if derivatives.get("lock_time_s") is not None:
            graph.add_edge(
                parameter_node,
                "PLL.lock_time",
                "sensitivity_evidence",
                {
                    "method": "central_finite_difference",
                    "value": derivatives["lock_time_s"],
                    "evidence_id": f"sensitivity:{parameter}:lock_time",
                },
            )

    for field in contract.get("fields", []):
        name = field.get("name")
        if name == "phase_noise_1mhz":
            graph.add_edge(
                "VCO.vctrl",
                "VCO.phase_noise_1mhz",
                "contract_dependency",
                {"contract_id": contract.get("contract_id"), "status": contract.get("status")},
            )
    graph.validate()
    return graph.to_dict()


def build_v1_graph_v2_artifact(
    *,
    contract: Mapping[str, Any],
    sensitivity: Mapping[str, Any],
    system_spec: Mapping[str, Any],
    run_id: str,
    initial_evaluation: Mapping[str, Any] | None = None,
    boundary: Mapping[str, Any] | None = None,
    recommended_requirement: Mapping[str, Any] | None = None,
    candidate_results: Sequence[Mapping[str, Any]] | None = None,
    final_evaluation: Mapping[str, Any] | None = None,
    block_meta: Mapping[str, Any] | None = None,
    context_contract: Mapping[str, Any] | None = None,
    final_context_coverage: Mapping[str, Any] | None = None,
    rejection: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile an executable graph with frozen semantic roles for V1.

    This is additive to :func:`build_v1_graph_artifact`.  The existing graph
    remains the compatibility artifact; Graph v2 adds explicit requirement,
    capability, operator and evidence nodes without changing any numeric
    calculation in ``v1.pipeline``.
    """

    validated_domain = _validated_domain_from_context(context_contract)
    if block_meta is None:
        block_meta = build_vco_block_meta_v1(
            contract,
            validated_domain=validated_domain,
        )
    graph = TypedGraph(
        graph_id=f"{run_id}:vco_pll_graph_v2",
        graph_version="2.0",
        metadata={
            "schema": "BlockMetaSchema v1 + TypedGraph v2",
            "plane_model": "implementation_metadata_schema_contract_realization_evidence",
            "planes": ["schema", "contract", "realization", "evidence"],
            "semantic_role_model": ["architecture", "behavior", "influence", "evidence"],
            "block_meta_ref": "vco_block_meta_v1.json",
            "execution_model": "architecture_feedback_plus_evaluation_operators",
            "deterministic": True,
            "agent_policy": "propose_only; deterministic_tools_validate",
            "allocation_outcome": "rejected" if rejection is not None else "allocated",
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

    # Architecture: block identity, physical ports, feedback and context.
    node("PLL", "architecture_block", "architecture", {"architecture": "integer_n_cppll"})
    node("VCO", "architecture_block", "architecture", {"target_block": True})
    node("PLL.reference", "port", "architecture", {"direction": "in", "unit": "Hz"}, owner="PLL")
    node("PLL.control_voltage", "port", "architecture", {"direction": "out", "unit": "V"}, owner="PLL")
    node("PLL.oscillation", "port", "architecture", {"direction": "in", "unit": "Hz"}, owner="PLL")
    node("VCO.vctrl", "port", "architecture", {"direction": "in", "unit": "V"}, owner="VCO")
    node("VCO.oscillation", "port", "architecture", {"direction": "out", "unit": "Hz"}, owner="VCO")
    node("Environment.temperature", "context_variable", "architecture", {"unit": "degC"})
    node("Environment.vdd", "context_variable", "architecture", {"unit": "V"})
    edge("VCO", "PLL", "signal_flow", {"signal": "oscillation"})
    edge("PLL", "VCO.vctrl", "feedback", {"signal": "control_voltage"})
    edge("PLL.control_voltage", "VCO.vctrl", "connects_to", {"signal": "control_voltage"})
    edge("VCO.oscillation", "PLL.oscillation", "connects_to", {"signal": "oscillation"})
    edge("Environment.temperature", "VCO", "requires", {"role": "system_context"})
    edge("Environment.vdd", "VCO", "requires", {"role": "system_context"})

    # Behavior: actual block metrics under context.
    node("VCO.phase_noise_1mhz", "behavioral_output", "behavior", {"metric_name": "phase_noise_1mhz_dbc_hz", "unit": "dBc/Hz"}, owner="VCO")
    node("VCO.frequency", "behavioral_output", "behavior", {"metric_name": "frequency_hz", "unit": "Hz"}, owner="VCO")
    node("VCO.kvco", "behavioral_output", "behavior", {"metric_name": "kvco_hz_per_v", "unit": "Hz/V"}, owner="VCO")
    node("VCO.power", "behavioral_output", "behavior", {"metric_name": "power_w", "unit": "W"}, owner="VCO")
    node("VCO.pn_anchor_1mhz", "candidate_knob", None, {"parameter_identity": "internal_model_knob", "knob_name": "pn_anchor_1mhz_dbc_hz", "unit": "dBc/Hz"}, owner="VCO")
    node("VCO.f0_hz", "candidate_knob", None, {"parameter_identity": "internal_model_knob", "knob_name": "f0_hz", "unit": "Hz"}, owner="VCO")
    node("VCO.k1_hz_per_v", "candidate_knob", None, {"parameter_identity": "internal_model_knob", "knob_name": "k1_hz_per_v", "unit": "Hz/V"}, owner="VCO")
    node("VCO.nominal_power_w", "candidate_knob", None, {"parameter_identity": "internal_model_knob", "knob_name": "nominal_power_w", "unit": "W"}, owner="VCO")
    # Influence: block behavior to system metric mechanisms/operators.
    node("operator.VCO_Noise_TF", "operator", "influence", {"operator": "vco_noise_transfer", "model_ref": "behavioral_vco_noise_v1"})
    node("operator.Noise_Integration", "operator", "influence", {"operator": "psd_to_integrated_jitter", "aggregation": "quadrature_psd_integral"})
    node("operator.PLL_Dynamics", "operator", "influence", {"operator": "closed_loop_dynamics", "model_ref": "averaged_cppll_v1"})
    node("PLL.integrated_jitter", "system_metric", "influence", {"metric_name": "integrated_jitter_s", "unit": "s"}, owner="PLL")
    node("PLL.lock_time", "system_metric", "influence", {"metric_name": "lock_time_s", "unit": "s"}, owner="PLL")
    node("PLL.output_frequency", "system_metric", "influence", {"metric_name": "output_frequency_hz", "unit": "Hz"}, owner="PLL")
    node("PLL.power", "system_metric", "influence", {"metric_name": "power_w", "unit": "W"}, owner="PLL")
    edge("VCO.vctrl", "VCO.frequency", "behavioral_dependency", {"equation_ref": "frequency_hz(Vctrl,T)"})
    edge("Environment.temperature", "VCO.frequency", "behavioral_dependency", {"equation_ref": "frequency_hz(Vctrl,T)"})
    edge("VCO.f0_hz", "VCO.frequency", "behavioral_dependency", {"mechanism": "sets_nominal_center_frequency"})
    edge("VCO.k1_hz_per_v", "VCO.frequency", "behavioral_dependency", {"mechanism": "parameterizes_linear_tuning_term"})
    edge("VCO.pn_anchor_1mhz", "VCO.phase_noise_1mhz", "behavioral_dependency", {"mechanism": "parameterizes_context_dependent_profile"})
    edge("VCO.vctrl", "VCO.phase_noise_1mhz", "behavioral_dependency", {"equation_ref": "phase_noise_dbc_hz(offset,Vctrl,T,power)"})
    edge("Environment.temperature", "VCO.phase_noise_1mhz", "behavioral_dependency", {"equation_ref": "phase_noise_dbc_hz(offset,Vctrl,T,power)"})
    edge("VCO.power", "VCO.phase_noise_1mhz", "behavioral_dependency", {"equation_ref": "phase_noise_dbc_hz(offset,Vctrl,T,power)"})
    edge("VCO.k1_hz_per_v", "VCO.kvco", "behavioral_dependency", {"mechanism": "parameterizes_nonlinear_tuning_slope"})
    edge("VCO.nominal_power_w", "VCO.power", "behavioral_dependency", {"mechanism": "parameterizes_nominal_block_power"})
    edge("VCO.vctrl", "VCO.kvco", "behavioral_dependency", {"equation_ref": "kvco_hz_per_v(Vctrl)"})
    edge("VCO.vctrl", "VCO.power", "behavioral_dependency", {"equation_ref": "power_w(Vctrl,T)"})
    edge("Environment.temperature", "VCO.power", "behavioral_dependency", {"equation_ref": "power_w(Vctrl,T)"})
    edge("VCO.phase_noise_1mhz", "operator.VCO_Noise_TF", "input_to", {"context_ref": "VCOBlockContext.v1"})
    edge("operator.VCO_Noise_TF", "operator.Noise_Integration", "input_to", {"transfer": "high_pass_locked_loop"})
    edge("operator.Noise_Integration", "PLL.integrated_jitter", "produces", {"equation_ref": "integrated_vco_jitter_s"})
    edge("VCO.phase_noise_1mhz", "PLL.integrated_jitter", "system_influence", {"source_behavior_metric": "phase_noise_1mhz_dbc_hz", "target_system_metric": "integrated_jitter_s", "mechanism": "noise_transfer_and_integration", "evidence_refs": ["Evidence.sensitivity"], "validity_domain": "VCOBlockContext.v1"})
    edge("VCO.kvco", "operator.PLL_Dynamics", "input_to", {"context_ref": "VCOBlockContext.v1"})
    edge("operator.PLL_Dynamics", "PLL.lock_time", "produces", {"equation_ref": "lock_time_from_reference_cycles"})
    edge("VCO.kvco", "PLL.integrated_jitter", "system_influence", {"source_behavior_metric": "kvco_hz_per_v", "target_system_metric": "integrated_jitter_s", "mechanism": "loop_bandwidth_change", "evidence_refs": ["Evidence.sensitivity"], "validity_domain": "VCOBlockContext.v1"})
    edge("VCO.kvco", "PLL.lock_time", "system_influence", {"source_behavior_metric": "kvco_hz_per_v", "target_system_metric": "lock_time_s", "mechanism": "closed_loop_dynamics", "evidence_refs": ["Evidence.sensitivity"], "validity_domain": "VCOBlockContext.v1"})
    edge("VCO.frequency", "PLL.output_frequency", "system_influence", {"source_behavior_metric": "frequency_hz", "target_system_metric": "output_frequency_hz", "mechanism": "divider_feedback"})
    edge("VCO.power", "PLL.power", "system_influence", {"source_behavior_metric": "power_w", "target_system_metric": "power_w", "mechanism": "block_power_aggregation"})

    # Workflow artifacts: requirements, capabilities and candidate instances
    # are objects, not Block Graph semantic roles.
    limits = system_spec.get("limits", {})
    node("SystemSpec.integrated_jitter", "system_requirement", None, {"source": "SystemSpec", "parameter_identity": "requirement", "requirement_id": "SystemSpec.integrated_jitter", "limit": limits.get("integrated_jitter_max_s"), "metric": "PLL.integrated_jitter"})
    node("SystemSpec.lock_time", "system_requirement", None, {"source": "SystemSpec", "parameter_identity": "requirement", "requirement_id": "SystemSpec.lock_time", "limit": limits.get("lock_time_max_s"), "metric": "PLL.lock_time"})
    node("SystemSpec.output_frequency", "system_requirement", None, {"source": "SystemSpec", "parameter_identity": "requirement", "requirement_id": "SystemSpec.output_frequency", "limit": limits.get("output_frequency_tolerance_hz"), "metric": "PLL.output_frequency"})
    node("SystemSpec.power", "system_requirement", None, {"source": "SystemSpec", "parameter_identity": "requirement", "requirement_id": "SystemSpec.power", "limit": limits.get("power_max_w"), "metric": "PLL.power"})
    required_pn = None if boundary is None else boundary.get("block_metric_at_boundary")
    search_knob_boundary = None if boundary is None else boundary.get("search_knob_boundary")
    recommended_pn = None if recommended_requirement is None else recommended_requirement.get("phase_noise_1mhz_max_dbc_hz")
    node("VCORequirement.required", "block_requirement", None, {"source": "boundary_measurement_under_frozen_context", "parameter_identity": "requirement", "requirement_id": "VCORequirement.required", "metric": "phase_noise_1mhz_max_dbc_hz", "measured_metric": "worst_phase_noise_1mhz_dbc_hz", "value": required_pn, "margin_db": 0.0, "search_knob": None if boundary is None else boundary.get("search_knob"), "search_knob_boundary": search_knob_boundary}, status="rejected" if rejection is not None else None)
    node("VCORequirement.recommended", "block_requirement", None, {"source": "measured_boundary_plus_margin", "parameter_identity": "requirement", "requirement_id": "VCORequirement.recommended", "metric": "phase_noise_1mhz_max_dbc_hz", "measured_metric": "worst_phase_noise_1mhz_dbc_hz", "value": recommended_pn, "margin_db": None if recommended_requirement is None else recommended_requirement.get("margin_db")}, status="rejected" if rejection is not None else None)
    node("VCO.design_space", "design_space", None, {"representation": "candidate_knobs", "dimensions": ["pn_anchor_1mhz_dbc_hz", "k1_hz_per_v"], "includes_infeasible": True}, owner="VCO")
    node("VCO.capability_region", "capability_region", None, {"representation": "sampled_feasible_candidates", "dimensions": ["worst_phase_noise_1mhz_dbc_hz", "kvco_min_hz_per_v", "kvco_max_hz_per_v", "worst_power_w", "frequency_min_hz", "frequency_max_hz"], "formal_status": "sampled_partial_one_dimensional", "status_note": "V1 capability points require BlockTB PASS; this is not a complete PN-by-Kvco region"}, owner="VCO")
    edge("SystemSpec.integrated_jitter", "PLL.integrated_jitter", "constrains", {"direction": "upper_bound", "value": limits.get("integrated_jitter_max_s")})
    edge("SystemSpec.lock_time", "PLL.lock_time", "constrains", {"direction": "upper_bound", "value": limits.get("lock_time_max_s")})
    edge("SystemSpec.output_frequency", "PLL.output_frequency", "constrains", {"direction": "tolerance", "value": limits.get("output_frequency_tolerance_hz")})
    edge("SystemSpec.power", "PLL.power", "constrains", {"direction": "upper_bound", "value": limits.get("power_max_w")})
    if rejection is None:
        edge("SystemSpec.integrated_jitter", "VCORequirement.required", "allocates", {"target_system_metric": "integrated_jitter_s", "search_knob": "pn_anchor_1mhz_dbc_hz", "allocated_block_metric": "worst_phase_noise_1mhz_dbc_hz", "method": "bracketed_bisection_then_frozen_context_measurement", "evidence_id": "Evidence.boundary_search"})
        edge("VCORequirement.required", "VCORequirement.recommended", "derived_from", {"margin_db": None if recommended_requirement is None else recommended_requirement.get("margin_db")})
        edge("VCORequirement.recommended", "VCO.capability_region", "constrains", {"metric": "worst_phase_noise_1mhz_dbc_hz"})

    if context_contract is not None:
        node("Context.VCO.contract", "context", "architecture", dict(context_contract), owner="VCO", status="validated")

    candidate_results = list(candidate_results or [])
    for item in candidate_results:
        candidate_id = str(item.get("candidate_id", "unknown"))
        candidate_node = f"Candidate.{candidate_id}"
        instance_node = f"Instance.{candidate_id}"
        block_tb = item.get("block_tb", {})
        system_eval = item.get("system_evaluation", {})
        coverage = item.get("context_coverage", {})
        system_checks = _evaluation_checks(system_eval)
        system_verdicts = _requirement_verdicts(system_checks)
        design_vector = dict(item.get("design_vector", {}))
        realized_parameters = dict(item.get("realized_parameters", {}))
        candidate_status = "validated" if item.get("selected") else "tested"
        node(candidate_node, "candidate", None, {"parameter_identity": "candidate", "candidate_id": candidate_id, "engineering_cost": item.get("engineering_cost"), "description": item.get("description", ""), "candidate_knobs": design_vector, "design_vector": design_vector, "selected": bool(item.get("selected"))}, owner="VCO", status=candidate_status)
        node(instance_node, "realized_instance", None, {"parameter_identity": "realized_instance", "source_candidate_id": candidate_id, "behavioral_variables": realized_parameters, "parameters": realized_parameters, "model_ref": "synthetic_behavioral_vco_v1"}, owner="VCO", status=candidate_status)
        for knob_name, knob_value in sorted(design_vector.items()):
            knob_node = f"Knob.{candidate_id}.{knob_name}"
            node(knob_node, "candidate_knob", None, {"parameter_identity": "candidate_knob", "knob_name": knob_name, "value": knob_value, "candidate_id": candidate_id}, owner="VCO", status=candidate_status)
            edge(candidate_node, knob_node, "contains", {"candidate_id": candidate_id, "knob_name": knob_name}, status=candidate_status)
        node(f"BlockTB.{candidate_id}", "evaluation", "evidence", {"result_identity": "measured_result", "candidate_id": candidate_id, "passed": block_tb.get("passed"), "requirement": block_tb.get("requirement"), "context": block_tb.get("context"), "checks": block_tb.get("checks"), "worst_case": block_tb.get("worst_case"), "measurement_method": block_tb.get("measurement_method"), "provenance": block_tb.get("provenance"), "evaluation_kind": "context_aware_block_tb", "artifact_ref": f"block_feasibility.json#candidate_id={candidate_id}", "evidence_validated": True}, status="validated" if block_tb.get("passed") else "rejected")
        node(f"SystemTB.{candidate_id}", "evaluation", "evidence", {"result_identity": "measured_result", "candidate_id": candidate_id, "passed": system_eval.get("passed"), "metrics": system_eval.get("metrics"), "residuals": system_eval.get("residuals"), "context": system_eval.get("context"), "checks": system_checks, "measurement_method": "evaluate_system", "evaluation_kind": "realized_instance_system_tb", "artifact_ref": f"block_feasibility.json#candidate_id={candidate_id}", "evidence_validated": True}, status="validated" if system_eval.get("passed") else "rejected")
        edge(candidate_node, instance_node, "realizes", {"model_ref": "synthetic_behavioral_vco_v1"})
        edge(instance_node, f"BlockTB.{candidate_id}", "evaluates", {"passed": block_tb.get("passed")}, status="validated" if block_tb.get("passed") else "rejected")
        edge(instance_node, f"SystemTB.{candidate_id}", "evaluates", {"passed": system_eval.get("passed")}, status="validated" if system_eval.get("passed") else "rejected")
        edge(candidate_node, "VCO.design_space", "candidate_of", {"candidate_id": candidate_id}, status="tested")
        edge("VCO.design_space", candidate_node, "provides", {"relationship": "sampled_candidate"}, status="tested")
        if block_tb.get("passed"):
            edge(candidate_node, "VCO.capability_region", "candidate_of", {"candidate_id": candidate_id}, status="validated")
            edge("VCO.capability_region", candidate_node, "provides", {"relationship": "verified_feasible_candidate"}, status="validated")
        edge(instance_node, f"BlockTB.{candidate_id}", "validated_by", {"test": "validate_vco_spec", "passed": block_tb.get("passed")}, status="validated" if block_tb.get("passed") else "rejected")
        edge(instance_node, f"SystemTB.{candidate_id}", "validated_by", {"test": "evaluate_system", "passed": system_eval.get("passed")}, status="validated" if system_eval.get("passed") else "rejected")
        if rejection is None:
            edge(f"BlockTB.{candidate_id}", "VCORequirement.recommended", "verifies_requirement", {"passed": block_tb.get("passed"), "checks": block_tb.get("checks", {})}, status="validated" if block_tb.get("passed") else "rejected")
            for requirement_id, passed in system_verdicts.items():
                edge(f"SystemTB.{candidate_id}", requirement_id, "verifies_requirement", {"passed": passed}, status="validated" if passed else "rejected")
        if context_contract is not None:
            actual_node = f"Context.SystemTB.{candidate_id}"
            node(actual_node, "context", "evidence", {**dict(system_eval.get("context", {})), "coverage": dict(coverage)}, status="validated" if coverage.get("passed") else "rejected")
            edge(f"BlockTB.{candidate_id}", "Context.VCO.contract", "uses_context", {"source": "frozen_pre_candidate_contract"})
            edge(f"SystemTB.{candidate_id}", actual_node, "uses_context", {"source": "actual_simulated_context"})
            edge("Context.VCO.contract", actual_node, "covers", {"passed": coverage.get("passed"), "checks": coverage.get("checks", {})}, status="validated" if coverage.get("passed") else "rejected")
        if item.get("selected"):
            node("Candidate.selected", "candidate", None, {"candidate_id": candidate_id, "selection_basis": "feasible_min_engineering_cost"}, status="validated")
            edge(candidate_node, "Candidate.selected", "selected_for", {"candidate_id": candidate_id})
            edge("Candidate.selected", instance_node, "realizes", {"candidate_id": candidate_id})

    # Evidence and supporting workflow objects.
    node("Schema.BlockMeta.VCO", "schema_definition", None, {"parameter_identity": "schema_rule", "schema_version": block_meta.get("schema_version"), "object_type": block_meta.get("object_type"), "block_id": block_meta.get("block_id"), "contract_sections": ["architecture", "behavior", "influence", "evidence"]}, owner="VCO", status="validated")
    node("Contract.VCO.v1", "contract", None, {"contract_id": contract.get("contract_id"), "status": contract.get("status")}, owner="VCO")
    node("Measurement.VCO.phase_noise_1mhz", "measurement_contract", None, {"metric": "phase_noise_1mhz_dbc_hz", "measured_metric": "worst_phase_noise_1mhz_dbc_hz", "method": "behavioral_psd_evaluation", "offset_hz": 1.0e6, "context_source": "VCOBlockContext.v1"})
    node("Validity.VCO.v1", "validity_domain", None, {"declared_domain": contract.get("validity", {}), "validated_domain": validated_domain, "fidelity": "synthetic_behavioral"}, owner="VCO")
    node("Evidence.sensitivity", "evidence", "evidence", {"kind": "deterministic_sensitivity_suite", "method": sensitivity.get("method"), "source": "v1.pipeline.run_sensitivity_suite", "measurement_method": "deterministic_finite_difference_and_grid_sweep"})
    if rejection is None:
        node("Evidence.boundary_search", "evidence", "evidence", {"kind": "pn_anchor_boundary_search", "search_knob": None if boundary is None else boundary.get("search_knob"), "search_knob_boundary": search_knob_boundary, "target_system_metric": None if boundary is None else boundary.get("target_system_metric"), "target_system_metric_at_boundary": None if boundary is None else boundary.get("target_system_metric_at_boundary"), "block_metric_at_boundary": required_pn, "validity_domain": None if boundary is None else boundary.get("validity_domain"), "iterations": None if boundary is None else boundary.get("iterations"), "measurement_method": "bracketed_bisection_plus_frozen_context_block_measurement", "artifact_ref": "required_vco_spec_boundary.json"})
    else:
        node("Evidence.PN.rejection", "evidence", "evidence", {"kind": "non_pn_constraint_blocks_allocation", "blocking_checks": rejection.get("blocking_checks", []), "tight_trial": rejection.get("tight_trial"), "reason": rejection.get("allocator_error"), "measurement_method": "tight_bound_systemtb"}, status="validated")
        for check in rejection.get("blocking_checks", []):
            requirement_id = {"lock_time": "SystemSpec.lock_time", "power": "SystemSpec.power", "output_frequency": "SystemSpec.output_frequency", "locked": "SystemSpec.lock_time"}.get(check)
            if requirement_id:
                edge(requirement_id, "Evidence.PN.rejection", "supported_by", {"blocking_check": check})
    if initial_evaluation is not None:
        initial_checks = _evaluation_checks(initial_evaluation)
        initial_verdicts = _requirement_verdicts(initial_checks)
        node("Evidence.SystemTB.initial", "evaluation", "evidence", {"passed": initial_evaluation.get("passed"), "metrics": initial_evaluation.get("metrics"), "residuals": initial_evaluation.get("residuals"), "checks": initial_checks, "context": initial_evaluation.get("context"), "measurement_method": "evaluate_system", "artifact_ref": "initial_system_evaluation.json"}, status="validated" if initial_evaluation.get("passed") else "rejected")
        for requirement_id, passed in initial_verdicts.items():
            edge("Evidence.SystemTB.initial", requirement_id, "verifies_requirement", {"passed": passed, "phase": "initial_system_evaluation"}, status="validated" if passed else "rejected")
    if final_evaluation is not None:
        final_checks = _evaluation_checks(final_evaluation)
        final_verdicts = _requirement_verdicts(final_checks)
        node("Evidence.SystemTB.final", "evaluation", "evidence", {"passed": final_evaluation.get("passed"), "metrics": final_evaluation.get("metrics"), "residuals": final_evaluation.get("residuals"), "checks": final_checks, "context": final_evaluation.get("context"), "measurement_method": "evaluate_system", "evaluation_kind": "independent_final_system_tb", "artifact_ref": "final_system_evaluation.json"}, status="validated" if final_evaluation.get("passed") else "rejected")
        node("SystemSpec.verdict", "evaluation", "evidence", {"passed": final_evaluation.get("passed"), "checks": final_verdicts, "residuals": final_evaluation.get("residuals"), "source": "independent_final_system_tb", "measurement_method": "requirement_verdict_from_systemtb"}, status="validated" if final_evaluation.get("passed") else "rejected")
        edge("Evidence.SystemTB.final", "SystemSpec.verdict", "yields_verdict", {"passed": final_evaluation.get("passed")}, status="validated" if final_evaluation.get("passed") else "rejected")
        for requirement_id, passed in final_verdicts.items():
            edge("SystemSpec.verdict", requirement_id, "verifies_requirement", {"passed": passed}, status="validated" if passed else "rejected")
        if candidate_results:
            selected_item = next((item for item in candidate_results if item.get("selected")), None)
            if selected_item is not None:
                cid = str(selected_item["candidate_id"])
                edge(f"Instance.{cid}", "Evidence.SystemTB.final", "evaluates", {"passed": final_evaluation.get("passed"), "independent_rerun": True, "artifact_ref": "final_system_evaluation.json"}, status="validated" if final_evaluation.get("passed") else "rejected")
                if context_contract is not None:
                    final_coverage = dict(final_context_coverage or {})
                    coverage_passed = final_coverage.get("passed")
                    node("Context.SystemTB.final", "context", "evidence", {**dict(final_evaluation.get("context", {})), "coverage": final_coverage}, status="validated" if coverage_passed else "rejected")
                    edge("Evidence.SystemTB.final", "Context.SystemTB.final", "uses_context")
                    edge("Context.VCO.contract", "Context.SystemTB.final", "covers", {"passed": coverage_passed, "checks": final_coverage.get("checks", {})}, status="validated" if coverage_passed else "rejected")
    edge("VCO.phase_noise_1mhz", "Measurement.VCO.phase_noise_1mhz", "measured_by", {"context_source": "SystemTB operating envelope"})
    edge("VCO", "Schema.BlockMeta.VCO", "contains", {"schema_version": block_meta.get("schema_version")})
    edge("Schema.BlockMeta.VCO", "Contract.VCO.v1", "derived_from", {"contract_id": contract.get("contract_id")})
    edge("Contract.VCO.v1", "Measurement.VCO.phase_noise_1mhz", "supported_by", {"contract_id": contract.get("contract_id")})
    edge("Contract.VCO.v1", "Validity.VCO.v1", "valid_in", {"status": contract.get("status")})
    edge("Evidence.sensitivity", "operator.VCO_Noise_TF", "supports", {"evidence_ids": sorted(sensitivity.get("sweeps", {}).keys())})
    if rejection is None:
        edge("VCORequirement.required", "Evidence.boundary_search", "derived_from", {"method": "bracketed_bisection"})
        edge("VCORequirement.recommended", "Evidence.boundary_search", "derived_from", {"margin_db": None if recommended_requirement is None else recommended_requirement.get("margin_db")})

    for parameter, sweep in sensitivity.get("sweeps", {}).items():
        source = {
            "pn_anchor_1mhz_dbc_hz": "VCO.pn_anchor_1mhz",
            "k1_hz_per_v": "VCO.k1_hz_per_v",
            "vctrl_max_v": "VCO.vctrl",
            "nominal_power_w": "VCO.nominal_power_w",
        }.get(parameter)
        if source is None:
            continue
        derivatives = sweep.get("local_derivatives", {})
        rows = list(sweep.get("rows", []))
        for metric, target in (
            ("integrated_jitter_s", "PLL.integrated_jitter"),
            ("lock_time_s", "PLL.lock_time"),
            ("power_w", "PLL.power"),
        ):
            if derivatives.get(metric) is not None:
                metric_values = [
                    float(row[metric])
                    for row in rows
                    if row.get(metric) is not None
                ]
                observed_span = (
                    max(metric_values) - min(metric_values)
                    if metric_values
                    else None
                )
                scale = max((abs(value) for value in metric_values), default=0.0)
                active = observed_span is not None and observed_span > max(1.0e-30, scale * 1.0e-12)
                edge(
                    source,
                    target,
                    "sensitivity_evidence",
                    {
                        "method": "central_finite_difference",
                        "value": derivatives[metric],
                        "observed_metric_span": observed_span,
                        "active_in_sweep": active,
                        "evidence_id": "Evidence.sensitivity",
                        "evidence_ref": f"sensitivity.json#sweeps.{parameter}.local_derivatives.{metric}",
                    },
                )

    graph.validate()
    artifact = graph.to_dict()
    validate_graph_v2_artifact(artifact)
    return artifact
