"""Block-agnostic contracts for an allocation/verification closure run."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Mapping, Sequence


def jsonable(value: Any) -> Any:
    """Convert workflow payloads to deterministic JSON-compatible objects."""

    if is_dataclass(value):
        return {key: jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value


@dataclass(frozen=True)
class SpecClosureRequest:
    """Complete input boundary for one modular spec-closure workflow.

    The workflow core treats the system spec and base instance as opaque.  A
    block adapter interprets them.  This keeps VCO, CP, divider, behavioral
    models and future circuit references outside the orchestration layer.
    """

    workflow_id: str
    system_spec: Any
    base_instance: Any
    block_definition: Mapping[str, Any]
    allocation_problem: Mapping[str, Any]
    candidate_proposals: Sequence[Mapping[str, Any]]
    declared_operating_context: Mapping[str, Any] = field(default_factory=dict)
    policy: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "spec-closure-request-1.0",
            "workflow_id": self.workflow_id,
            "system_spec": jsonable(self.system_spec),
            "base_instance": jsonable(self.base_instance),
            "block_definition": jsonable(self.block_definition),
            "allocation_problem": jsonable(self.allocation_problem),
            "candidate_proposals": jsonable(self.candidate_proposals),
            "declared_operating_context": jsonable(
                self.declared_operating_context
            ),
            "policy": jsonable(self.policy),
        }


@dataclass(frozen=True)
class SpecClosureReport:
    """Canonical output of the modular allocation/verification workflow."""

    workflow_id: str
    status: str
    block_definition: Mapping[str, Any]
    baseline: Mapping[str, Any]
    operating_context: Mapping[str, Any]
    allocation: Mapping[str, Any]
    candidate_evaluations: Sequence[Mapping[str, Any]]
    selection: Mapping[str, Any]
    evidence: Mapping[str, Any]
    failure_reasons: Sequence[str]
    provenance: Mapping[str, Any]

    @property
    def passed(self) -> bool:
        return self.status == "passed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "spec-closure-report-1.0",
            "workflow_id": self.workflow_id,
            "status": self.status,
            "passed": self.passed,
            "block_definition": jsonable(self.block_definition),
            "baseline": jsonable(self.baseline),
            "operating_context": jsonable(self.operating_context),
            "allocation": jsonable(self.allocation),
            "candidate_evaluations": jsonable(self.candidate_evaluations),
            "selection": jsonable(self.selection),
            "evidence": jsonable(self.evidence),
            "failure_reasons": list(self.failure_reasons),
            "provenance": jsonable(self.provenance),
        }


__all__ = ["SpecClosureRequest", "SpecClosureReport", "jsonable"]
