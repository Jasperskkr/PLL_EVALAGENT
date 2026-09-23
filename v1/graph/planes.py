"""Orthogonal plane metadata for the unified Typed Graph.

Public Block Graph semantics are expressed by ``semantic_role``
(``architecture/behavior/influence/evidence``).  A plane answers a different
question: is a node a schema definition, a reusable contract/hypothesis, a
run-time realization, or immutable evaluation evidence?  Keeping these
dimensions orthogonal gives future Agents enforceable authority boundaries;
planes are implementation metadata, not public Block Graph layers.
"""

from __future__ import annotations

from typing import Any, Mapping


GRAPH_PLANES = frozenset({"schema", "contract", "realization", "evidence"})
GRAPH_AUTHORITIES = frozenset(
    {
        "schema_compiler",
        "contract_builder",
        "agent_or_allocator",
        "deterministic_allocator",
        "system_spec_input",
        "realization_compiler",
        "deterministic_simulator",
        "deterministic_evaluator",
        "deterministic_graph_compiler",
    }
)
GRAPH_SCOPES = frozenset({"global", "reusable", "run_specific"})
GRAPH_MUTABILITIES = frozenset(
    {"immutable", "versioned", "proposed_then_immutable", "append_only"}
)

# Edge planes are intentionally keyed by relation semantics rather than only
# by endpoint planes.  This matters for cross-plane provenance: a
# ``sensitivity_evidence`` edge connects a behavioral variable to a system
# metric, but the relationship itself is evidence emitted by a deterministic
# sweep.  Keeping that fact explicit lets an Agent request evidence views
# without mistaking a structural dependency for a validated influence.
EDGE_PLANE_RULES = {
    "validated_by": "evidence",
    "evaluates": "evidence",
    "covers": "evidence",
    "verifies_requirement": "evidence",
    "yields_verdict": "evidence",
    "sensitivity_evidence": "evidence",
    "supported_by": "evidence",
    "supports": "evidence",
    "uses_context": "evidence",
    "allocates": "realization",
    "candidate_of": "realization",
    "realizes": "realization",
    "selected_for": "realization",
    "constrains": "realization",
    "measured_by": "contract",
    "valid_in": "contract",
    "factor_input": "contract",
    "factor_output": "contract",
}

SCHEMA_NODE_TYPES = frozenset(
    {
        "architecture_block",
        "port",
        "signal",
        "context_variable",
        "schema_definition",
        "design_variable",
        "behavioral_output",
        "system_metric",
        "operator",
    }
)
REALIZATION_NODE_TYPES = frozenset(
    {
        "system_requirement",
        "block_requirement",
        "capability_region",
        "system_feasible_region",
        "design_space",
        "candidate",
        "candidate_knob",
        "realized_instance",
    }
)
CONTRACT_NODE_TYPES = frozenset(
    {
        "contract",
        "measurement_contract",
        "validity_domain",
        "uncertainty_model",
        "behavioral_variable",
        "factor",
    }
)


def node_plane(node_id: str, node_type: str) -> str:
    """Return the canonical plane for a node vocabulary member.

    A few context IDs are intentionally specialized: the frozen VCO context
    is a reusable contract, while a context captured by a particular SystemTB
    run is evidence.  This is a deterministic naming convention, not an Agent
    guess.
    """

    if node_id.startswith("Schema."):
        return "schema"
    if node_id.startswith("Contract."):
        return "contract"
    if node_id.startswith("Evidence.") or node_id == "SystemSpec.verdict":
        return "evidence"
    if node_id.startswith(("SystemSpec.", "VCORequirement.", "Candidate.", "Instance.", "Knob.")):
        return "realization"
    if node_id.startswith("Context.VCO.contract"):
        return "contract"
    if node_id.startswith("Context.SystemTB."):
        return "evidence"
    if node_type in SCHEMA_NODE_TYPES:
        return "schema"
    if node_type in CONTRACT_NODE_TYPES:
        return "contract"
    if node_type in REALIZATION_NODE_TYPES:
        return "realization"
    if node_type in {"evidence", "evaluation", "measured_result"}:
        return "evidence"
    # ``context`` is only used for the two explicit context namespaces above.
    if node_type == "context":
        return "contract"
    raise ValueError(f"cannot classify graph node plane: {node_id} ({node_type})")


