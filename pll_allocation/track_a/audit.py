"""Compatibility alias; implementation: pll_allocation/_legacy/archive_audit.py."""
import sys
from .._legacy import archive_audit as _implementation
sys.modules[__name__] = _implementation
