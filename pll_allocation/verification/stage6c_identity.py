"""Compatibility alias; implementation: pll_allocation/verification/nonideal_noise_identity.py."""
import sys
from . import nonideal_noise_identity as _implementation
sys.modules[__name__] = _implementation
