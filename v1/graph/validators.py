"""Semantic checks for Graph v2 artifacts."""

from __future__ import annotations

from typing import Any, Mapping

from .model import (
    EDGE_TYPES,
    GRAPH_SEMANTIC_ROLES,
    GRAPH_STATUSES,
    NODE_TYPES,
    WORKFLOW_NODE_TYPES,
)
from .planes import (
    GRAPH_AUTHORITIES,
    GRAPH_MUTABILITIES,
    GRAPH_PLANES,
    GRAPH_SCOPES,
    EDGE_PLANE_RULES,
    node_plane,
)


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
        if "layer" in node:
            raise ValueError(f"graph v2 node {node_id} must use semantic_role, not layer")
        if node.get("type") not in NODE_TYPES:
            raise ValueError(f"unknown graph v2 node type: {node.get('type')}")
        if (
            node.get("semantic_role") is not None
            and node.get("semantic_role") not in GRAPH_SEMANTIC_ROLES
        ):
            raise ValueError(f"graph v2 node {node_id} has invalid semantic_role")
        if (
            node.get("semantic_role") is None
            and node.get("type") not in WORKFLOW_NODE_TYPES
        ):
            raise ValueError(f"graph v2 node {node_id} missing semantic_role")
        if node.get("status") is not None and node["status"] not in GRAPH_STATUSES:
            raise ValueError(f"graph v2 node {node_id} has invalid status")
        for field, vocabulary in (
            ("plane", GRAPH_PLANES),
            ("authority", GRAPH_AUTHORITIES),
            ("scope", GRAPH_SCOPES),
            ("mutability", GRAPH_MUTABILITIES),
        ):
            if node.get(field) not in vocabulary:
                raise ValueError(f"graph v2 node {node_id} has invalid {field}")
        if not isinstance(node.get("provenance"), Mapping) or not node["provenance"]:
            raise ValueError(f"graph v2 node {node_id} must have provenance")
        expected_plane = node_plane(node_id, str(node["type"]))
        if node["plane"] != expected_plane:
            raise ValueError(
                f"graph v2 node {node_id} has plane {node['plane']}; expected {expected_plane}"
            )
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
        for field, vocabulary in (
            ("plane", GRAPH_PLANES),
            ("authority", GRAPH_AUTHORITIES),
            ("scope", GRAPH_SCOPES),
            ("mutability", GRAPH_MUTABILITIES),
        ):
            if edge.get(field) not in vocabulary:
                raise ValueError(f"graph edge {source} -> {target} has invalid {field}")
        if not isinstance(edge.get("provenance"), Mapping) or not edge["provenance"]:
            raise ValueError(f"graph edge {source} -> {target} must have provenance")
        expected_edge_plane = EDGE_PLANE_RULES.get(str(edge["type"]))
        if expected_edge_plane is not None and edge["plane"] != expected_edge_plane:
            raise ValueError(
                f"graph edge {source} -> {target} has plane {edge['plane']}; "
                f"expected {expected_edge_plane} for {edge['type']}"
            )
        # Canonical Graph v2 edges are compiler-produced append-only facts.
        # Agent-originated hypotheses must stay in a proposal object until a
        # deterministic compiler/evaluator promotes them into this artifact.
        if edge["authority"] != "deterministic_graph_compiler":
            raise ValueError(
                f"graph edge {source} -> {target} must be compiler-owned"
            )
        if edge["mutability"] != "append_only":
            raise ValueError(
                f"canonical graph edge {source} -> {target} must be append_only"
            )
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

    _validate_semantic_freeze(nodes, edges, artifact)

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

        plane = node["plane"]
        node_type = node["type"]
        authority = node["authority"]
        mutability = node["mutability"]
        # These are governance invariants, not style conventions.  They stop
        # an Agent proposal from being promoted to a fact by changing labels.
        if node_type == "realized_instance":
            if plane != "realization" or authority != "realization_compiler":
                raise ValueError(
                    f"realized instance {node_id} must be compiler-owned realization"
                )
        if plane == "evidence":
            if mutability != "append_only":
                raise ValueError(f"evidence-plane node must be append_only: {node_id}")
            if authority not in {"deterministic_simulator", "deterministic_evaluator"}:
                raise ValueError(f"evidence-plane node has non-deterministic authority: {node_id}")
        if node_id.startswith("SystemSpec.") and node_type == "system_requirement":
            if node["plane"] != "realization" or node["mutability"] != "immutable":
                raise ValueError(f"SystemSpec node must be immutable realization: {node_id}")
        if node_type == "candidate" and mutability != "proposed_then_immutable":
            raise ValueError(f"candidate node must be proposed_then_immutable: {node_id}")

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


def _contains_any(value: Any, needles: set[str]) -> bool:
    text = str(value).lower()
    return any(needle in text for needle in needles)


def _close(a: Any, b: Any, tolerance: float = 1e-12) -> bool:
    try:
        left = float(a)
        right = float(b)
    except (TypeError, ValueError):
        return False
    return abs(left - right) <= tolerance * max(1.0, abs(left), abs(right))


