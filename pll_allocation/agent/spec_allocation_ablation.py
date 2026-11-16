"""Compatibility import for studies.ablation."""
import sys
from ..studies import ablation as _implementation
sys.modules[__name__] = _implementation
