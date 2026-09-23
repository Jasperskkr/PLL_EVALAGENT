"""Additive multi-parameter allocation interfaces."""

from .design_space import AxisDefinition, DesignPointDefinition, DesignSpaceDefinition
from .design_vector import DesignVector, compile_design_vector_to_vco
from .boundaries import build_system_boundary_map
from .boundary_contract import extract_boundary_block_contract
from .conditional_allocation import (
    build_conditional_block_spec_map,
    validate_conditional_block_spec_map,
    validate_conditional_contract_prediction,
)
from .evaluator import evaluate_design_vector
from .multidim_evaluator import evaluate_context_coverage, evaluate_design_point
from .regions import build_capability_region, build_system_feasible_region
from .selection import build_replay_evidence, select_candidate
from .service import SyntheticVCOAllocationBackend, allocate_system_spec

__all__ = [
    "AxisDefinition",
    "DesignPointDefinition",
    "DesignSpaceDefinition",
    "DesignVector",
    "build_system_boundary_map",
    "extract_boundary_block_contract",
    "build_conditional_block_spec_map",
    "validate_conditional_block_spec_map",
    "validate_conditional_contract_prediction",
    "compile_design_vector_to_vco",
    "evaluate_design_vector",
    "evaluate_context_coverage",
    "evaluate_design_point",
    "build_capability_region",
    "build_system_feasible_region",
    "build_replay_evidence",
    "select_candidate",
    "SyntheticVCOAllocationBackend",
    "allocate_system_spec",
]
