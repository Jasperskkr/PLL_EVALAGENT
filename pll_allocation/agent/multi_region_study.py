"""Compatibility import for studies.multi_region."""
import sys
from ..studies import multi_region as _implementation
sys.modules[__name__] = _implementation
