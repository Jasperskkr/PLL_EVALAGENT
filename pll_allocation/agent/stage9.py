"""Compatibility import; implementation lives in agent.feedback."""
import sys
from . import feedback as _implementation
sys.modules[__name__] = _implementation
