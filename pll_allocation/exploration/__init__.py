"""Configurable M1 exploration; no LLM or M2 execution."""
from .contracts import load_problem, resolve_problem, make_parameters, check_candidate


def run_exploration(problem_path, out, *, seed=None, budget=None):
    """Shared CLI/GUI interface. Refuses an existing output directory."""
    from .engine import run_exploration as run
    return run(problem_path, out, seed=seed, budget=budget)


def load_physics_context(path):
    from .engine import load_physics_context as load
    return load(path)


__all__ = ['load_problem', 'resolve_problem', 'make_parameters', 'check_candidate', 'run_exploration', 'load_physics_context']
