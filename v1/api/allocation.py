"""Stable input/output objects for forward SystemSpec allocation.

Allocation and verification are intentionally different contracts:

* allocation consumes a system requirement plus a search/design problem and
  produces one or more block requirements;
* verification consumes a concrete block requirement and a realized instance
  and reports whether the assignment closes at BlockTB and SystemTB.

The payload fields are mappings on purpose.  A future multi-block allocator
or an Agent can add a block-specific problem description without changing the
outer service boundary.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from typing import Any, Mapping

from ..specs import SystemSpec


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


@dataclass(frozen=True)
class SpecAllocationRequest:
    """Input boundary for one forward SystemSpec -> BlockSpec allocation."""

    system_spec: SystemSpec
    base_instance: Any
    operating_context: Mapping[str, Any]
    allocation_problem: Mapping[str, Any]
    block_id: str = "VCO"
    backend_id: str = "synthetic_vco_allocator_v1"
    request_id: str = "spec-allocation-request"
    keep_raw: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "spec-allocation-request-1.0",
            "request_id": self.request_id,
            "block_id": self.block_id,
            "backend_id": self.backend_id,
            "system_spec": _jsonable(self.system_spec.to_dict()),
            "base_instance": _jsonable(self.base_instance),
            "operating_context": _jsonable(self.operating_context),
            "allocation_problem": _jsonable(self.allocation_problem),
            "keep_raw": self.keep_raw,
        }


@dataclass(frozen=True)
class SpecAllocationReport:
    """Canonical result boundary for a forward allocation operation."""

    request_id: str
    status: str
    allocated_block_spec: Mapping[str, Any] | None
    recommended_block_spec: Mapping[str, Any] | None
    evidence: Mapping[str, Any]
    failure_reasons: tuple[str, ...]
    provenance: Mapping[str, Any]

    @property
    def allocated(self) -> bool:
        return self.status == "allocated"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "spec-allocation-report-1.0",
            "request_id": self.request_id,
            "status": self.status,
            "allocated": self.allocated,
            "allocated_block_spec": _jsonable(self.allocated_block_spec),
            "recommended_block_spec": _jsonable(self.recommended_block_spec),
            "evidence": _jsonable(self.evidence),
            "failure_reasons": list(self.failure_reasons),
            "provenance": _jsonable(self.provenance),
        }


__all__ = ["SpecAllocationRequest", "SpecAllocationReport"]
