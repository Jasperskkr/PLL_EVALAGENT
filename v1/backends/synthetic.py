"""Adapters for the current deterministic Python behavioral model."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Mapping

from ..api.allocation import SpecAllocationRequest
from ..api.verification import VerificationRequest
from ..evaluation.constraints import behavior_vector
from ..evaluation.system import evaluate_system
from ..evaluation.vco import measure_vco_behavior
from ..evaluation.scalar import search_required_pn_boundary
from ..model.instances import build_vco_instance
from ..model.pll_behavioral import VCOParams
from ..specs import VCORequirement


class SyntheticVCOAllocationBackend:
    """Deterministic V1 forward allocator backed by the behavioral model."""

    backend_id = "synthetic_vco_allocator_v1"

    def allocate(self, request: SpecAllocationRequest) -> Mapping[str, Any]:
        if not isinstance(request.base_instance, VCOParams):
            raise TypeError("synthetic allocator expects a VCOParams base instance")
        problem = dict(request.allocation_problem)
        boundary = search_required_pn_boundary(
            request.system_spec,
            request.base_instance,
            float(problem.get("loose_bound_dbc_hz", -110.0)),
            float(problem.get("tight_bound_dbc_hz", -125.0)),
            int(problem.get("iterations", 24)),
        )
        boundary_instance = build_vco_instance(
            request.base_instance,
            {boundary["search_knob"]: boundary["search_knob_boundary"]},
        )
        measurement = measure_vco_behavior(
            request.system_spec,
            boundary_instance,
            request.operating_context,
        )
        initial = VCORequirement.from_dict(problem["initial_block_spec"])
        required = VCORequirement(
            phase_noise_1mhz_max_dbc_hz=float(
                measurement["worst_case"]["worst_phase_noise_1mhz_dbc_hz"]
            ),
            tuning_range_min_hz=initial.tuning_range_min_hz,
            kvco_min_hz_per_v=initial.kvco_min_hz_per_v,
            kvco_max_hz_per_v=initial.kvco_max_hz_per_v,
            power_max_w=initial.power_max_w,
            margin_db=0.0,
        )
        margin_db = float(problem.get("recommended_margin_db", 0.0))
        recommended = VCORequirement(
            phase_noise_1mhz_max_dbc_hz=required.phase_noise_1mhz_max_dbc_hz - margin_db,
            tuning_range_min_hz=required.tuning_range_min_hz,
            kvco_min_hz_per_v=required.kvco_min_hz_per_v,
            kvco_max_hz_per_v=required.kvco_max_hz_per_v,
            power_max_w=required.power_max_w,
            margin_db=margin_db,
        )
        return {
            "boundary": {
                **boundary,
                "block_metric_at_boundary": required.phase_noise_1mhz_max_dbc_hz,
                "boundary_block_measurement": {
                    "context": measurement["context"],
                    "worst_case": measurement["worst_case"],
                    "measurement_method": measurement["measurement_method"],
                    "provenance": measurement["provenance"],
                },
            },
            "required": required.to_dict(),
            "recommended": recommended.to_dict(),
        }


class SyntheticVCOBackend:
    """Measure the existing VCO/SystemTB implementation behind stable seams."""

    backend_id = "synthetic_vco_v1"
    judgment = "vco_requirement"

    @staticmethod
    def _instance(request: VerificationRequest) -> VCOParams:
        instance = request.realized_instance
        if isinstance(instance, VCOParams):
            return instance
        if isinstance(instance, Mapping):
            return VCOParams(**dict(instance))
        raise TypeError("synthetic_vco_v1 expects VCOParams or a parameter mapping")

    def measure_block(self, request: VerificationRequest) -> Mapping[str, Any]:
        """Observe realized block behavior; BlockSpec judgment stays above."""

        return measure_vco_behavior(
            request.system_spec,
            self._instance(request),
            request.operating_context,
        )

    def evaluate_system(self, request: VerificationRequest) -> Mapping[str, Any]:
        return evaluate_system(
            request.system_spec,
            self._instance(request),
            keep_raw=request.keep_raw,
        )

    def describe_instance(self, request: VerificationRequest) -> Mapping[str, Any]:
        return {"model": self.backend_id, "parameters": asdict(self._instance(request))}


class SyntheticVCOConstraintBackend(SyntheticVCOBackend):
    """V1.5 adapter measuring the declarative behavior-vector vocabulary."""

    backend_id = "synthetic_vco_v1_constraint_set"
    judgment = "constraint_set"

    def measure_block(self, request: VerificationRequest) -> Mapping[str, Any]:
        measurement = measure_vco_behavior(
            request.system_spec,
            self._instance(request),
            request.operating_context,
            vctrl_points=int(request.operating_context.get("vctrl_points", 11)),
        )
        return {**measurement, "behavior_vector": behavior_vector(measurement)}


__all__ = [
    "SyntheticVCOAllocationBackend",
    "SyntheticVCOBackend",
    "SyntheticVCOConstraintBackend",
]
