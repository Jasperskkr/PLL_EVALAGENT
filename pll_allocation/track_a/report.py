"""Compatibility alias; implementation: pll_allocation/_legacy/archive_report.py."""
import sys
from .._legacy import archive_report as _implementation
sys.modules[__name__] = _implementation
