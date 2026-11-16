"""Compatibility import/worker for verification.continuous."""
import sys
from . import continuous as _implementation
if __name__ == '__main__':
    _implementation.main()
else:
    sys.modules[__name__] = _implementation
