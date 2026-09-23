"""Schema checks for block definitions and untrusted candidate proposals."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..api.workflow import SpecClosureRequest


REQUIRED_VERIFICATION_ACTIONS = frozenset(
    {"block_tb", "system_tb", "context_coverage"}
)


def _object_list(value: Any, field_name: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{field_name} must be an array")
    result = list(value)
    if any(not isinstance(item, Mapping) for item in result):
        raise ValueError(f"{field_name} members must be objects")
    return result


def _unique_names(items: Sequence[Mapping[str, Any]], field_name: str) -> set[str]:
    names = [str(item.get("name", "")).strip() for item in items]
    if any(not name for name in names):
        raise ValueError(f"{field_name} members require name")
    if len(names) != len(set(names)):
        raise ValueError(f"{field_name} names must be unique")
    return set(names)


def validate_block_definition(definition: Mapping[str, Any]) -> None:
    """Validate the block contract consumed by the generic workflow.

    An Agent may propose this object, but it is not executable until this
    deterministic validator accepts its vocabulary and cross references.
    """

    required = (
        "schema_version",
        "block_id",
        "block_type",
        "design_variables",
        "behavior_metrics",
        "system_influences",
        "requirement_mapping",
    )
    missing = [name for name in required if name not in definition]
    if missing:
        raise ValueError(f"block definition missing field(s): {missing}")
    if definition["schema_version"] != "block-definition-1.0":
        raise ValueError("unsupported block definition schema")
    if not str(definition["block_id"]).strip():
        raise ValueError("block definition requires block_id")
    if not str(definition["block_type"]).strip():
        raise ValueError("block definition requires block_type")

    design_variables = _object_list(
        definition["design_variables"], "design_variables"
    )
    behavior_metrics = _object_list(
        definition["behavior_metrics"], "behavior_metrics"
    )
    influences = _object_list(
        definition["system_influences"], "system_influences"
    )
    if not design_variables or not behavior_metrics or not influences:
        raise ValueError(
            "block definition requires design variables, behavior metrics, and influences"
        )
    design_names = _unique_names(design_variables, "design_variables")
    behavior_names = _unique_names(behavior_metrics, "behavior_metrics")
    for item in design_variables + behavior_metrics:
        if not str(item.get("unit", "")).strip():
            raise ValueError(f"metric {item.get('name')} requires unit")

    requirement = definition["requirement_mapping"]
    if not isinstance(requirement, Mapping):
        raise ValueError("requirement_mapping must be an object")
    for name in (
        "block_requirement_id",
        "metric",
        "measured_metric",
        "system_requirement_id",
    ):
        if not str(requirement.get(name, "")).strip():
            raise ValueError(f"requirement_mapping requires {name}")
    if str(requirement["measured_metric"]) not in behavior_names:
        raise ValueError("requirement measured_metric is not a declared behavior metric")

    for influence in influences:
        for name in (
            "source_metric",
            "target_metric",
            "system_requirement_id",
            "system_check",
            "mechanism",
        ):
            if not str(influence.get(name, "")).strip():
                raise ValueError(f"system influence requires {name}")
        if str(influence["source_metric"]) not in behavior_names:
            raise ValueError("influence source_metric is not declared behavior")
    allocation_knob = str(requirement.get("search_knob", ""))
    if allocation_knob and allocation_knob not in design_names:
        raise ValueError("requirement search_knob is not a declared design variable")


def validate_candidate_proposal(
    proposal: Mapping[str, Any], *, block_id: str
) -> None:
    """Validate one deterministic or Agent-originated candidate proposal."""

    required = (
        "schema_version",
        "proposal_id",
        "candidate_id",
        "block_id",
        "source",
        "status",
        "design_vector",
        "rationale",
        "evidence_refs",
        "requested_verification",
    )
    missing = [name for name in required if name not in proposal]
    if missing:
        raise ValueError(f"candidate proposal missing field(s): {missing}")
    if proposal["schema_version"] != "candidate-proposal-1.0":
        raise ValueError("unsupported candidate proposal schema")
    if proposal["status"] != "proposed":
        raise ValueError("candidate proposal must enter as proposed")
    if str(proposal["block_id"]) != block_id:
        raise ValueError("candidate proposal targets a different block")
    if not str(proposal["candidate_id"]).strip():
        raise ValueError("candidate proposal requires candidate_id")
    if not isinstance(proposal["design_vector"], Mapping):
        raise ValueError("candidate design_vector must be an object")
    if not str(proposal["rationale"]).strip():
        raise ValueError("candidate proposal requires rationale")
    evidence_refs = proposal["evidence_refs"]
    if not isinstance(evidence_refs, list) or not evidence_refs:
        raise ValueError("candidate proposal requires evidence_refs")
    requested = proposal["requested_verification"]
    if not isinstance(requested, list):
        raise ValueError("requested_verification must be an array")
    missing_actions = REQUIRED_VERIFICATION_ACTIONS - set(requested)
    if missing_actions:
        raise ValueError(
            f"candidate proposal omits verification action(s): {sorted(missing_actions)}"
        )
    if proposal.get("declare_pass") or proposal.get("modify_system_spec"):
        raise ValueError("proposal cannot modify SystemSpec or declare PASS")


def validate_spec_closure_request(request: SpecClosureRequest) -> None:
    """Validate the outer envelope before replaceable providers are called."""

    if not request.workflow_id.strip():
        raise ValueError("workflow_id is required")
    if not isinstance(request.block_definition, Mapping):
        raise ValueError("block_definition seed must be an object")
    if not isinstance(request.allocation_problem, Mapping):
        raise ValueError("allocation_problem must be an object")
    if not isinstance(request.candidate_proposals, Sequence):
        raise ValueError("candidate_proposals must be an array")


__all__ = [
    "REQUIRED_VERIFICATION_ACTIONS",
    "validate_block_definition",
    "validate_candidate_proposal",
    "validate_spec_closure_request",
]
