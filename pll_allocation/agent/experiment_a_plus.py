"""Compatibility import for studies.initial_allocation."""
import sys
from ..studies import initial_allocation as _implementation
sys.modules[__name__] = _implementation
