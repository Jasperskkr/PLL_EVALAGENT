"""Single formal config location, independent of working directory and research trees."""
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[2]
CONFIGS = PROJECT/'configs'
if not CONFIGS.is_dir():
    CONFIGS = Path(sys.prefix)/'share/pll-allocation/configs'
