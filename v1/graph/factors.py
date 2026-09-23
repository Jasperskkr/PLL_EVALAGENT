"""First-class, auditable factor objects for the canonical Typed Graph.

Factors are deliberately a small representation layer.  They do not execute
inference or optimization; their inputs, outputs, model/evidence references,
and validity claims are compiled into the same graph as the legacy edges.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


FACTOR_TYPES = frozenset(
    {"system_response", "allocation", "constraint", "block_response"}
)
FACTOR_VERIFICATION_STATUSES = frozenset(
    {"unverified", "proposed", "supported", "partially_validated", "validated", "rejected"}
)
MODEL_KINDS = frozenset(
    {
        "discrete_conditional_map",
        "piecewise_linear",
        "surrogate",
        "gaussian_process",
        "analytical",
        "deterministic_behavioral_response",
        "empirical_sweep",
        "unknown",
    }
)


def _string_tuple(values: Sequence[str] | None) -> tuple[str, ...]:
    return tuple(str(value) for value in (values or ()))


@dataclass(frozen=True)
class Factor:
    """Schema-level description of one joint relationship.

    ``input_refs`` and ``output_refs`` are intentionally arbitrary-length so a
    future factor can add dimensions without changing this core schema.
    ``validity_domain`` and ``uncertainty`` remain descriptive metadata until a
    deterministic verifier promotes a factor to ``validated``.
    """

    factor_id: str
    factor_type: str
    name: str
    input_refs: tuple[str, ...] = field(default_factory=tuple)
    output_refs: tuple[str, ...] = field(default_factory=tuple)
    relation_kind: str = "joint_dependency"
    model_kind: str = "unknown"
    model_ref: str | None = None
    artifact_ref: str | None = None
    validity_domain: Mapping[str, Any] | None = None
    context_refs: tuple[str, ...] = field(default_factory=tuple)
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    uncertainty: Mapping[str, Any] | None = None
    verification_status: str = "unverified"
    source_run_ids: tuple[str, ...] = field(default_factory=tuple)
    artifact_hashes: Mapping[str, str] | None = None
    version: str = "1.0"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.factor_id or not self.name:
            raise ValueError("factor_id and name are required")
        if self.factor_type not in FACTOR_TYPES:
            raise ValueError(f"unknown factor_type: {self.factor_type}")
        if self.model_kind not in MODEL_KINDS:
            raise ValueError(f"unknown model_kind: {self.model_kind}")
        if self.verification_status not in FACTOR_VERIFICATION_STATUSES:
            raise ValueError(
                f"unknown factor verification_status: {self.verification_status}"
            )
        if not self.input_refs:
            raise ValueError("factor must declare at least one input_ref")
        if not self.output_refs:
            raise ValueError("factor must declare at least one output_ref")
        if any(not str(ref) for ref in (*self.input_refs, *self.output_refs)):
            raise ValueError("factor refs must be non-empty strings")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Factor":
        """Build a factor from serialized properties or a factor view entry."""

        return cls(
            factor_id=str(value["factor_id"]),
            factor_type=str(value["factor_type"]),
            name=str(value.get("name", value["factor_id"])),
            input_refs=_string_tuple(value.get("input_refs", value.get("inputs"))),
            output_refs=_string_tuple(value.get("output_refs", value.get("outputs"))),
            relation_kind=str(value.get("relation_kind", "joint_dependency")),
            model_kind=str(value.get("model_kind", "unknown")),
            model_ref=value.get("model_ref"),
            artifact_ref=value.get("artifact_ref"),
            validity_domain=value.get("validity_domain"),
            context_refs=_string_tuple(value.get("context_refs")),
            evidence_refs=_string_tuple(value.get("evidence_refs")),
            uncertainty=value.get("uncertainty"),
            verification_status=str(value.get("verification_status", "unverified")),
            source_run_ids=_string_tuple(value.get("source_run_ids")),
            artifact_hashes=value.get("artifact_hashes"),
            version=str(value.get("version", "1.0")),
            metadata=value.get("metadata", {}),
        )

    def to_properties(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "factor_id": self.factor_id,
            "factor_type": self.factor_type,
            "name": self.name,
            "input_refs": list(self.input_refs),
            "output_refs": list(self.output_refs),
            "relation_kind": self.relation_kind,
            "model_kind": self.model_kind,
            "context_refs": list(self.context_refs),
            "evidence_refs": list(self.evidence_refs),
            "verification_status": self.verification_status,
            "source_run_ids": list(self.source_run_ids),
            "version": self.version,
            "metadata": dict(self.metadata),
        }
        for key, value in (
            ("model_ref", self.model_ref),
            ("artifact_ref", self.artifact_ref),
            ("validity_domain", self.validity_domain),
            ("uncertainty", self.uncertainty),
            ("artifact_hashes", self.artifact_hashes),
        ):
            if value is not None:
                result[key] = value
        return result

    def to_dict(self) -> dict[str, Any]:
        """Serialize the factor using the canonical graph property shape."""

        return self.to_properties()


def add_factor_to_graph(graph: Any, factor: Factor, *, status: str | None = None) -> None:
    """Compile a Factor into the canonical graph as one node plus typed links."""

    node_id = f"Factor.{factor.factor_id}"
    graph.add_node(node_id, "factor", factor.to_properties(), status=status)
    edge_status = status
    for ref in factor.input_refs:
        graph.add_edge(
            ref,
            node_id,
            "factor_input",
            {"factor_id": factor.factor_id, "role": "input"},
            status=edge_status,
        )
    for ref in factor.output_refs:
        graph.add_edge(
            node_id,
            ref,
            "factor_output",
            {"factor_id": factor.factor_id, "role": "output"},
            status=edge_status,
        )
    # Keep provenance queryable using the existing evidence vocabulary as well
    # as the compact ``evidence_refs`` property on the factor node.
    for ref in factor.evidence_refs:
        graph.add_edge(
            ref,
            node_id,
            "supports",
            {"factor_id": factor.factor_id},
            status=edge_status,
        )
        graph.add_edge(
            node_id,
            ref,
            "supported_by",
            {"factor_id": factor.factor_id},
            status=edge_status,
        )


def _factor_nodes(graph: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [node for node in graph.get("nodes", []) if node.get("type") == "factor"]


def factor_view(graph: Mapping[str, Any]) -> dict[str, Any]:
    """Return the mathematical projection of one canonical graph.

    The returned object is a read-only projection; it is never a second source
    of truth.  Variables are collected from factor refs and factor links are
    retained for consumers that need to draw the dependency shape.
    """

    factors: list[dict[str, Any]] = []
    variable_ids: set[str] = set()
    factor_ids: set[str] = set()
    for node in _factor_nodes(graph):
        props = dict(node.get("properties", {}))
        inputs = [str(ref) for ref in props.get("input_refs", [])]
        outputs = [str(ref) for ref in props.get("output_refs", [])]
        variable_ids.update(inputs)
        variable_ids.update(outputs)
        factor_ids.add(str(node["id"]))
        factors.append(
            {
                "node_id": str(node["id"]),
                "factor_id": props.get("factor_id", str(node["id"]).removeprefix("Factor.")),
                "factor_type": props.get("factor_type"),
                "name": props.get("name"),
                "inputs": inputs,
                "outputs": outputs,
                "relation_kind": props.get("relation_kind"),
                "model_kind": props.get("model_kind"),
                "model_ref": props.get("model_ref"),
                "artifact_ref": props.get("artifact_ref"),
                "validity_domain": props.get("validity_domain"),
                "context_refs": list(props.get("context_refs", [])),
                "evidence_refs": list(props.get("evidence_refs", [])),
                "uncertainty": props.get("uncertainty"),
                "verification_status": props.get("verification_status"),
                "source_run_ids": list(props.get("source_run_ids", [])),
                "artifact_hashes": props.get("artifact_hashes"),
                "version": props.get("version"),
                "metadata": dict(props.get("metadata", {})),
            }
        )
    factors.sort(key=lambda item: str(item["factor_id"]))
    factor_edges = [
        dict(edge)
        for edge in graph.get("edges", [])
        if edge.get("type") in {"factor_input", "factor_output"}
        and (str(edge.get("source")) in factor_ids or str(edge.get("target")) in factor_ids)
    ]
    factor_edges.sort(key=lambda item: (str(item["source"]), str(item["target"]), str(item["type"])))
    return {
        "graph_id": graph.get("graph_id"),
        "graph_version": graph.get("graph_version"),
        "variables": sorted(variable_ids),
        "factors": factors,
        "edges": factor_edges,
        "metadata": {"view": "factor", "read_only": True},
    }


def audit_factor_graph(
    graph: Mapping[str, Any],
    *,
    required_factor_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Run generic factor closure checks without simulator-specific assumptions."""

    nodes = {str(node["id"]): node for node in graph.get("nodes", [])}
    edges = list(graph.get("edges", []))
    factor_nodes = _factor_nodes(graph)
    required = {f"Factor.{value}" for value in (required_factor_ids or ())}
    checks: dict[str, bool] = {
        "factor_nodes_exist": bool(factor_nodes),
        "required_factor_nodes_exist": required.issubset(nodes),
    }
    diagnostics: list[str] = []
    all_refs_resolve = True
    all_edges_match = True
    all_evidence_resolve = True
    all_artifact_hashes_match = True
    for node in factor_nodes:
        node_id = str(node["id"])
        props = node.get("properties", {})
        if props.get("factor_id") != node_id.removeprefix("Factor."):
            diagnostics.append(f"factor_id does not match node id: {node_id}")
        inputs = [str(ref) for ref in props.get("input_refs", [])]
        outputs = [str(ref) for ref in props.get("output_refs", [])]
        if any(ref not in nodes for ref in (*inputs, *outputs)):
            all_refs_resolve = False
        context_refs = [str(ref) for ref in props.get("context_refs", [])]
        if any(ref not in nodes for ref in context_refs):
            all_refs_resolve = False
        evidence_refs = [str(ref) for ref in props.get("evidence_refs", [])]
        if any(ref not in nodes for ref in evidence_refs):
            all_evidence_resolve = False
        input_edges = {
            str(edge.get("source"))
            for edge in edges
            if edge.get("type") == "factor_input" and edge.get("target") == node_id
        }
        output_edges = {
            str(edge.get("target"))
            for edge in edges
            if edge.get("type") == "factor_output" and edge.get("source") == node_id
        }
        if input_edges != set(inputs) or output_edges != set(outputs):
            all_edges_match = False
        hashes = props.get("artifact_hashes", {})
        metadata = graph.get("metadata", {})
        if isinstance(hashes, Mapping):
            for key, value in hashes.items():
                if key in metadata and metadata.get(key) != value:
                    all_artifact_hashes_match = False
        if props.get("verification_status") == "validated" and node.get("status") != "validated":
            diagnostics.append(f"validated factor has non-validated node status: {node_id}")
            all_edges_match = False
    checks["factor_refs_resolve"] = all_refs_resolve
    checks["factor_input_output_edges_match"] = all_edges_match
    checks["factor_evidence_refs_resolve"] = all_evidence_resolve
    checks["factor_artifact_hashes_match"] = all_artifact_hashes_match
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "counts": {"factors": len(factor_nodes)},
        "factor_ids": sorted(str(node["id"]) for node in factor_nodes),
        "diagnostics": diagnostics,
    }


__all__ = [
    "FACTOR_TYPES",
    "MODEL_KINDS",
    "Factor",
    "add_factor_to_graph",
    "factor_view",
    "audit_factor_graph",
]
