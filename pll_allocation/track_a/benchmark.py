"""Compatibility alias; implementation: pll_allocation/studies/allocation_baselines.py."""
import sys
from ..studies import allocation_baselines as _implementation
sys.modules[__name__] = _implementation
