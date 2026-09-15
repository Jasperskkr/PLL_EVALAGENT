"""Typed, deterministic graph primitives used by the V1/V2 allocation seam.

The graph is intentionally a small property graph rather than a dependency on
an external graph database.  V1 callers can continue to create plain nodes and
edges.  Graph v2 callers may additionally attach a layer, owner and lifecycle
status; the validator then checks the graph vocabulary and semantic edge
references before an artifact is serialized.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional


GRAPH_LAYERS = frozenset({"interface", "behavior", "allocation", "verification"})
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
        "design_variable",
        "behavioral_output",
        "system_metric",
        "system_requirement",
        "block_requirement",
        "capability_region",
        "design_space",
        "candidate",
        "realized_instance",
        "operator",
        "contract",
        "measurement_contract",
        "validity_domain",
        "uncertainty_model",
        "evidence",
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
    layer: Optional[str] = None
    owner: Optional[str] = None
    status: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "id": self.node_id,
            "type": self.node_type,
            "properties": self.properties,
        }
        if self.layer is not None:
            result["layer"] = self.layer
        if self.owner is not None:
            result["owner"] = self.owner
        if self.status is not None:
            result["status"] = self.status
        return result


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    edge_type: str
    properties: Dict[str, Any] = field(default_factory=dict)
    status: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "source": self.source,
            "target": self.target,
            "type": self.edge_type,
            "properties": self.properties,
        }
        if self.status is not None:
            result["status"] = self.status
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
        owner: Optional[str] = None,
        status: Optional[str] = None,
    ) -> None:
        if any(node.node_id == node_id for node in self.nodes):
            return
        self.nodes.append(
            GraphNode(
                node_id,
                node_type,
                dict(properties or {}),
                layer=layer,
                owner=owner,
                status=status,
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
    ) -> None:
        if not any(
            edge.source == source
            and edge.target == target
            and edge.edge_type == edge_type
            for edge in self.edges
        ):
            self.edges.append(
                GraphEdge(
                    source,
                    target,
                    edge_type,
                    dict(properties or {}),
                    status=status,
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
                if node.layer not in GRAPH_LAYERS:
                    raise ValueError(
                        f"graph v2 node {node.node_id} must have a valid layer"
                    )
                if node.status is not None and node.status not in GRAPH_STATUSES:
                    raise ValueError(f"unknown node status: {node.status}")
        for edge in self.edges:
            if edge.source not in node_ids or edge.target not in node_ids:
                raise ValueError(
                    f"graph edge references unknown node: {edge.source} -> {edge.target}"
                )
            if strict and edge.edge_type not in EDGE_TYPES:
                raise ValueError(f"unknown graph edge type: {edge.edge_type}")
            if edge.status is not None and edge.status not in GRAPH_STATUSES:
                raise ValueError(f"unknown edge status: {edge.status}")

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
