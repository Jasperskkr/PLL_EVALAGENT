"""Compile the current V1 outputs into explicit, replayable graph evidence."""

from __future__ import annotations

from typing import Any, Mapping

from .model import TypedGraph


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

