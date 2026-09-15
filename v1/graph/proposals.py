"""Schema-constrained proposal objects for a future graph-building Agent."""

from __future__ import annotations

from typing import Any, Mapping

from .model import EDGE_TYPES, NODE_TYPES


PROPOSAL_ACTIONS = frozenset({"add_node", "add_edge", "modify_node", "modify_edge", "remove_node", "remove_edge"})
VERIFICATION_ACTIONS = frozenset(
    {
        "schema_validation",
        "unit_check",
        "block_tb",
        "parameter_sweep",
        "sensitivity",
        "system_tb",
        "independent_evaluator",
    }
)


def validate_graph_proposal(
    proposal: Mapping[str, Any],
    graph: Mapping[str, Any] | None = None,
) -> None:
    """Validate an Agent proposal without applying it to the canonical graph.

    A valid proposal is still only a hypothesis.  The Agent is not allowed to
    submit a terminal lifecycle status or a final PASS declaration.
    """

    for key in (
        "proposal_id",
        "action",
        "subject",
        "rationale",
        "evidence_ids",
        "requested_verification",
        "status",
    ):
        if key not in proposal:
            raise ValueError(f"graph proposal missing required field: {key}")
    if proposal["action"] not in PROPOSAL_ACTIONS:
        raise ValueError(f"unsupported graph proposal action: {proposal['action']}")
    if proposal["status"] != "proposed":
        raise ValueError("Agent graph proposal status must be proposed")
    if not str(proposal["rationale"]).strip():
        raise ValueError("graph proposal requires a rationale")
    if not isinstance(proposal["evidence_ids"], list) or not proposal["evidence_ids"]:
        raise ValueError("graph proposal requires at least one evidence id")
    requested = proposal["requested_verification"]
    if not isinstance(requested, list) or not requested:
        raise ValueError("graph proposal requires deterministic verification actions")
    unknown_verification = set(requested) - VERIFICATION_ACTIONS
    if unknown_verification:
        raise ValueError(
            f"unsupported verification action(s): {sorted(unknown_verification)}"
        )
    if proposal.get("declare_pass") or proposal.get("modify_system_spec"):
        raise ValueError("Agent cannot modify SystemSpec or declare PASS")

    subject = proposal["subject"]
    if not isinstance(subject, Mapping):
        raise ValueError("graph proposal subject must be an object")
    action = str(proposal["action"])
    if action.endswith("node"):
        if not subject.get("id"):
            raise ValueError("node proposal requires subject.id")
        if action == "add_node" and subject.get("type") not in NODE_TYPES:
            raise ValueError(f"unknown proposed node type: {subject.get('type')}")
        if action in {"modify_node", "remove_node"} and str(subject["id"]).startswith("SystemSpec."):
            raise ValueError("Agent cannot modify or remove SystemSpec nodes")
    else:
        for key in ("source", "target", "type"):
            if not subject.get(key):
                raise ValueError(f"edge proposal requires subject.{key}")
        if subject["type"] not in EDGE_TYPES:
            raise ValueError(f"unknown proposed edge type: {subject['type']}")
        if action in {"modify_edge", "remove_edge"} and str(subject["source"]).startswith("SystemSpec."):
            raise ValueError("Agent cannot modify or remove SystemSpec constraint edges")

    if graph is not None and action != "add_node":
        node_ids = {str(node.get("id")) for node in graph.get("nodes", [])}
        if action.endswith("edge"):
            for endpoint in ("source", "target"):
                if str(subject[endpoint]) not in node_ids:
                    raise ValueError(
                        f"proposal references unknown {endpoint}: {subject[endpoint]}"
                    )
        elif str(subject["id"]) not in node_ids:
            raise ValueError(f"proposal references unknown node: {subject['id']}")
