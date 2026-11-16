"""Compatibility alias; implementation: pll_allocation/allocation/first_allocation.py."""
import sys
from ..allocation import first_allocation as _implementation
sys.modules[__name__] = _implementation
