"""Compile current V1 outputs into replayable Graph v1 and Graph v2 evidence."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .model import TypedGraph
from .validators import validate_graph_v2_artifact
from ..schema.block_schema import build_vco_block_meta_v1


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
            "pn_1mhz_dbc_hz": "VCO.phase_noise_1mhz",
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
) -> dict[str, Any]:
    """Compile an executable, four-layer graph for the current V1 instance.

    This is additive to :func:`build_v1_graph_artifact`.  The existing graph
    remains the compatibility artifact; Graph v2 adds explicit requirement,
    capability, operator and verification nodes without changing any numeric
    calculation in ``v1.pipeline``.
    """

    if block_meta is None:
        block_meta = build_vco_block_meta_v1(contract)
    graph = TypedGraph(
        graph_id=f"{run_id}:vco_pll_graph_v2",
        graph_version="2.0",
        metadata={
            "schema": "BlockMetaSchema v1 + TypedGraph v2",
            "block_meta_ref": "vco_block_meta_v1.json",
            "execution_model": "architecture_feedback_plus_evaluation_operators",
            "deterministic": True,
            "agent_policy": "propose_only; deterministic_tools_validate",
        },
    )

    def node(
        node_id: str,
        node_type: str,
        layer: str,
        properties: Mapping[str, Any] | None = None,
        *,
        owner: str | None = None,
        status: str | None = None,
    ) -> None:
        graph.add_node(
            node_id,
            node_type,
            properties,
            layer=layer,
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

    # Interface layer: architecture, ports, contexts and interactions.
    node("PLL", "architecture_block", "interface", {"architecture": "integer_n_cppll"})
    node("VCO", "architecture_block", "interface", {"target_block": True})
    node("PLL.reference", "port", "interface", {"direction": "in", "unit": "Hz"}, owner="PLL")
    node("PLL.control_voltage", "port", "interface", {"direction": "out", "unit": "V"}, owner="PLL")
    node("PLL.oscillation", "port", "interface", {"direction": "in", "unit": "Hz"}, owner="PLL")
    node("VCO.vctrl", "port", "interface", {"direction": "in", "unit": "V"}, owner="VCO")
    node("VCO.oscillation", "port", "interface", {"direction": "out", "unit": "Hz"}, owner="VCO")
    node("VCO.phase_noise_profile", "port", "interface", {"direction": "out", "unit": "dBc/Hz"}, owner="VCO")
    node("VCO.Kvco", "port", "interface", {"direction": "out", "unit": "Hz/V"}, owner="VCO")
    node("Environment.temperature", "context_variable", "interface", {"unit": "degC"})
    node("Environment.vdd", "context_variable", "interface", {"unit": "V"})
    edge("VCO", "PLL", "signal_flow", {"signal": "oscillation"})
    edge("PLL", "VCO.vctrl", "feedback", {"signal": "control_voltage"})
    edge("PLL.control_voltage", "VCO.vctrl", "connects_to", {"signal": "control_voltage"})
    edge("VCO.oscillation", "PLL.oscillation", "connects_to", {"signal": "oscillation"})
    edge("Environment.temperature", "VCO", "requires", {"role": "system_context"})
    edge("Environment.vdd", "VCO", "requires", {"role": "system_context"})

    # Behavior layer: explicit operators separate the physical mechanism from
    # the architecture feedback loop, making the evaluation path acyclic.
    node("VCO.phase_noise_1mhz", "behavioral_output", "behavior", {"unit": "dBc/Hz"}, owner="VCO")
    node("VCO.frequency", "behavioral_output", "behavior", {"unit": "Hz"}, owner="VCO")
    node("VCO.kvco", "behavioral_output", "behavior", {"unit": "Hz/V"}, owner="VCO")
    node("VCO.power", "behavioral_output", "behavior", {"unit": "W"}, owner="VCO")
    node("VCO.phase_noise_1mhz_design", "design_variable", "behavior", {"unit": "dBc/Hz"}, owner="VCO")
    node("VCO.k1_design", "design_variable", "behavior", {"unit": "Hz/V"}, owner="VCO")
    node("operator.VCO_Noise_TF", "operator", "behavior", {"operator": "vco_noise_transfer", "model_ref": "behavioral_vco_noise_v1"})
    node("operator.Noise_Integration", "operator", "behavior", {"operator": "psd_to_integrated_jitter", "aggregation": "quadrature_psd_integral"})
    node("operator.PLL_Dynamics", "operator", "behavior", {"operator": "closed_loop_dynamics", "model_ref": "averaged_cppll_v1"})
    node("PLL.integrated_jitter", "system_metric", "behavior", {"unit": "s"}, owner="PLL")
    node("PLL.lock_time", "system_metric", "behavior", {"unit": "s"}, owner="PLL")
    node("PLL.output_frequency", "system_metric", "behavior", {"unit": "Hz"}, owner="PLL")
    node("PLL.power", "system_metric", "behavior", {"unit": "W"}, owner="PLL")
    edge("VCO.vctrl", "VCO.frequency", "behavioral_dependency", {"equation_ref": "frequency_hz(Vctrl,T)"})
    edge("Environment.temperature", "VCO.frequency", "behavioral_dependency", {"equation_ref": "frequency_hz(Vctrl,T)"})
    edge("VCO.phase_noise_1mhz_design", "VCO.phase_noise_1mhz", "behavioral_dependency", {"mechanism": "parameterizes_context_dependent_profile"})
    edge("VCO.vctrl", "VCO.phase_noise_1mhz", "behavioral_dependency", {"equation_ref": "phase_noise_dbc_hz(offset,Vctrl,T,power)"})
    edge("Environment.temperature", "VCO.phase_noise_1mhz", "behavioral_dependency", {"equation_ref": "phase_noise_dbc_hz(offset,Vctrl,T,power)"})
    edge("VCO.phase_noise_1mhz", "VCO.phase_noise_profile", "provides", {"relationship": "1MHz anchor parameterizes profile"})
    edge("VCO.k1_design", "VCO.kvco", "behavioral_dependency", {"mechanism": "parameterizes_nonlinear_tuning_slope"})
    edge("VCO.vctrl", "VCO.kvco", "behavioral_dependency", {"equation_ref": "kvco_hz_per_v(Vctrl)"})
    edge("VCO.kvco", "VCO.Kvco", "provides", {"relationship": "realized interaction value"})
    edge("VCO.phase_noise_profile", "operator.VCO_Noise_TF", "input_to", {"context_ref": "SystemTB.operating_envelope"})
    edge("operator.VCO_Noise_TF", "operator.Noise_Integration", "input_to", {"transfer": "high_pass_locked_loop"})
    edge("operator.Noise_Integration", "PLL.integrated_jitter", "produces", {"equation_ref": "integrated_vco_jitter_s"})
    edge("VCO.phase_noise_1mhz", "PLL.integrated_jitter", "shortcut", {"derived_from": ["operator.VCO_Noise_TF", "operator.Noise_Integration"], "query_only": True})
    edge("VCO.Kvco", "operator.PLL_Dynamics", "input_to", {"context_ref": "SystemTB.operating_envelope"})
    edge("operator.PLL_Dynamics", "PLL.lock_time", "produces", {"equation_ref": "lock_time_from_reference_cycles"})
    edge("VCO.frequency", "PLL.output_frequency", "system_influence", {"mechanism": "divider_feedback"})
    edge("VCO.power", "PLL.power", "system_influence", {"mechanism": "block_power_aggregation"})

    # Allocation layer: requirements, capabilities and candidate instances are
    # distinct objects.  Optional run artifacts enrich the properties but are
    # never required to invent a graph edge.
    limits = system_spec.get("limits", {})
    node("SystemSpec.integrated_jitter", "system_requirement", "allocation", {"source": "SystemSpec", "limit": limits.get("integrated_jitter_max_s"), "metric": "PLL.integrated_jitter"})
    node("SystemSpec.lock_time", "system_requirement", "allocation", {"source": "SystemSpec", "limit": limits.get("lock_time_max_s"), "metric": "PLL.lock_time"})
    node("SystemSpec.output_frequency", "system_requirement", "allocation", {"source": "SystemSpec", "limit": limits.get("output_frequency_tolerance_hz"), "metric": "PLL.output_frequency"})
    node("SystemSpec.power", "system_requirement", "allocation", {"source": "SystemSpec", "limit": limits.get("power_max_w"), "metric": "PLL.power"})
    required_pn = None if boundary is None else boundary.get("required_boundary")
    recommended_pn = None if recommended_requirement is None else recommended_requirement.get("phase_noise_1mhz_max_dbc_hz")
    node("VCORequirement.required", "block_requirement", "allocation", {"source": "deterministic_pn_boundary_search", "metric": "phase_noise_1mhz_max_dbc_hz", "value": required_pn, "margin_db": 0.0})
    node("VCORequirement.recommended", "block_requirement", "allocation", {"source": "deterministic_boundary_plus_margin", "metric": "phase_noise_1mhz_max_dbc_hz", "value": recommended_pn, "margin_db": None if recommended_requirement is None else recommended_requirement.get("margin_db")})
    node("VCO.capability_region", "capability_region", "allocation", {"representation": "sampled_feasible_points", "dimensions": ["phase_noise_1mhz_dbc_hz"], "status_note": "V1 formal dimension is one-dimensional"}, owner="VCO")
    edge("SystemSpec.integrated_jitter", "PLL.integrated_jitter", "constrains", {"direction": "upper_bound", "value": limits.get("integrated_jitter_max_s")})
    edge("SystemSpec.lock_time", "PLL.lock_time", "constrains", {"direction": "upper_bound", "value": limits.get("lock_time_max_s")})
    edge("SystemSpec.output_frequency", "PLL.output_frequency", "constrains", {"direction": "tolerance", "value": limits.get("output_frequency_tolerance_hz")})
    edge("SystemSpec.power", "PLL.power", "constrains", {"direction": "upper_bound", "value": limits.get("power_max_w")})
    edge("SystemSpec.integrated_jitter", "VCORequirement.required", "allocates", {"allocation_metric": "phase_noise_1mhz_dbc_hz", "method": "bracketed_bisection", "evidence_id": "allocation:pn_boundary"})
    edge("VCORequirement.required", "VCORequirement.recommended", "derived_from", {"margin_db": None if recommended_requirement is None else recommended_requirement.get("margin_db")})
    edge("VCORequirement.recommended", "VCO.capability_region", "constrains", {"metric": "phase_noise_1mhz_dbc_hz"})

    candidate_results = list(candidate_results or [])
    for item in candidate_results:
        candidate_id = str(item.get("candidate_id", "unknown"))
        candidate_node = f"Candidate.{candidate_id}"
        block_tb = item.get("block_tb", {})
        system_eval = item.get("system_evaluation", {})
        node(candidate_node, "candidate", "allocation", {"engineering_cost": item.get("engineering_cost"), "description": item.get("description", "")})
        node(f"BlockTB.{candidate_id}", "evaluation", "verification", {"passed": block_tb.get("passed"), "context": block_tb.get("context"), "evaluation_kind": "context_aware_block_tb"})
        node(f"SystemTB.{candidate_id}", "evaluation", "verification", {"passed": system_eval.get("passed"), "metrics": system_eval.get("metrics"), "evaluation_kind": "realized_instance_system_tb"})
        edge(candidate_node, "VCO.capability_region", "candidate_of", {"candidate_id": candidate_id})
        edge("VCO.capability_region", candidate_node, "provides", {"relationship": "sampled_candidate"})
        edge(candidate_node, f"BlockTB.{candidate_id}", "validated_by", {"test": "validate_vco_spec", "passed": block_tb.get("passed")}, status="validated" if block_tb.get("passed") is not None else "tested")
        edge(candidate_node, f"SystemTB.{candidate_id}", "validated_by", {"test": "evaluate_system", "passed": system_eval.get("passed")}, status="validated" if system_eval.get("passed") is not None else "tested")
        if item.get("selected"):
            node("Candidate.selected", "realized_instance", "allocation", {"candidate_id": candidate_id, "selection_basis": "feasible_min_engineering_cost"})
            edge(candidate_node, "Candidate.selected", "realizes", {"candidate_id": candidate_id})

    # Verification layer: contracts and evidence link mechanisms to the
    # deterministic artifacts which support their current status.
    node("Schema.BlockMeta.VCO", "contract", "verification", {"schema_version": block_meta.get("schema_version"), "object_type": block_meta.get("object_type"), "block_id": block_meta.get("block_id"), "contract_sections": ["interface_contract", "behavior_contract", "capability_contract", "verification_contract"]}, owner="VCO", status="validated")
    node("Contract.VCO.v1", "contract", "verification", {"contract_id": contract.get("contract_id"), "status": contract.get("status")}, owner="VCO")
    node("Measurement.VCO.phase_noise_1mhz", "measurement_contract", "verification", {"metric": "phase_noise_1mhz_dbc_hz", "method": "behavioral_psd_evaluation", "offset_hz": 1.0e6, "context_source": "SystemTB operating envelope"})
    node("Validity.VCO.v1", "validity_domain", "verification", {"domain": contract.get("validity", {}), "fidelity": "synthetic_behavioral"}, owner="VCO")
    node("Evidence.sensitivity", "evidence", "verification", {"kind": "deterministic_sensitivity_suite", "method": sensitivity.get("method"), "source": "v1.pipeline.run_sensitivity_suite"})
    node("Evidence.boundary_search", "evidence", "verification", {"kind": "required_pn_boundary", "required_boundary": required_pn, "iterations": None if boundary is None else boundary.get("iterations")})
    if initial_evaluation is not None:
        node("Evidence.SystemTB.initial", "evaluation", "verification", {"passed": initial_evaluation.get("passed"), "metrics": initial_evaluation.get("metrics"), "residuals": initial_evaluation.get("residuals")})
        edge("Evidence.SystemTB.initial", "SystemSpec.integrated_jitter", "derived_from", {"phase": "initial_system_evaluation"})
    if final_evaluation is not None:
        node("Evidence.SystemTB.final", "evaluation", "verification", {"passed": final_evaluation.get("passed"), "metrics": final_evaluation.get("metrics"), "residuals": final_evaluation.get("residuals")})
        edge("VCO.capability_region", "Evidence.SystemTB.final", "supported_by", {"phase": "final_system_validation"})
    edge("VCO.phase_noise_1mhz", "Measurement.VCO.phase_noise_1mhz", "measured_by", {"context_source": "SystemTB operating envelope"})
    edge("VCO", "Schema.BlockMeta.VCO", "contains", {"schema_version": block_meta.get("schema_version")})
    edge("Schema.BlockMeta.VCO", "Contract.VCO.v1", "derived_from", {"contract_id": contract.get("contract_id")})
    edge("Contract.VCO.v1", "Measurement.VCO.phase_noise_1mhz", "supported_by", {"contract_id": contract.get("contract_id")})
    edge("Contract.VCO.v1", "Validity.VCO.v1", "valid_in", {"status": contract.get("status")})
    edge("Evidence.sensitivity", "operator.VCO_Noise_TF", "supports", {"evidence_ids": sorted(sensitivity.get("sweeps", {}).keys())})
    edge("VCORequirement.required", "Evidence.boundary_search", "derived_from", {"method": "bracketed_bisection"})
    edge("VCORequirement.recommended", "Evidence.boundary_search", "derived_from", {"margin_db": None if recommended_requirement is None else recommended_requirement.get("margin_db")})

    for parameter, sweep in sensitivity.get("sweeps", {}).items():
        source = {
            "pn_1mhz_dbc_hz": "VCO.phase_noise_1mhz_design",
            "k1_hz_per_v": "VCO.k1_design",
            "vctrl_max_v": "VCO.vctrl",
        }.get(parameter)
        if source is None:
            continue
        derivatives = sweep.get("local_derivatives", {})
        for metric, target in (
            ("integrated_jitter_s", "PLL.integrated_jitter"),
            ("lock_time_s", "PLL.lock_time"),
        ):
            if derivatives.get(metric) is not None:
                edge(
                    source,
                    target,
                    "sensitivity_evidence",
                    {
                        "method": "central_finite_difference",
                        "value": derivatives[metric],
                        "evidence_id": f"sensitivity:{parameter}:{metric}",
                    },
                )

    graph.validate()
    artifact = graph.to_dict()
    validate_graph_v2_artifact(artifact)
    return artifact
