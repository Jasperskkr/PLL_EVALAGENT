"""Canonical BlockSpec verification service.

This module owns orchestration only.  A backend supplies BlockTB and SystemTB
observations; the service combines them with context closure and returns one
stable report.  Agent proposals and future circuit adapters should call this
function instead of importing the behavioral model directly.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from ..api.verification import VerificationReport, VerificationRequest
from ..backends.synthetic import SyntheticVCOBackend, SyntheticVCOConstraintBackend
from ..specs import VCORequirement
from .context import evaluate_context_coverage
from .constraints import evaluate_block_constraints
from .block_tb import run_block_tb
from .system_tb import run_system_tb
from .vco import check_vco_spec


BACKEND_REGISTRY = {
    SyntheticVCOBackend.backend_id: SyntheticVCOBackend,
    SyntheticVCOConstraintBackend.backend_id: SyntheticVCOConstraintBackend,
}

BlockJudgment = Callable[
    [VerificationRequest, Mapping[str, Any]],
    dict[str, Any],
]


def register_verification_backend(
    backend_id: str,
    factory: Callable[[], Any],
    *,
    replace: bool = False,
) -> None:
    """Register a measurement adapter without modifying verification flow."""

    if not backend_id:
        raise ValueError("backend_id must be non-empty")
    if backend_id in BACKEND_REGISTRY and not replace:
        raise ValueError(f"verification backend already registered: {backend_id}")
    BACKEND_REGISTRY[backend_id] = factory


def _judge_constraint_set(
    request: VerificationRequest,
    measurement: Mapping[str, Any],
) -> dict[str, Any]:
    verdict = evaluate_block_constraints(
        {"system_spec": request.system_spec.to_dict()},
        measurement["behavior_vector"],
        list(dict(request.block_spec).get("constraints", [])),
    )
    return {
        **verdict,
        "measurement_method": measurement["measurement_method"],
        "provenance": measurement["provenance"],
        "characterization_window": measurement["characterization_window"],
        "context": measurement["characterization_window"],
        "behavior_vector": dict(measurement["behavior_vector"]),
    }


def _judge_vco_requirement(
    request: VerificationRequest,
    measurement: Mapping[str, Any],
) -> dict[str, Any]:
    requirement = request.block_spec
    if not isinstance(requirement, VCORequirement):
        requirement = VCORequirement.from_dict(requirement)
    return check_vco_spec(request.system_spec, requirement, measurement)


JUDGMENT_REGISTRY: dict[str, BlockJudgment] = {
    "constraint_set": _judge_constraint_set,
    "vco_requirement": _judge_vco_requirement,
}


def register_block_judgment(
    judgment_id: str,
    judgment: BlockJudgment,
    *,
    replace: bool = False,
) -> None:
    """Register a BlockSpec judgment strategy for a backend adapter."""

    if not judgment_id:
        raise ValueError("judgment_id must be non-empty")
    if judgment_id in JUDGMENT_REGISTRY and not replace:
        raise ValueError(f"block judgment already registered: {judgment_id}")
    JUDGMENT_REGISTRY[judgment_id] = judgment


def _judge_block(
    request: VerificationRequest,
    measurement: Mapping[str, Any],
    backend: Any,
) -> dict[str, Any]:
    """Apply the judgment policy declared by the backend that measured."""

    judgment_id = backend.judgment
    judgment = JUDGMENT_REGISTRY.get(judgment_id)
    if judgment is None:
        available = ", ".join(sorted(JUDGMENT_REGISTRY))
        raise ValueError(
            f"backend {backend.backend_id!r} declares unsupported judgment "
            f"{judgment_id!r}; available: {available}"
        )
    return judgment(request, measurement)


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

    if backend is None:
        backend_type = BACKEND_REGISTRY.get(request.backend_id)
        if backend_type is None:
            available = ", ".join(sorted(BACKEND_REGISTRY))
            raise ValueError(
                f"unknown verification backend_id {request.backend_id!r}; "
                f"available: {available}"
            )
        selected_backend = backend_type()
    else:
        selected_backend = backend
    backend_id = selected_backend.backend_id
    measurement = dict(run_block_tb(request, selected_backend))
    block_tb = _judge_block(request, measurement, selected_backend)
    system_tb_raw = dict(run_system_tb(request, selected_backend))
    system_tb = _system_projection(system_tb_raw, keep_raw=request.keep_raw)
    system_checks = _aggregate_system_checks(system_tb)
    system_tb["checks"] = system_checks
    system_tb["measurement_method"] = "backend.evaluate_system"
    coverage = evaluate_context_coverage(
        request.operating_context,
        system_tb.get("trajectory_envelope", system_tb.get("context", {})),
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
            "backend": backend_id,
            "direction": "BlockSpec -> SystemSpec",
            "block_id": request.block_id,
            "deterministic": True,
            "realized_instance_shared_by_block_and_system_tb": True,
            "realized_instance": instance_description,
        },
    )
    return report.to_dict()


__all__ = [
    "register_block_judgment",
    "register_verification_backend",
    "verify_block_assignment",
]
