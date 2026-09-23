"""Deterministic read-only queries for Agent context construction."""

from __future__ import annotations

from collections import deque
from typing import Any, Iterable, Mapping, Sequence

from .planes import GRAPH_PLANES
from .factors import factor_view as _factor_view


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


def plane_view(
    graph: Mapping[str, Any],
    plane: str,
    *,
    include_cross_plane_edges: bool = True,
) -> dict[str, Any]:
    """Return a deterministic read-only view for one Typed Graph plane.

    The canonical artifact remains one graph.  Views are projections for
    Agent context windows and permissions; they do not copy or mutate the
    source graph.  By default, edges are retained when either endpoint is in
    the selected plane so a Contract or Evidence view keeps its boundary
    traceability.
    """

    if plane not in GRAPH_PLANES:
        raise ValueError(f"unknown graph plane: {plane}")
    nodes = [
        dict(node)
        for node in graph.get("nodes", [])
        if node.get("plane") == plane
    ]
    node_ids = {str(node["id"]) for node in nodes}
    edges = []
    for edge in graph.get("edges", []):
        source_in = str(edge.get("source")) in node_ids
        target_in = str(edge.get("target")) in node_ids
        if source_in and target_in or (include_cross_plane_edges and (source_in or target_in)):
            edges.append(dict(edge))
    nodes.sort(key=lambda item: str(item["id"]))
    edges.sort(key=lambda item: (str(item["source"]), str(item["target"]), str(item["type"])))
    return {
        "graph_id": graph.get("graph_id"),
        "graph_version": graph.get("graph_version"),
        "plane": plane,
        "nodes": nodes,
        "edges": edges,
        "metadata": {"view": plane, "read_only": True},
    }


def all_plane_views(
    graph: Mapping[str, Any], *, include_cross_plane_edges: bool = True
) -> dict[str, dict[str, Any]]:
    """Build all four deterministic views in canonical plane order."""

    return {
        plane: plane_view(
            graph, plane, include_cross_plane_edges=include_cross_plane_edges
        )
        for plane in ("schema", "contract", "realization", "evidence")
    }


def contract_view(graph: Mapping[str, Any]) -> dict[str, Any]:
    return plane_view(graph, "contract")


def realization_view(graph: Mapping[str, Any]) -> dict[str, Any]:
    return plane_view(graph, "realization")


def evidence_view(graph: Mapping[str, Any]) -> dict[str, Any]:
    return plane_view(graph, "evidence")


def factor_view(graph: Mapping[str, Any]) -> dict[str, Any]:
    """Return the factor projection without creating another graph artifact."""

    return _factor_view(graph)
