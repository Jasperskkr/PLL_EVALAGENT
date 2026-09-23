"""Stable request/response objects exposed by the verification core."""

from .allocation import SpecAllocationRequest, SpecAllocationReport
from .verification import VerificationRequest, VerificationReport
from .workflow import SpecClosureRequest, SpecClosureReport

__all__ = [
    "SpecAllocationRequest",
    "SpecAllocationReport",
    "VerificationRequest",
    "VerificationReport",
    "SpecClosureRequest",
    "SpecClosureReport",
]
