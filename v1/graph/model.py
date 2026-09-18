"""Typed, deterministic graph primitives used by the V1/V2 allocation seam.

The graph is intentionally a small property graph rather than a dependency on
an external graph database.  V1 callers can continue to create plain nodes and
edges.  Graph v2 callers may additionally attach a semantic role, owner and
lifecycle status; the validator then checks the graph vocabulary and semantic
edge references before an artifact is serialized.

Public Block Graph semantics are carried only by ``semantic_role``.  The
``plane`` metadata is retained for implementation provenance/authority and is
not a Block Graph layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from .planes import (
    GRAPH_AUTHORITIES,
    GRAPH_MUTABILITIES,
    GRAPH_PLANES,
    GRAPH_SCOPES,
    default_edge_metadata,
    default_node_metadata,
)


GRAPH_SEMANTIC_ROLES = frozenset(
    {"architecture", "behavior", "influence", "evidence"}
)
WORKFLOW_NODE_TYPES = frozenset(
    {
        "system_requirement",
        "block_requirement",
        "capability_region",
        "design_space",
        "candidate",
        "candidate_knob",
        "realized_instance",
        "contract",
        "schema_definition",
        "measurement_contract",
        "validity_domain",
        "uncertainty_model",
    }
)
GRAPH_STATUSES = frozenset(
    {"proposed", "supported", "tested", "partially_validated", "validated", "rejected"}
)

# These are the stable vocabulary exposed to a future Agent.  Adding a new
# domain-specific node/edge must be an explicit schema change, not a silently
# invented string in an Agent response.
NODE_TYPES = frozenset(
    {
        "architecture_block",
        "port",
        "signal",
        "context",
        "context_variable",
        "behavioral_variable",
        "design_variable",
        "behavioral_output",
        "system_metric",
        "system_requirement",
        "block_requirement",
        "capability_region",
        "design_space",
        "candidate",
        "candidate_knob",
        "realized_instance",
        "operator",
        "contract",
        "schema_definition",
        "measurement_contract",
        "validity_domain",
        "uncertainty_model",
        "evidence",
        "measured_result",
        "evaluation",
    }
)

EDGE_TYPES = frozenset(
    {
        # Existing V1 vocabulary.
        "signal_flow",
        "feedback",
        "behavioral_dependency",
        "noise_transfer",
        "system_influence",
        "constrains",
        "sensitivity_evidence",
        "contract_dependency",
        # V2 typed vocabulary.
        "contains",
        "provides",
        "requires",
        "connects_to",
        "input_to",
        "produces",
        "allocates",
        "candidate_of",
        "realizes",
        "validated_by",
        "measured_by",
        "valid_in",
        "supports",
        "supported_by",
        "derived_from",
        "shortcut",
        "evaluates",
        "uses_context",
        "covers",
        "verifies_requirement",
        "yields_verdict",
        "selected_for",
    }
)


@dataclass(frozen=True)
class GraphNode:
    node_id: str
    node_type: str
    properties: Dict[str, Any] = field(default_factory=dict)
    semantic_role: Optional[str] = None
    owner: Optional[str] = None
    status: Optional[str] = None
    plane: Optional[str] = None
    authority: Optional[str] = None
    scope: Optional[str] = None
    mutability: Optional[str] = None
    provenance: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "id": self.node_id,
            "type": self.node_type,
            "properties": self.properties,
        }
        if self.semantic_role is not None:
            result["semantic_role"] = self.semantic_role
        if self.owner is not None:
            result["owner"] = self.owner
        if self.status is not None:
            result["status"] = self.status
        if self.plane is not None:
            result["plane"] = self.plane
        if self.authority is not None:
            result["authority"] = self.authority
        if self.scope is not None:
            result["scope"] = self.scope
        if self.mutability is not None:
            result["mutability"] = self.mutability
        if self.provenance is not None:
            result["provenance"] = self.provenance
        return result


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    edge_type: str
    properties: Dict[str, Any] = field(default_factory=dict)
    status: Optional[str] = None
    plane: Optional[str] = None
    authority: Optional[str] = None
    scope: Optional[str] = None
    mutability: Optional[str] = None
    provenance: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "source": self.source,
            "target": self.target,
            "type": self.edge_type,
            "properties": self.properties,
        }
        if self.status is not None:
            result["status"] = self.status
        if self.plane is not None:
            result["plane"] = self.plane
        if self.authority is not None:
            result["authority"] = self.authority
        if self.scope is not None:
            result["scope"] = self.scope
        if self.mutability is not None:
            result["mutability"] = self.mutability
        if self.provenance is not None:
            result["provenance"] = self.provenance
        return result


@dataclass
class TypedGraph:
    graph_id: str
    graph_version: str = "1.0"
    nodes: List[GraphNode] = field(default_factory=list)
    edges: List[GraphEdge] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_node(
        self,
        node_id: str,
        node_type: str,
        properties: Mapping[str, Any] | None = None,
        *,
        layer: Optional[str] = None,
        semantic_role: Optional[str] = None,
        owner: Optional[str] = None,
        status: Optional[str] = None,
        plane: Optional[str] = None,
        authority: Optional[str] = None,
        scope: Optional[str] = None,
        mutability: Optional[str] = None,
        provenance: Mapping[str, Any] | None = None,
    ) -> None:
        if any(node.node_id == node_id for node in self.nodes):
            return
        node_properties = dict(properties or {})
        if semantic_role is None and layer is not None:
            semantic_role = layer
        if self.graph_version.startswith("2."):
            defaults = default_node_metadata(node_id, node_type, node_properties)
            plane = plane or defaults["plane"]
            authority = authority or defaults["authority"]
            scope = scope or defaults["scope"]
            mutability = mutability or defaults["mutability"]
            provenance = dict(provenance or defaults["provenance"])
        self.nodes.append(
            GraphNode(
                node_id,
                node_type,
                node_properties,
                semantic_role=semantic_role,
                owner=owner,
                status=status,
                plane=plane,
                authority=authority,
                scope=scope,
                mutability=mutability,
                provenance=dict(provenance) if provenance is not None else None,
            )
        )

    def add_edge(
        self,
        source: str,
        target: str,
        edge_type: str,
        properties: Mapping[str, Any] | None = None,
        *,
        status: Optional[str] = None,
        plane: Optional[str] = None,
        authority: Optional[str] = None,
        scope: Optional[str] = None,
        mutability: Optional[str] = None,
        provenance: Mapping[str, Any] | None = None,
    ) -> None:
        if not any(
            edge.source == source
            and edge.target == target
            and edge.edge_type == edge_type
            for edge in self.edges
        ):
            edge_properties = dict(properties or {})
            source_node = next((node for node in self.nodes if node.node_id == source), None)
            target_node = next((node for node in self.nodes if node.node_id == target), None)
            if self.graph_version.startswith("2.") and source_node and target_node:
                defaults = default_edge_metadata(
                    edge_type,
                    source_node.to_dict(),
                    target_node.to_dict(),
                    edge_properties,
                )
                plane = plane or defaults["plane"]
                authority = authority or defaults["authority"]
                scope = scope or defaults["scope"]
                mutability = mutability or defaults["mutability"]
                provenance = dict(provenance or defaults["provenance"])
            self.edges.append(
                GraphEdge(
                    source,
                    target,
                    edge_type,
                    edge_properties,
                    status=status,
                    plane=plane,
                    authority=authority,
                    scope=scope,
                    mutability=mutability,
                    provenance=dict(provenance) if provenance is not None else None,
                )
            )

    def validate(self) -> None:
        node_ids = {node.node_id for node in self.nodes}
        if len(node_ids) != len(self.nodes):
            raise ValueError("graph contains duplicate node ids")
        strict = self.graph_version.startswith("2.")
        if strict:
            for node in self.nodes:
                if node.node_type not in NODE_TYPES:
                    raise ValueError(f"unknown graph node type: {node.node_type}")
                if (
                    node.semantic_role is not None
                    and node.semantic_role not in GRAPH_SEMANTIC_ROLES
                ):
                    raise ValueError(
                        f"graph v2 node {node.node_id} must have a valid semantic_role"
                    )
                if (
                    node.semantic_role is None
                    and node.node_type not in WORKFLOW_NODE_TYPES
                ):
                    raise ValueError(
                        f"graph v2 node {node.node_id} must declare semantic_role"
                    )
                if node.status is not None and node.status not in GRAPH_STATUSES:
                    raise ValueError(f"unknown node status: {node.status}")
                if node.plane not in GRAPH_PLANES:
                    raise ValueError(f"unknown graph plane: {node.plane}")
                if node.authority not in GRAPH_AUTHORITIES:
                    raise ValueError(f"unknown graph authority: {node.authority}")
                if node.scope not in GRAPH_SCOPES:
                    raise ValueError(f"unknown graph scope: {node.scope}")
                if node.mutability not in GRAPH_MUTABILITIES:
                    raise ValueError(f"unknown graph mutability: {node.mutability}")
                if not isinstance(node.provenance, Mapping) or not node.provenance:
                    raise ValueError(f"graph v2 node {node.node_id} must have provenance")
        for edge in self.edges:
            if edge.source not in node_ids or edge.target not in node_ids:
                raise ValueError(
                    f"graph edge references unknown node: {edge.source} -> {edge.target}"
                )
            if strict and edge.edge_type not in EDGE_TYPES:
                raise ValueError(f"unknown graph edge type: {edge.edge_type}")
            if edge.status is not None and edge.status not in GRAPH_STATUSES:
                raise ValueError(f"unknown edge status: {edge.status}")
            if strict:
                if edge.plane not in GRAPH_PLANES:
                    raise ValueError(f"unknown graph edge plane: {edge.plane}")
                if edge.authority not in GRAPH_AUTHORITIES:
                    raise ValueError(f"unknown graph edge authority: {edge.authority}")
                if edge.scope not in GRAPH_SCOPES:
                    raise ValueError(f"unknown graph edge scope: {edge.scope}")
                if edge.mutability not in GRAPH_MUTABILITIES:
                    raise ValueError(f"unknown graph edge mutability: {edge.mutability}")
                if not isinstance(edge.provenance, Mapping) or not edge.provenance:
                    raise ValueError(
                        f"graph v2 edge {edge.source} -> {edge.target} must have provenance"
                    )

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        result = {
            "graph_id": self.graph_id,
            "graph_version": self.graph_version,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
        }
        if self.metadata:
            result["metadata"] = self.metadata
        return result
