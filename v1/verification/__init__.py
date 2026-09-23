"""Deterministic verification service and TB projections."""

from .context import evaluate_context_coverage
from .block_tb import run_block_tb
from .system_tb import run_system_tb

def __getattr__(name: str):
    if name == "verify_block_assignment":
        from .service import verify_block_assignment

        return verify_block_assignment
    raise AttributeError(name)


__all__ = [
    "evaluate_context_coverage",
    "run_block_tb",
    "run_system_tb",
    "verify_block_assignment",
]
