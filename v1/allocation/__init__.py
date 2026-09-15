"""Additive multi-parameter allocation interfaces."""

from .spec_vector import SpecVector, compile_spec_vector_to_vco
from .evaluator import evaluate_spec_vector

__all__ = ["SpecVector", "compile_spec_vector_to_vco", "evaluate_spec_vector"]

