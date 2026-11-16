"""Compatibility alias; implementation: pll_allocation/studies/simulated_repairs.py."""
import sys
from ..studies import simulated_repairs as _implementation
sys.modules[__name__] = _implementation
