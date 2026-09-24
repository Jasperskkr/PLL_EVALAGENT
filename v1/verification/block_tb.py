"""BlockTB evaluator seam."""

from __future__ import annotations

from typing import Any, Mapping

from ..api.verification import VerificationRequest
from ..backends.protocol import BlockBackend


def run_block_tb(
    request: VerificationRequest, backend: BlockBackend
) -> Mapping[str, Any]:
    """Collect block measurements from the backend; the service judges them."""

    return backend.measure_block(request)


__all__ = ["run_block_tb"]
