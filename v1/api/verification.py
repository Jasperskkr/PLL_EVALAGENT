"""JSON-friendly API objects for block-assignment verification.

The request deliberately keeps the system requirement, block requirement,
realized instance and operating context separate.  A future circuit backend
can replace ``realized_instance`` with an instance reference while preserving
the same outer contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..io import jsonable
from ..specs import SystemSpec, VCORequirement


@dataclass(frozen=True)
class VerificationRequest:
    """Input boundary for one BlockTB + SystemTB verification."""

    system_spec: SystemSpec
    block_spec: VCORequirement | Mapping[str, Any]
    realized_instance: Any
    operating_context: Mapping[str, Any]
    block_id: str = "VCO"
    backend_id: str = "synthetic_vco_v1"
    request_id: str = "verification-request"
    keep_raw: bool = False

    def to_dict(self) -> dict[str, Any]:
        system_payload = self.system_spec.to_dict()
        block_payload = (
            self.block_spec.to_dict()
            if hasattr(self.block_spec, "to_dict")
            else dict(self.block_spec)
        )
        return {
            "schema_version": "verification-request-1.0",
            "request_id": self.request_id,
            "block_id": self.block_id,
            "backend_id": self.backend_id,
            "system_spec": jsonable(system_payload),
            "block_spec": jsonable(block_payload),
            "realized_instance": jsonable(self.realized_instance),
            "operating_context": jsonable(self.operating_context),
            "keep_raw": self.keep_raw,
        }


@dataclass(frozen=True)
class VerificationReport:
    """Canonical result boundary used by runners and future Agent tools."""

    request_id: str
    status: str
    block_tb: Mapping[str, Any]
    system_tb: Mapping[str, Any]
    context_coverage: Mapping[str, Any]
    failure_reasons: tuple[str, ...]
    provenance: Mapping[str, Any]

    @property
    def passed(self) -> bool:
        return self.status == "passed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "verification-report-1.0",
            "request_id": self.request_id,
            "status": self.status,
            "passed": self.passed,
            "block_tb": jsonable(self.block_tb),
            "system_tb": jsonable(self.system_tb),
            "context_coverage": jsonable(self.context_coverage),
            "failure_reasons": list(self.failure_reasons),
            "provenance": jsonable(self.provenance),
        }


__all__ = ["VerificationRequest", "VerificationReport"]
