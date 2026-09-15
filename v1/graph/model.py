"""Minimal typed property graph with deterministic serialization."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping


@dataclass(frozen=True)
class GraphNode:
    node_id: str
    node_type: str
    properties: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.node_id,
            "type": self.node_type,
            "properties": self.properties,
        }


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    edge_type: str
    properties: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "type": self.edge_type,
            "properties": self.properties,
        }


@dataclass
class TypedGraph:
    graph_id: str
    graph_version: str = "1.0"
    nodes: List[GraphNode] = field(default_factory=list)
    edges: List[GraphEdge] = field(default_factory=list)

    def add_node(
        self, node_id: str, node_type: str, properties: Mapping[str, Any] | None = None
    ) -> None:
        if any(node.node_id == node_id for node in self.nodes):
            return
        self.nodes.append(GraphNode(node_id, node_type, dict(properties or {})))

    def add_edge(
        self,
        source: str,
        target: str,
        edge_type: str,
        properties: Mapping[str, Any] | None = None,
    ) -> None:
        if not any(
            edge.source == source
            and edge.target == target
            and edge.edge_type == edge_type
            for edge in self.edges
        ):
            self.edges.append(
                GraphEdge(source, target, edge_type, dict(properties or {}))
            )

    def validate(self) -> None:
        node_ids = {node.node_id for node in self.nodes}
        for edge in self.edges:
            if edge.source not in node_ids or edge.target not in node_ids:
                raise ValueError(
                    f"graph edge references unknown node: {edge.source} -> {edge.target}"
                )

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return {
            "graph_id": self.graph_id,
            "graph_version": self.graph_version,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
        }

