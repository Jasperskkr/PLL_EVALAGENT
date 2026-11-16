"""Compatibility alias; implementation: pll_allocation/block_space/profiles.py."""
import sys
from . import profiles as _implementation
sys.modules[__name__] = _implementation
