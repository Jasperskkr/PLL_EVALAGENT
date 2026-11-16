"""Fixed regional executor tools; strategies submit decisions, never M1 judgments."""
from .contracts import validate_decision
from .assessment import assess_regions


def run_region_exploration(context_path, decisions_path, out, *, m1_budget):
    from .explorer import run_region_exploration as run
    return run(context_path, decisions_path, out, m1_budget=m1_budget)


def __getattr__(name):
    if name == 'RegionExplorer':
        from .explorer import RegionExplorer
        return RegionExplorer
    raise AttributeError(name)


__all__ = ['RegionExplorer', 'assess_regions', 'validate_decision', 'run_region_exploration']
