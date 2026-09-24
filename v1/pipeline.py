"""Backward-compatible facade for the pre-evaluation V1 API.

Core numerical and judgment implementations live in semantic modules now.
This module intentionally contains no business logic; it remains available
for existing runners and downstream users while they migrate imports.
"""

from .evaluation.scalar import (
    abstract_pn_evaluation,
    abstract_vco_parameter_evaluation,
    search_required_pn_boundary,
    search_required_scalar_boundary,
)
from .evaluation.system import (
    build_pll_params,
    evaluate_system,
    evaluate_system_residuals,
    strip_raw_results,
)
from .evaluation.vco import characterize_vco, measure_vco_behavior
from .evaluation.sensitivity import run_parameter_sweep, run_sensitivity_suite
from .io import write_csv, write_json
from .model.instances import (
    LEGACY_VCO_PARAMETER_ALIASES,
    build_vco_instance,
    canonical_vco_parameter,
    normalize_vco_overrides,
)
from .verification.vco import validate_vco_scalar_requirement, validate_vco_spec

__all__ = [
    "LEGACY_VCO_PARAMETER_ALIASES", "canonical_vco_parameter",
    "normalize_vco_overrides", "build_pll_params", "build_vco_instance",
    "evaluate_system_residuals", "evaluate_system", "characterize_vco",
    "write_json", "write_csv", "run_parameter_sweep", "run_sensitivity_suite",
    "abstract_pn_evaluation", "search_required_pn_boundary",
    "abstract_vco_parameter_evaluation", "search_required_scalar_boundary",
    "measure_vco_behavior", "validate_vco_spec", "validate_vco_scalar_requirement",
    "strip_raw_results",
]
