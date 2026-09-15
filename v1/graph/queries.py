"""Deterministic read-only queries for Agent context construction."""

from __future__ import annotations

from collections import deque
from typing import Any, Iterable, Mapping, Sequence


def trace_paths(
    graph: Mapping[str, Any],
    source: str,
    target: str,
    *,
    edge_types: Iterable[str] | None = None,
    max_depth: int = 8,
) -> list[dict[str, Any]]:
    """Return deterministic simple paths between two graph nodes."""

    node_ids = {str(node["id"]) for node in graph.get("nodes", [])}
    if source not in node_ids or target not in node_ids:
        raise ValueError("trace source and target must exist in graph")
    allowed = None if edge_types is None else set(edge_types)
    adjacency: dict[str, list[Mapping[str, Any]]] = {node_id: [] for node_id in node_ids}
    for edge in graph.get("edges", []):
        if allowed is None or edge.get("type") in allowed:
            adjacency[str(edge["source"])].append(edge)
    for edges in adjacency.values():
        edges.sort(key=lambda item: (str(item["target"]), str(item["type"])))

    queue = deque([(source, [source], [])])
    paths: list[dict[str, Any]] = []
    while queue:
        current, nodes, edges = queue.popleft()
        if len(edges) >= max_depth:
            continue
        for edge in adjacency[current]:
            next_node = str(edge["target"])
            if next_node in nodes:
                continue
            next_nodes = nodes + [next_node]
            next_edges = edges + [dict(edge)]
            if next_node == target:
                paths.append({"nodes": next_nodes, "edges": next_edges})
            else:
                queue.append((next_node, next_nodes, next_edges))
    return paths


def requirement_allocation_paths(
    graph: Mapping[str, Any], requirement_id: str
) -> list[dict[str, Any]]:
    """Trace one SystemSpec requirement to every allocated Block requirement."""

    targets = {
        str(edge["target"])
        for edge in graph.get("edges", [])
        if edge.get("type") == "allocates" and edge.get("source") == requirement_id
    }
    paths: list[dict[str, Any]] = []
    for target in sorted(targets):
        paths.extend(trace_paths(graph, requirement_id, target, max_depth=4))
    return paths


def evidence_neighborhood(
    graph: Mapping[str, Any], node_id: str
) -> dict[str, Sequence[Mapping[str, Any]]]:
    """Return evidence-bearing incoming and outgoing edges for one node."""

    evidence_types = {
        "sensitivity_evidence",
        "validated_by",
        "supported_by",
        "supports",
        "derived_from",
        "measured_by",
        "valid_in",
    }
    incoming = [
        edge
        for edge in graph.get("edges", [])
        if edge.get("target") == node_id and edge.get("type") in evidence_types
    ]
    outgoing = [
        edge
        for edge in graph.get("edges", [])
        if edge.get("source") == node_id and edge.get("type") in evidence_types
    ]
    return {"incoming": incoming, "outgoing": outgoing}
