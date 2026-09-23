"""Replaceable stages of the block-agnostic spec-closure workflow."""

from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence

from ..api.workflow import SpecClosureRequest


class BlockDefinitionProvider(Protocol):
    module_id: str

    def resolve(self, request: SpecClosureRequest) -> Mapping[str, Any]:
        """Return a proposed block definition for deterministic validation."""


class BaselineEvaluator(Protocol):
    module_id: str

    def evaluate(self, request: SpecClosureRequest) -> Mapping[str, Any]:
        """Evaluate the starting system/block realization."""


class ContextBuilder(Protocol):
    module_id: str

    def build(
        self,
        request: SpecClosureRequest,
        baseline: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Freeze the operating context before allocation/candidate testing."""


class AllocationModule(Protocol):
    module_id: str

    def allocate(
        self,
        request: SpecClosureRequest,
        baseline: Mapping[str, Any],
        operating_context: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Produce an allocated BlockSpec and deterministic evidence."""


class CandidateProvider(Protocol):
    module_id: str

    def propose(
        self,
        request: SpecClosureRequest,
        allocation: Mapping[str, Any],
    ) -> Sequence[Mapping[str, Any]]:
        """Return untrusted candidate proposals; an Agent may implement this."""


class CandidateRealizer(Protocol):
    module_id: str

    def realize(
        self,
        request: SpecClosureRequest,
        proposal: Mapping[str, Any],
    ) -> Any:
        """Compile a proposed design vector into a model/circuit instance."""


class AssignmentVerifier(Protocol):
    module_id: str

    def verify(
        self,
        request: SpecClosureRequest,
        allocation: Mapping[str, Any],
        proposal: Mapping[str, Any],
        realized_instance: Any,
        operating_context: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Run deterministic BlockTB/SystemTB closure for one instance."""


class CandidateSelector(Protocol):
    module_id: str

    def select(
        self,
        request: SpecClosureRequest,
        candidate_evaluations: Sequence[Mapping[str, Any]],
    ) -> Mapping[str, Any]:
        """Select one passing candidate using an explicit policy."""


class EvidenceFinalizer(Protocol):
    module_id: str

    def finalize(
        self,
        request: SpecClosureRequest,
        block_definition: Mapping[str, Any],
        baseline: Mapping[str, Any],
        operating_context: Mapping[str, Any],
        allocation: Mapping[str, Any],
        candidate_evaluations: Sequence[Mapping[str, Any]],
        selection: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Compile and audit schema/graph evidence for the complete run."""


__all__ = [
    "AllocationModule",
    "AssignmentVerifier",
    "BaselineEvaluator",
    "BlockDefinitionProvider",
    "CandidateProvider",
    "CandidateRealizer",
    "CandidateSelector",
    "ContextBuilder",
    "EvidenceFinalizer",
]