def node_authority(node_id: str, node_type: str, plane: str) -> str:
    if plane == "schema":
        return "schema_compiler"
    if plane == "contract":
        return "contract_builder"
    # Evaluation/evidence nodes are facts emitted by the deterministic
    # simulator/evaluator.  This check must happen before the SystemSpec ID
    # convention below because ``SystemSpec.verdict`` is an evidence node
    # whose identifier still starts with ``SystemSpec.``.
    if plane == "evidence" or node_type in {"evidence", "evaluation", "measured_result"}:
        return "deterministic_evaluator"
    if node_type == "system_requirement" or node_id.startswith("SystemSpec."):
        return "system_spec_input"
    if node_type in {"candidate", "candidate_knob"}:
        return "agent_or_allocator"
    if node_type in {
        "capability_region",
        "system_feasible_region",
        "design_space",
        "block_requirement",
    }:
        return "deterministic_allocator"
    if node_type == "realized_instance":
        return "realization_compiler"
    return "deterministic_evaluator"


def node_scope(node_id: str, node_type: str, plane: str) -> str:
    if plane == "schema":
        return "global"
    if plane == "contract":
        return "reusable"
    return "run_specific"


def node_mutability(node_id: str, node_type: str, plane: str) -> str:
    if plane == "schema" or node_type == "system_requirement":
        return "immutable"
    if plane == "contract":
        return "versioned"
    if node_type == "candidate":
        return "proposed_then_immutable"
    if plane == "evidence" or node_type in {"evaluation", "evidence", "measured_result"}:
        return "append_only"
    return "immutable"


def default_provenance(
    node_id: str,
    node_type: str,
    plane: str,
    properties: Mapping[str, Any],
) -> dict[str, Any]:
    """Create a compact, serializable provenance descriptor.

    Detailed numeric evidence remains in node properties and referenced JSON
    artifacts.  This descriptor records who/what generated the object without
    duplicating those payloads.
    """

    if plane == "schema":
        source = "v1/graph/model.py"
    elif plane == "contract":
        source = str(properties.get("source", "v1.contract / v1.schema"))
    elif node_type == "realized_instance":
        source = "v1.graph.compiler.realized_instance"
    elif plane == "realization":
        source = str(properties.get("source", "v1.graph.compiler.allocation"))
    else:
        source = str(
            properties.get("source", "v1.pipeline / run_v1_prove.py deterministic evaluation")
        )
    result: dict[str, Any] = {"source": source, "plane": plane}
    for key in ("artifact_ref", "model_ref", "evidence_id"):
        if properties.get(key) is not None:
            result[key] = properties[key]
    return result


def default_node_metadata(
    node_id: str, node_type: str, properties: Mapping[str, Any]
) -> dict[str, Any]:
    plane = node_plane(node_id, node_type)
    return {
        "plane": plane,
        "authority": node_authority(node_id, node_type, plane),
        "scope": node_scope(node_id, node_type, plane),
        "mutability": node_mutability(node_id, node_type, plane),
        "provenance": default_provenance(node_id, node_type, plane, properties),
    }


def default_edge_metadata(
    edge_type: str,
    source: Mapping[str, Any],
    target: Mapping[str, Any],
    properties: Mapping[str, Any],
) -> dict[str, Any]:
    """Infer relation metadata from already typed endpoints.

    The relation is attributed to the more authoritative target plane for
    cross-plane edges (for example allocation and evidence), while same-plane
    edges retain that plane.  ``authority`` records the deterministic graph
    compiler; it is not permission for an Agent to forge a validated edge.
    """

    source_plane = str(source.get("plane"))
    target_plane = str(target.get("plane"))
    if edge_type in EDGE_PLANE_RULES:
        plane = EDGE_PLANE_RULES[edge_type]
    elif source_plane == target_plane:
        plane = source_plane
    else:
        plane = target_plane
    result: dict[str, Any] = {
        "plane": plane,
        "authority": "deterministic_graph_compiler",
        "scope": "run_specific",
        "mutability": "append_only",
        "provenance": {"source": "v1.graph.compiler", "edge_type": edge_type},
    }
    if properties.get("evidence_id") is not None:
        result["provenance"]["evidence_id"] = properties["evidence_id"]
    return result
