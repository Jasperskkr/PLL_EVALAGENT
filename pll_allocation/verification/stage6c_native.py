"""Compatibility alias; implementation: pll_allocation/verification/nonideal_noise_native.py."""
import sys
from . import nonideal_noise_native as _implementation
sys.modules[__name__] = _implementation
