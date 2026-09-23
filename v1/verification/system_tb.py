"""Validation-mode SystemTB evaluator seam."""

from __future__ import annotations

from typing import Any, Mapping

from ..api.verification import VerificationRequest
from ..backends.protocol import SystemBackend


def run_system_tb(
    request: VerificationRequest, backend: SystemBackend
) -> Mapping[str, Any]:
    """Evaluate the same realized instance used by BlockTB."""

    return backend.evaluate_system(request)


__all__ = ["run_system_tb"]
