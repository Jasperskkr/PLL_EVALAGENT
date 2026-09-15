"""Schema-constrained Agent actions; execution remains deterministic."""

from __future__ import annotations

from typing import Any, Mapping


ALLOWED_ACTIONS = frozenset(
    {
        "add_field",
        "remove_field",
        "add_context",
        "remove_context",
        "add_dependency",
        "remove_dependency",
        "change_representation",
        "modify_validity",
        "tighten_spec",
        "relax_spec",
        "adjust_range",
        "select_search_region",
    }
)


def validate_agent_action(action: Mapping[str, Any]) -> None:
    action_type = action.get("action")
    if action_type not in ALLOWED_ACTIONS:
        raise ValueError(f"unsupported Agent action: {action_type}")
    if not action.get("target"):
        raise ValueError("Agent action requires target")
    if action_type not in {"remove_field", "remove_context", "remove_dependency"}:
        if not action.get("evidence_ids"):
            raise ValueError("non-removal Agent action requires evidence_ids")
    if action.get("modify_system_spec") or action.get("declare_pass"):
        raise ValueError("Agent cannot modify SystemSpec or declare PASS")

