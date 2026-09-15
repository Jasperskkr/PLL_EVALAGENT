"""Semantic checks for Graph v2 artifacts."""

from __future__ import annotations

from typing import Any, Mapping

from .model import EDGE_TYPES, GRAPH_LAYERS, GRAPH_STATUSES, NODE_TYPES


EDGE_ENDPOINT_RULES = {
    "connects_to": ({"port"}, {"port"}),
    "input_to": ({"port", "behavioral_output", "design_variable", "operator"}, {"operator"}),
    "produces": ({"operator"}, {"system_metric", "behavioral_output", "evaluation"}),
    "allocates": ({"system_requirement", "system_metric"}, {"block_requirement"}),
    "candidate_of": ({"candidate"}, {"capability_region", "design_space"}),
    "realizes": ({"candidate"}, {"realized_instance"}),
    "measured_by": ({"behavioral_output", "system_metric"}, {"measurement_contract"}),
    "valid_in": ({"contract"}, {"validity_domain"}),
    "evaluates": ({"realized_instance"}, {"evaluation"}),
    "uses_context": ({"evaluation"}, {"context"}),
    "covers": ({"context"}, {"context"}),
    "verifies_requirement": ({"evaluation"}, {"system_requirement", "block_requirement"}),
    "yields_verdict": ({"evaluation"}, {"evaluation"}),
    "selected_for": ({"candidate"}, {"candidate"}),
}


def _nodes(artifact: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    nodes = artifact.get("nodes")
    if not isinstance(nodes, list):
        raise ValueError("graph nodes must be an array")
    result: dict[str, Mapping[str, Any]] = {}
    for node in nodes:
        if not isinstance(node, Mapping) or not node.get("id"):
            raise ValueError("graph node must be a non-empty object with id")
        node_id = str(node["id"])
        if node_id in result:
            raise ValueError(f"duplicate graph node id: {node_id}")
        if node.get("type") not in NODE_TYPES:
            raise ValueError(f"unknown graph v2 node type: {node.get('type')}")
        if node.get("layer") not in GRAPH_LAYERS:
            raise ValueError(f"graph v2 node {node_id} has invalid layer")
        if node.get("status") is not None and node["status"] not in GRAPH_STATUSES:
            raise ValueError(f"graph v2 node {node_id} has invalid status")
        result[node_id] = node
    return result


def validate_graph_v2_artifact(artifact: Mapping[str, Any]) -> None:
    """Validate vocabulary, references and required evidence shape."""

    if artifact.get("graph_version") != "2.0":
        raise ValueError("Graph v2 artifact must declare graph_version 2.0")
    nodes = _nodes(artifact)
    edges = artifact.get("edges")
    if not isinstance(edges, list):
        raise ValueError("graph edges must be an array")
    for edge in edges:
        if not isinstance(edge, Mapping):
            raise ValueError("graph edge must be an object")
        source = str(edge.get("source", ""))
        target = str(edge.get("target", ""))
        if source not in nodes or target not in nodes:
            raise ValueError(f"graph edge references unknown node: {source} -> {target}")
        if edge.get("type") not in EDGE_TYPES:
            raise ValueError(f"unknown graph v2 edge type: {edge.get('type')}")
        if edge.get("status") is not None and edge["status"] not in GRAPH_STATUSES:
            raise ValueError(f"graph edge has invalid status: {edge['status']}")
        if not isinstance(edge.get("properties", {}), Mapping):
            raise ValueError("graph edge properties must be an object")
        endpoint_rule = EDGE_ENDPOINT_RULES.get(str(edge["type"]))
        if endpoint_rule is not None:
            source_type = nodes[source]["type"]
            target_type = nodes[target]["type"]
            if source_type not in endpoint_rule[0] or target_type not in endpoint_rule[1]:
                raise ValueError(
                    f"invalid endpoints for {edge['type']}: "
                    f"{source}({source_type}) -> {target}({target_type})"
                )
        if edge["type"] == "connects_to":
            source_props = nodes[source].get("properties", {})
            target_props = nodes[target].get("properties", {})
            source_unit = source_props.get("unit")
            target_unit = target_props.get("unit")
            if source_unit and target_unit and source_unit != target_unit:
                raise ValueError(
                    f"unit mismatch on connects_to: {source_unit} != {target_unit}"
                )
            if source_props.get("direction") not in {"out", "inout"}:
                raise ValueError(f"connects_to source port is not an output: {source}")
            if target_props.get("direction") not in {"in", "inout"}:
                raise ValueError(f"connects_to target port is not an input: {target}")

    required_ids = (
        "SystemSpec.integrated_jitter",
        "VCORequirement.required",
        "VCO.capability_region",
        "operator.VCO_Noise_TF",
        "operator.Noise_Integration",
        "operator.PLL_Dynamics",
    )
    missing = [node_id for node_id in required_ids if node_id not in nodes]
    if missing:
        raise ValueError(f"graph v2 missing required node(s): {missing}")

    edge_types = {edge["type"] for edge in edges}
    required_edge_types = ["input_to", "produces"]
    if artifact.get("metadata", {}).get("allocation_outcome") == "rejected":
        required_edge_types.append("supported_by")
    else:
        required_edge_types.extend(["allocates", "validated_by"])
    for required_type in required_edge_types:
        if required_type not in edge_types:
            raise ValueError(f"graph v2 missing required edge type: {required_type}")

    for node_id, node in nodes.items():
        if node["type"] in {"system_requirement", "block_requirement"}:
            props = node.get("properties", {})
            if not isinstance(props, Mapping):
                raise ValueError(f"requirement node {node_id} properties must be an object")
            if "source" not in props:
                raise ValueError(f"requirement node {node_id} missing source")
        if node["type"] == "evaluation":
            passed = node.get("properties", {}).get("passed")
            if passed is False and node.get("status") != "rejected":
                raise ValueError(f"failed evaluation node must be rejected: {node_id}")
            if passed is True and node.get("status") == "rejected":
                raise ValueError(f"passing evaluation node cannot be rejected: {node_id}")

    evidence_ids = {
        node_id for node_id, node in nodes.items() if node["type"] == "evidence"
    }
    for edge in edges:
        evidence_ref = edge.get("properties", {}).get("evidence_id")
        if evidence_ref is not None and evidence_ref not in evidence_ids:
            raise ValueError(f"edge references unknown evidence node: {evidence_ref}")

    for edge in edges:
        if edge["type"] in {"validated_by", "evaluates", "covers", "verifies_requirement"}:
            passed = edge.get("properties", {}).get("passed")
            if passed is False and edge.get("status") != "rejected":
                raise ValueError("failed evaluation relationship must be rejected")
            if passed is True and edge.get("status") == "rejected":
                raise ValueError("passing evaluation relationship cannot be rejected")