def _validate_semantic_freeze(
    nodes: Mapping[str, Mapping[str, Any]],
    edges: list[Mapping[str, Any]],
    artifact: Mapping[str, Any],
) -> None:
    metadata = artifact.get("metadata", {})
    if metadata.get("semantic_role_model") != [
        "architecture",
        "behavior",
        "influence",
        "evidence",
    ]:
        raise ValueError("graph v2 metadata must freeze semantic_role_model")
    forbidden_models = {
        "semantic_layer_model",
        "block_graph_layers",
        "layers",
    }
    if any(key in metadata for key in forbidden_models):
        raise ValueError("graph v2 metadata must not publish layer terminology")

    if "VCO.Kvco" in nodes and "VCO.kvco" in nodes:
        raise ValueError("duplicate VCO Kvco identity: VCO.Kvco and VCO.kvco")

    behavior_knobs = {"pn_anchor", "k1_hz_per_v", "nominal_power", "f0_hz"}
    forbidden_ports = {"phase_noise", "kvco", "power"}
    for node_id, node in nodes.items():
        props = node.get("properties", {})
        semantic_role = node.get("semantic_role")
        if (
            semantic_role == "architecture"
            and node.get("type") == "port"
            and (_contains_any(node_id, forbidden_ports) or _contains_any(props, forbidden_ports))
        ):
            raise ValueError(f"architecture port exposes behavior metric: {node_id}")
        if semantic_role == "behavior" and (
            node.get("type") == "candidate_knob"
            or _contains_any(node_id, behavior_knobs)
            or _contains_any(props.get("knob_name"), behavior_knobs)
        ):
            raise ValueError(f"internal model knob cannot be Behavior: {node_id}")
        if node.get("type") == "block_requirement":
            if props.get("metric") == "phase_noise_1mhz_max_dbc_hz":
                if props.get("measured_metric") != "worst_phase_noise_1mhz_dbc_hz":
                    raise ValueError(f"PN requirement missing measured metric: {node_id}")
                if _close(props.get("value"), props.get("search_knob_boundary")):
                    raise ValueError(
                        f"PN anchor boundary directly assigned to requirement: {node_id}"
                    )
        if node.get("type") in {"evaluation", "evidence", "measured_result"}:
            if not isinstance(node.get("provenance"), Mapping) or not node["provenance"]:
                raise ValueError(f"evidence missing provenance: {node_id}")
            if node.get("semantic_role") == "evidence" and not props.get("measurement_method"):
                raise ValueError(f"evidence missing measurement method: {node_id}")
        if node.get("type") == "validity_domain":
            for key in ("declared_domain", "validated_domain"):
                if key not in props:
                    raise ValueError(f"validity domain missing {key}: {node_id}")
        if node_id.startswith("BlockTB."):
            context = props.get("context", {})
            if context.get("context_id") != "VCOBlockContext.v1":
                raise ValueError(f"BlockTB did not use frozen VCOBlockContext: {node_id}")
            for key in ("vctrl_min_v", "vctrl_max_v", "temperature_points_c", "vdd_v"):
                if key not in context:
                    raise ValueError(f"BlockTB context missing {key}: {node_id}")

    for edge in edges:
        source = str(edge["source"])
        target = str(edge["target"])
        edge_type = str(edge["type"])
        source_node = nodes[source]
        target_node = nodes[target]
        if (
            source_node.get("semantic_role") == "behavior"
            and target_node.get("type") == "system_metric"
            and edge_type != "system_influence"
        ):
            raise ValueError(
                f"Behavior-to-SystemMetric edge must be Influence: {source} -> {target}"
            )
        if edge_type == "system_influence":
            props = edge.get("properties", {})
            for key in ("source_behavior_metric", "target_system_metric", "mechanism"):
                if key not in props:
                    raise ValueError(f"system_influence missing {key}: {source} -> {target}")
        if edge_type == "behavioral_dependency" and source == "Environment.vdd":
            raise ValueError(f"VDD is context only, not a declared behavior dependency: {source} -> {target}")
        if (
            target_node.get("type") == "block_requirement"
            and source_node.get("type") in {"candidate", "candidate_knob", "realized_instance"}
            and edge_type in {"verifies_requirement", "constrains", "derived_from"}
        ):
            raise ValueError(
                f"candidate/knob cannot directly judge BlockRequirement: {source} -> {target}"
            )

    capability_members = [
        edge
        for edge in edges
        if edge.get("type") == "candidate_of"
        and edge.get("target") == "VCO.capability_region"
        and edge.get("status") == "validated"
    ]
    for edge in capability_members:
        candidate_id = str(edge["source"]).split(".", 1)[1]
        block_tb = nodes.get(f"BlockTB.{candidate_id}", {})
        if block_tb.get("properties", {}).get("passed") is not True:
            raise ValueError(
                f"capability feasible point lacks passing BlockTB: {edge['source']}"
            )
