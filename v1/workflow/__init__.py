"""Modular allocation/verification workflow and replaceable stage protocols."""

from .service import WorkflowModules, run_spec_closure
from .modules import (
    GraphEvidenceFinalizer,
    MinimumCostPassingSelector,
    StaticBlockDefinitionProvider,
    StaticCandidateProvider,
)

__all__ = [
    "GraphEvidenceFinalizer",
    "MinimumCostPassingSelector",
    "StaticBlockDefinitionProvider",
    "StaticCandidateProvider",
    "WorkflowModules",
    "run_spec_closure",
]
