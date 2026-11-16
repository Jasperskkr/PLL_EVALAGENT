"""Compatibility alias; implementation: pll_allocation/verification/phase_step_native.py."""
import sys
from . import phase_step_native as _implementation
sys.modules[__name__] = _implementation
