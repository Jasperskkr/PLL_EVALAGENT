"""Compatibility import for studies.ablation_report."""
import sys
from ..studies import ablation_report as _implementation
sys.modules[__name__] = _implementation
