"""Canonical forward SystemSpec -> BlockSpec allocation service.

This is deliberately separate from :mod:`v1.verification.service`.  The
allocator searches a system-level boundary and emits a block requirement;
verification only checks a concrete requirement against a realized instance.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Mapping

from ..api.allocation import SpecAllocationReport, SpecAllocationRequest
from ..backends.synthetic import SyntheticVCOAllocationBackend


def allocate_system_spec(
    request: SpecAllocationRequest,
    *,
    backend: Any | None = None,
) -> dict[str, Any]:
    """Allocate a BlockSpec from a SystemSpec and return one stable report."""

    selected_backend = backend or SyntheticVCOAllocationBackend()
    try:
        result = dict(selected_backend.allocate(request))
        report = SpecAllocationReport(
            request_id=request.request_id,
            status="allocated",
            allocated_block_spec=result["required"],
            recommended_block_spec=result.get("recommended"),
            evidence={
                "direction": "SystemSpec -> BlockSpec",
                "boundary": result["boundary"],
                "allocation_problem": dict(request.allocation_problem),
            },
            failure_reasons=(),
            provenance={
                "service": "v1.allocation.service.allocate_system_spec",
                "backend": getattr(selected_backend, "backend_id", request.backend_id),
                "deterministic": True,
                "realized_instance_used_for_boundary": asdict(request.base_instance)
                if hasattr(request.base_instance, "__dataclass_fields__")
                else request.base_instance,
            },
        )
    except Exception as exc:
        report = SpecAllocationReport(
            request_id=request.request_id,
            status="rejected",
            allocated_block_spec=None,
            recommended_block_spec=None,
            evidence={
                "direction": "SystemSpec -> BlockSpec",
                "allocation_problem": dict(request.allocation_problem),
            },
            failure_reasons=(f"Allocation:{type(exc).__name__}:{exc}",),
            provenance={
                "service": "v1.allocation.service.allocate_system_spec",
                "backend": getattr(selected_backend, "backend_id", request.backend_id),
                "deterministic": True,
            },
        )
    return report.to_dict()


__all__ = ["SyntheticVCOAllocationBackend", "allocate_system_spec"]
