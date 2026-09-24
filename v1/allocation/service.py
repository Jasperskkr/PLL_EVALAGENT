"""Canonical forward SystemSpec -> BlockSpec allocation service.

This is deliberately separate from :mod:`v1.verification.service`.  The
allocator searches a system-level boundary and emits a block requirement;
verification only checks a concrete requirement against a realized instance.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Callable

from ..api.allocation import SpecAllocationReport, SpecAllocationRequest
from ..backends.synthetic import SyntheticVCOAllocationBackend


BACKEND_REGISTRY = {
    SyntheticVCOAllocationBackend.backend_id: SyntheticVCOAllocationBackend,
}


def register_allocation_backend(
    backend_id: str,
    factory: Callable[[], Any],
    *,
    replace: bool = False,
) -> None:
    """Register an allocation adapter without changing service orchestration."""

    if not backend_id:
        raise ValueError("backend_id must be non-empty")
    if backend_id in BACKEND_REGISTRY and not replace:
        raise ValueError(f"allocation backend already registered: {backend_id}")
    BACKEND_REGISTRY[backend_id] = factory


def allocate_system_spec(
    request: SpecAllocationRequest,
    *,
    backend: Any | None = None,
) -> dict[str, Any]:
    """Allocate a BlockSpec from a SystemSpec and return one stable report."""

    if backend is None:
        backend_type = BACKEND_REGISTRY.get(request.backend_id)
        if backend_type is None:
            available = ", ".join(sorted(BACKEND_REGISTRY))
            raise ValueError(
                f"unknown allocation backend_id {request.backend_id!r}; "
                f"available: {available}"
            )
        selected_backend = backend_type()
    else:
        selected_backend = backend
    backend_id = selected_backend.backend_id
    allocate = selected_backend.allocate
    try:
        result = dict(allocate(request))
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
                "backend": backend_id,
                "deterministic": True,
                "realized_instance_used_for_boundary": asdict(request.base_instance)
                if hasattr(request.base_instance, "__dataclass_fields__")
                else request.base_instance,
            },
        )
    except (TypeError, ValueError) as exc:
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
                "backend": backend_id,
                "deterministic": True,
            },
        )
    return report.to_dict()


__all__ = ["allocate_system_spec", "register_allocation_backend"]
