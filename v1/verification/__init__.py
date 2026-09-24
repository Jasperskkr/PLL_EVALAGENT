"""Deterministic verification service and TB projections."""

from .context import evaluate_context_coverage
from .block_tb import run_block_tb
from .system_tb import run_system_tb
from .service import (
    register_block_judgment,
    register_verification_backend,
    verify_block_assignment,
)


__all__ = [
    "evaluate_context_coverage",
    "run_block_tb",
    "run_system_tb",
    "register_block_judgment",
    "register_verification_backend",
    "verify_block_assignment",
]
