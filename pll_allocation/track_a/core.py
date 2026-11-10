"""Legacy import alias; implementation is owned by allocation."""
import importlib as _importlib
import sys as _sys
_sys.modules[__name__] = _importlib.import_module("pll_allocation.allocation.core")
