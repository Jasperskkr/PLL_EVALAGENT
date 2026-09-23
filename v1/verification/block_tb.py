"""BlockTB evaluator seam."""

from __future__ import annotations

from typing import Any, Mapping

from ..api.verification import VerificationRequest
from ..backends.protocol import BlockBackend


def run_block_tb(
    request: VerificationRequest, backend: BlockBackend
) -> Mapping[str, Any]:
    """Delegate block measurement and requirement checks to the backend."""

    return backend.validate_block(request)


__all__ = ["run_block_tb"]
