"""Small backend protocols; numerical policy stays above this layer."""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from ..api.allocation import SpecAllocationRequest
from ..api.verification import VerificationRequest


class AllocationBackend(Protocol):
    backend_id: str

    def allocate(self, request: SpecAllocationRequest) -> Mapping[str, Any]:
        """Search/solve a SystemSpec and emit BlockSpec allocation evidence."""


class BlockBackend(Protocol):
    backend_id: str

    def validate_block(self, request: VerificationRequest) -> Mapping[str, Any]:
        """Measure a realized block and evaluate its BlockSpec."""


class SystemBackend(Protocol):
    backend_id: str

    def evaluate_system(self, request: VerificationRequest) -> Mapping[str, Any]:
        """Run SystemTB against the same realized instance."""


__all__ = ["AllocationBackend", "BlockBackend", "SystemBackend"]
