"""Compatibility alias; implementation: pll_allocation/verification/nonideal.py."""
import sys
from . import nonideal as _implementation
sys.modules[__name__] = _implementation
