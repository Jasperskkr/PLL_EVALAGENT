"""Canonical BlockSpec verification service.

This module owns orchestration only.  A backend supplies BlockTB and SystemTB
observations; the service combines them with context closure and returns one
stable report.  Agent proposals and future circuit adapters should call this
function instead of importing the behavioral model directly.
"""

from __future__ import annotations

from typing import Any, Mapping

from ..api.verification import VerificationReport, VerificationRequest
from ..backends.synthetic import SyntheticVCOBackend
from .context import evaluate_context_coverage
from .block_tb import run_block_tb
from .system_tb import run_system_tb


def _aggregate_system_checks(evaluation: Mapping[str, Any]) -> dict[str, bool]:
    contexts = list(evaluation.get("per_context", []))
    if not contexts:
        return {
            str(name): bool(value)
            for name, value in evaluation.get("checks", {}).items()
        }
    names = sorted(
        {
            str(name)
            for context in contexts
            for name in context.get("checks", {})
        }
    )
    return {
        name: all(bool(context.get("checks", {}).get(name, False)) for context in contexts)
        for name in names
    }


def _system_projection(
    evaluation: Mapping[str, Any], *, keep_raw: bool
) -> dict[str, Any]:
    if keep_raw:
        return dict(evaluation)
    return {key: value for key, value in evaluation.items() if key != "raw_results"}


def verify_block_assignment(
    request: VerificationRequest,
    *,
    backend: Any | None = None,
) -> dict[str, Any]:
    """Run BlockTB and validation-mode SystemTB for one assignment."""

    selected_backend = backend or SyntheticVCOBackend()
    block_tb = dict(run_block_tb(request, selected_backend))
    system_tb_raw = dict(run_system_tb(request, selected_backend))
    system_tb = _system_projection(system_tb_raw, keep_raw=request.keep_raw)
    system_checks = _aggregate_system_checks(system_tb)
    system_tb["checks"] = system_checks
    system_tb["measurement_method"] = "backend.evaluate_system"
    coverage = evaluate_context_coverage(
        request.operating_context,
        system_tb.get("context", {}),
    )

    failure_reasons = [
        f"BlockTB:{name}"
        for name, passed in block_tb.get("checks", {}).items()
        if not passed
    ]
    failure_reasons.extend(
        f"SystemTB:{name}"
        for name, passed in system_checks.items()
        if not passed
    )
    failure_reasons.extend(
        f"Context:{name}"
        for name, passed in coverage.get("checks", {}).items()
        if not passed
    )
    passed = bool(
        block_tb.get("passed")
        and system_tb.get("passed")
        and coverage.get("passed")
    )
    instance_description = (
        selected_backend.describe_instance(request)
        if hasattr(selected_backend, "describe_instance")
        else {"backend_instance": "opaque"}
    )
    report = VerificationReport(
        request_id=request.request_id,
        status="passed" if passed else "failed",
        block_tb=block_tb,
        system_tb=system_tb,
        context_coverage=coverage,
        failure_reasons=tuple(failure_reasons),
        provenance={
            "service": "v1.verification.service.verify_block_assignment",
            "backend": getattr(selected_backend, "backend_id", request.backend_id),
            "direction": "BlockSpec -> SystemSpec",
            "block_id": request.block_id,
            "deterministic": True,
            "realized_instance_shared_by_block_and_system_tb": True,
            "realized_instance": instance_description,
        },
    )
    return report.to_dict()


__all__ = ["verify_block_assignment"]
