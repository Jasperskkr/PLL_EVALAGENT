"""Compatibility alias; implementation: pll_allocation/verification/phase_step.py."""
import sys
from . import phase_step as _implementation
sys.modules[__name__] = _implementation
