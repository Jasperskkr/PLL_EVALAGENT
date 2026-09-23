"""Conditional V1.5 BlockSpec allocation and per-slice validation.

This module applies an explicit engineering-margin policy to the measured
boundary behavior contract.  It emits a discrete ``PN_spec(k1)`` table and
validates one least-overdesigned sampled candidate for every mapped k1 slice.
It does not interpolate across k1 or invent requirements for unmapped slices.
"""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Dict, Mapping, Sequence

from ..api.verification import VerificationRequest
from ..backends.synthetic import SyntheticVCOBackend
from ..model.pll_behavioral import VCOParams
from ..specs import SystemSpec, VCORequirement
from ..verification.service import verify_block_assignment
from .design_space import DesignPointDefinition, DesignSpaceDefinition
from .multidim_evaluator import evaluate_design_point


ALLOCATION_METHOD = "boundary_measured_behavior_minus_fixed_margin"
VALIDATION_METHOD = "per_condition_least_overdesign_independent_replay"
ALLOCATION_STATUS = "allocated_on_mapped_slices"
WORKFLOW_OUTCOME = "conditional_block_spec_allocated_and_validated_on_mapped_slices"


def _digest(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def build_conditional_block_spec_map(
    *,
    case: Mapping[str, Any],
    boundary_block_contract: Mapping[str, Any],
) -> Dict[str, Any]:
    """Allocate a discrete measured-PN requirement for every mapped k1."""

    config = dict(case.get("conditional_block_spec_allocation", {}))
    if config.get("status") != "enabled":
        raise ValueError("conditional BlockSpec allocation is not enabled")
    if config.get("method") != ALLOCATION_METHOD:
        raise ValueError(
            f"unsupported conditional allocation method: {config.get('method')}"
        )
    if config.get("condition_axis") != boundary_block_contract[
        "condition_axis"
    ]["name"]:
        raise ValueError("conditional allocation axis does not match the contract")
    if config.get("allocated_measured_metric") != (
        "worst_phase_noise_1mhz_dbc_hz"
    ):
        raise ValueError("V1.5 conditional allocation must use measured worst PN")
    if config.get("requirement_metric") != "phase_noise_1mhz_max_dbc_hz":
        raise ValueError("V1.5 conditional allocation requirement is not PN")
    if config.get("direction") != "upper_bound_more_negative_is_tighter":
        raise ValueError("unsupported conditional PN requirement direction")
    if config.get("interpolation_allowed") is not False:
        raise ValueError("conditional BlockSpec interpolation must remain disabled")

    margin_policy = dict(config.get("engineering_margin", {}))
    if margin_policy.get("type") != "fixed_db":
        raise ValueError("V1.5 currently supports only an explicit fixed-dB margin")
    margin_db = float(margin_policy.get("value_db", 0.0))
    if margin_db <= 0.0:
        raise ValueError("engineering margin must be positive")

    power_limit = float(case["system_spec"]["limits"]["power_max_w"])
    entries: list[Dict[str, Any]] = []
    for contract_entry in boundary_block_contract.get("entries", []):
        behavior = contract_entry["measured_block_behavior"]
        boundary_worst_pn = float(
            behavior["worst_phase_noise_1mhz_dbc_hz"]
        )
        allocated_pn = boundary_worst_pn - margin_db
        required = VCORequirement(
            phase_noise_1mhz_max_dbc_hz=boundary_worst_pn,
            power_max_w=power_limit,
            margin_db=0.0,
        )
        recommended = VCORequirement(
            phase_noise_1mhz_max_dbc_hz=allocated_pn,
            power_max_w=power_limit,
            margin_db=margin_db,
        )
        entries.append(
            {
                "condition": dict(contract_entry["condition"]),
                "condition_semantics": "candidate_design_knob",
                "source_boundary": dict(
                    contract_entry["source_system_boundary"]
                ),
                "source_boundary_behavior": dict(behavior),
                "required_block_spec_at_boundary": required.to_dict(),
                "allocated_block_spec": recommended.to_dict(),
                "allocation_derivation": {
                    "measured_metric": "worst_phase_noise_1mhz_dbc_hz",
                    "boundary_measured_value_dbc_hz": boundary_worst_pn,
                    "engineering_margin_db": margin_db,
                    "allocated_value_dbc_hz": allocated_pn,
                    "equation": (
                        "allocated_phase_noise_max = "
                        "boundary_worst_measured_phase_noise - margin_db"
                    ),
                },
            }
        )

    expected_count = int(boundary_block_contract["entry_count"])
    checks = {
        "source_contract_validated": bool(
            boundary_block_contract.get("validation", {}).get("passed")
        ),
        "all_contract_entries_allocated": len(entries) == expected_count,
        "one_unique_entry_per_condition": len(
            {float(item["condition"]["value"]) for item in entries}
        )
        == len(entries),
        "margin_applied_exactly": bool(entries)
        and all(
            item["allocated_block_spec"][
                "phase_noise_1mhz_max_dbc_hz"
            ]
            == item["source_boundary_behavior"][
                "worst_phase_noise_1mhz_dbc_hz"
            ]
            - margin_db
            for item in entries
        ),
        "all_allocated_specs_are_tighter": bool(entries)
        and all(
            item["allocated_block_spec"][
                "phase_noise_1mhz_max_dbc_hz"
            ]
            < item["required_block_spec_at_boundary"][
                "phase_noise_1mhz_max_dbc_hz"
            ]
            for item in entries
        ),
        "unmapped_slices_not_allocated": len(
            boundary_block_contract.get("unmapped_slices", [])
        )
        == boundary_block_contract["validation"]["unmapped_slice_count"],
    }
    validation = {
        "passed": all(checks.values()),
        "checks": checks,
        "allocated_entry_count": len(entries),
        "unallocated_slice_count": len(
            boundary_block_contract.get("unmapped_slices", [])
        ),
    }
    if not validation["passed"]:
        failed = sorted(name for name, passed in checks.items() if not passed)
        raise ValueError(f"conditional BlockSpec allocation failed: {failed}")

    artifact: Dict[str, Any] = {
        "schema_version": "v1.5-conditional-block-spec-map-1.0",
        "case_id": str(case["case_id"]),
        "allocation_id": "VCO.conditional_phase_noise_requirement.v1_5",
        "status": ALLOCATION_STATUS,
        "candidate_validation_required": True,
        "candidate_validation_artifact_ref": (
            "conditional_candidate_validation.json"
        ),
        "method": ALLOCATION_METHOD,
        "condition_axis": dict(boundary_block_contract["condition_axis"]),
        "allocated_measured_metric": "worst_phase_noise_1mhz_dbc_hz",
        "requirement_metric": "phase_noise_1mhz_max_dbc_hz",
        "direction": "upper_bound_more_negative_is_tighter",
        "engineering_margin": {
            "type": "fixed_db",
            "value_db": margin_db,
            "policy_source": margin_policy.get("policy_source"),
            "data_derived": False,
        },
        "contract_form": "discrete_conditional_table",
        "interpolation_allowed": False,
        "entry_count": len(entries),
        "entries": entries,
        "unallocated_slices": [
            {
                **dict(item),
                "allocation_status": "no_allocatable_system_region",
            }
            for item in boundary_block_contract.get("unmapped_slices", [])
        ],
        "source_boundary_block_contract_sha256": boundary_block_contract[
            "contract_sha256"
        ],
        "validation": validation,
        "claim_boundary": (
            "Conditional measured-PN BlockSpec allocated only for the listed "
            "validated k1 slices using an explicit fixed engineering margin; "
            "no interpolation, global k1 requirement, or transistor-level "
            "signoff is claimed."
        ),
        "provenance": {
            "builder": (
                "v1.allocation.conditional_allocation."
                "build_conditional_block_spec_map"
            ),
            "deterministic": True,
            "random_seed": None,
        },
    }
    artifact["block_spec_map_sha256"] = _digest(artifact)
    return artifact


def _same_replay(
    sampled: Mapping[str, Any], replay: Mapping[str, Any]
) -> Dict[str, bool]:
    return {
        "design_vector_identical": sampled["design_vector"]
        == replay["design_vector"],
        "realized_instance_identical": sampled["realized_instance"]
        == replay["realized_instance"],
        "behavior_vector_identical": sampled["behavior_vector"]
        == replay["behavior_vector"],
        "block_tb_identical": sampled["block_tb"] == replay["block_tb"],
        "system_tb_identical": sampled["system_tb"] == replay["system_tb"],
        "context_coverage_identical": sampled["context_coverage"]
        == replay["context_coverage"],
        "status_identical": sampled["status"] == replay["status"],
    }


def validate_conditional_block_spec_map(
    *,
    case: Mapping[str, Any],
    system_boundary_map: Mapping[str, Any],
    conditional_block_spec_map: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    design_space: DesignSpaceDefinition,
    system_spec: SystemSpec,
    base_vco: VCOParams,
    selected_point_id: str,
) -> Dict[str, Any]:
    """Validate one least-overdesigned candidate for every allocated slice."""

    config = case["conditional_block_spec_allocation"]
    if config.get("candidate_validation_method") != VALIDATION_METHOD:
        raise ValueError("unsupported conditional candidate validation method")
    condition_axis = str(conditional_block_spec_map["condition_axis"]["name"])
    search_axis = str(
        conditional_block_spec_map["entries"][0]["source_boundary"][
            "search_axis"
        ]
    )
    records_by_condition: dict[float, list[Mapping[str, Any]]] = {}
    for record in records:
        value = float(record["design_vector"]["values"][condition_axis])
        records_by_condition.setdefault(value, []).append(record)

    boundary_point_ids: set[str] = set()
    for slice_item in system_boundary_map.get("slices", []):
        initial = slice_item.get("initial_bracket", {})
        for key in ("passing_point_id", "failing_point_id"):
            if initial.get(key) is not None:
                boundary_point_ids.add(str(initial[key]))
        refined = slice_item.get("refined_boundary", {})
        for evidence_key in ("passing_evidence", "nearest_failing_evidence"):
            evidence = refined.get(evidence_key, {})
            if evidence.get("point_id") is not None:
                boundary_point_ids.add(str(evidence["point_id"]))
        for trial in slice_item.get("refinement_history", []):
            if trial.get("point_id") is not None:
                boundary_point_ids.add(str(trial["point_id"]))

    validation_entries: list[Dict[str, Any]] = []
    for spec_entry in conditional_block_spec_map["entries"]:
        condition_value = float(spec_entry["condition"]["value"])
        allocated_spec = spec_entry["allocated_block_spec"]
        pn_limit = float(allocated_spec["phase_noise_1mhz_max_dbc_hz"])
        eligible = [
            record
            for record in records_by_condition.get(condition_value, [])
            if record["status"]["jointly_feasible"]
            and float(
                record["behavior_vector"][
                    "worst_phase_noise_1mhz_dbc_hz"
                ]
            )
            <= pn_limit
        ]
        if not eligible:
            raise ValueError(
                f"no sampled candidate satisfies allocated spec at {condition_value}"
            )
        eligible.sort(
            key=lambda record: (
                -float(record["design_vector"]["values"][search_axis]),
                str(record["point_id"]),
            )
        )
        sampled = eligible[0]
        values = {
            name: float(value)
            for name, value in sampled["design_vector"]["values"].items()
        }
        point = DesignPointDefinition(
            point_id=design_space.point_id(values),
            ordinal=int(sampled["ordinal"]),
            values=values,
        )
        replay = evaluate_design_point(case, system_spec, base_vco, point)
        replay_comparisons = _same_replay(sampled, replay)

        requirement = VCORequirement.from_dict(allocated_spec)
        realized_vco = VCOParams(
            **dict(replay["realized_instance"]["parameters"])
        )
        verification = verify_block_assignment(
            VerificationRequest(
                system_spec=system_spec,
                block_spec=requirement,
                realized_instance=realized_vco,
                operating_context=dict(case["block_context"]),
                block_id="VCO",
                backend_id="synthetic_vco_v1",
                request_id=(
                    f"{case['case_id']}:conditional-allocation:"
                    f"{point.point_id}"
                ),
                keep_raw=False,
            ),
            backend=SyntheticVCOBackend(),
        )
        verification_metrics_match = (
            verification["system_tb"]["metrics"]
            == replay["system_tb"]["metrics"]
            and verification["system_tb"]["checks"]
            == replay["system_tb"]["checks"]
            and verification["system_tb"]["residuals"]
            == replay["system_tb"]["residuals"]
        )
        candidate_checks = {
            "condition_matches": float(values[condition_axis])
            == condition_value,
            "candidate_is_on_feasible_search_side": float(values[search_axis])
            <= float(spec_entry["source_boundary"]["passing_value"]),
            "candidate_not_used_for_boundary_extraction": str(
                sampled["point_id"]
            )
            not in boundary_point_ids,
            "sampled_candidate_jointly_feasible": bool(
                sampled["status"]["jointly_feasible"]
            ),
            "independent_replay_identical": all(replay_comparisons.values()),
            "allocated_block_spec_passed": bool(
                verification["block_tb"]["passed"]
            ),
            "independent_systemtb_passed": bool(
                verification["system_tb"]["passed"]
            ),
            "context_covered": bool(
                verification["context_coverage"]["passed"]
            ),
            "same_instance_used_by_both_tbs": bool(
                verification["provenance"][
                    "realized_instance_shared_by_block_and_system_tb"
                ]
            ),
            "verification_matches_replay": verification_metrics_match,
        }
        validation_entries.append(
            {
                "condition": dict(spec_entry["condition"]),
                "block_spec": dict(allocated_spec),
                "source_block_spec_map_sha256": conditional_block_spec_map[
                    "block_spec_map_sha256"
                ],
                "selected_validation_candidate": {
                    "selection_rule": (
                        "least-negative PN anchor among sampled jointly feasible "
                        "candidates satisfying the allocated measured-PN spec"
                    ),
                    "point_id": str(sampled["point_id"]),
                    "boundary_extraction_point_id_exclusion": True,
                    "design_vector": values,
                    "measured_block_behavior": dict(
                        replay["behavior_vector"]
                    ),
                    "phase_noise_requirement_margin_db": float(
                        verification["block_tb"]["worst_case"][
                            "phase_noise_margin_db"
                        ]
                    ),
                },
                "replay_comparisons": replay_comparisons,
                "verification_report": verification,
                "checks": candidate_checks,
                "passed": all(candidate_checks.values()),
            }
        )

    validated_point_ids = {
        str(item["selected_validation_candidate"]["point_id"])
        for item in validation_entries
    }
    checks = {
        "allocation_map_validated": bool(
            conditional_block_spec_map.get("validation", {}).get("passed")
        ),
        "one_candidate_validated_per_allocated_slice": (
            len(validation_entries)
            == conditional_block_spec_map.get("entry_count")
        ),
        "all_conditional_candidates_pass": bool(validation_entries)
        and all(item["passed"] for item in validation_entries),
        "global_selected_candidate_is_conditionally_validated": (
            selected_point_id in validated_point_ids
        ),
        "unallocated_slices_preserved": len(
            conditional_block_spec_map.get("unallocated_slices", [])
        )
        == conditional_block_spec_map["validation"]["unallocated_slice_count"],
    }
    validation = {
        "passed": all(checks.values()),
        "checks": checks,
        "validated_condition_count": len(validation_entries),
        "unallocated_slice_count": len(
            conditional_block_spec_map.get("unallocated_slices", [])
        ),
    }
    if not validation["passed"]:
        failed = sorted(name for name, passed in checks.items() if not passed)
        raise ValueError(f"conditional candidate validation failed: {failed}")

    artifact: Dict[str, Any] = {
        "schema_version": "v1.5-conditional-candidate-validation-1.0",
        "case_id": str(case["case_id"]),
        "status": "validated_on_all_allocated_slices",
        "workflow_outcome": WORKFLOW_OUTCOME,
        "block_spec_mapping_status": ALLOCATION_STATUS,
        "method": VALIDATION_METHOD,
        "source_block_spec_map_sha256": conditional_block_spec_map[
            "block_spec_map_sha256"
        ],
        "global_selected_point_id": selected_point_id,
        "boundary_extraction_point_count": len(boundary_point_ids),
        "entries": validation_entries,
        "validation": validation,
        "claim_boundary": (
            "All allocated discrete k1 slices have one independently replayed "
            "sampled candidate; interpolation and unmapped k1 slices remain "
            "outside the validated allocation domain."
        ),
        "provenance": {
            "builder": (
                "v1.allocation.conditional_allocation."
                "validate_conditional_block_spec_map"
            ),
            "deterministic": True,
            "random_seed": None,
        },
    }
    artifact["validation_sha256"] = _digest(artifact)
    return artifact


def validate_conditional_contract_prediction(
    *,
    case: Mapping[str, Any],
    conditional_block_spec_map: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    system_spec: SystemSpec,
) -> Dict[str, Any]:
    """Check that BlockSpec-PASS candidates are SystemTB-PASS when replayed.

    This is a sufficient-condition check.  A candidate rejected by the
    allocated BlockSpec is reported as uncertified; it is not treated as a
    predicted SystemTB failure because the engineering margin may be
    conservative.
    """

    config = dict(case.get("conditional_block_spec_allocation", {}))
    if config.get("contract_prediction_policy") != (
        "block_pass_must_imply_system_pass"
    ):
        raise ValueError("unsupported conditional contract prediction policy")
    by_condition: dict[float, list[Mapping[str, Any]]] = {}
    condition_axis = str(conditional_block_spec_map["condition_axis"]["name"])
    for record in records:
        value = float(record["design_vector"]["values"][condition_axis])
        by_condition.setdefault(value, []).append(record)

    entries: list[Dict[str, Any]] = []
    for spec_entry in conditional_block_spec_map["entries"]:
        condition_value = float(spec_entry["condition"]["value"])
        requirement = VCORequirement.from_dict(
            spec_entry["allocated_block_spec"]
        )
        condition_results: list[Dict[str, Any]] = []
        for record in by_condition.get(condition_value, []):
            realized = VCOParams(
                **dict(record["realized_instance"]["parameters"])
            )
            report = verify_block_assignment(
                VerificationRequest(
                    system_spec=system_spec,
                    block_spec=requirement,
                    realized_instance=realized,
                    operating_context=dict(case["block_context"]),
                    block_id="VCO",
                    backend_id="synthetic_vco_v1",
                    request_id=(
                        f"{case['case_id']}:contract-prediction:"
                        f"{record['point_id']}"
                    ),
                    keep_raw=False,
                ),
                backend=SyntheticVCOBackend(),
            )
            system_pass = bool(report["system_tb"]["passed"])
            block_pass = bool(report["block_tb"]["passed"])
            context_pass = bool(report["context_coverage"]["passed"])
            block_worst = report["block_tb"].get(
                "worst_case", report["block_tb"].get("behavior_vector", {})
            )
            replay_behavior = {
                field: float(block_worst[field])
                for field in (
                    "worst_phase_noise_1mhz_dbc_hz",
                    "kvco_min_hz_per_v",
                    "kvco_max_hz_per_v",
                    "frequency_min_hz",
                    "frequency_max_hz",
                    "worst_power_w",
                )
            }
            certified = block_pass and context_pass
            system_predicted_pass = certified
            system_actual_pass = system_pass and context_pass
            comparisons = {
                "system_metrics_match_sampled": report["system_tb"][
                    "metrics"
                ]
                == record["system_tb"]["metrics"],
                "system_checks_match_sampled": report["system_tb"]["checks"]
                == record["system_tb"]["checks"],
                "system_residuals_match_sampled": report["system_tb"][
                    "residuals"
                ]
                == record["system_tb"]["residuals"],
                "behavior_vector_match_sampled": replay_behavior
                == record["behavior_vector"],
            }
            condition_results.append(
                {
                    "point_id": str(record["point_id"]),
                    "design_vector": dict(record["design_vector"]["values"]),
                    "measured_block_behavior": dict(record["behavior_vector"]),
                    "allocated_block_spec": dict(
                        spec_entry["allocated_block_spec"]
                    ),
                    "block_spec_pass": block_pass,
                    "context_pass": context_pass,
                    "certified_by_contract": certified,
                    "systemtb_actual_pass": system_actual_pass,
                    "systemtb_predicted_pass": system_predicted_pass,
                    "prediction_correct": (
                        not system_predicted_pass or system_actual_pass
                    ),
                    "comparison_to_sampled_evidence": comparisons,
                    "independent_systemtb_replay_identical": all(
                        comparisons.values()
                    ),
                }
            )
        certified_count = sum(
            bool(item["certified_by_contract"]) for item in condition_results
        )
        false_positive_count = sum(
            bool(item["certified_by_contract"])
            and not bool(item["systemtb_actual_pass"])
            for item in condition_results
        )
        entries.append(
            {
                "condition": dict(spec_entry["condition"]),
                "candidate_count": len(condition_results),
                "certified_candidate_count": certified_count,
                "certified_systemtb_pass_count": sum(
                    bool(item["certified_by_contract"])
                    and bool(item["systemtb_actual_pass"])
                    for item in condition_results
                ),
                "uncertified_systemtb_pass_count": sum(
                    not bool(item["certified_by_contract"])
                    and bool(item["systemtb_actual_pass"])
                    for item in condition_results
                ),
                "uncertified_systemtb_fail_count": sum(
                    not bool(item["certified_by_contract"])
                    and not bool(item["systemtb_actual_pass"])
                    for item in condition_results
                ),
                "false_positive_count": false_positive_count,
                "all_replays_match_sampled_evidence": all(
                    item["independent_systemtb_replay_identical"]
                    for item in condition_results
                ),
                "candidates": condition_results,
                "passed": certified_count > 0 and false_positive_count == 0,
            }
        )

    checks = {
        "allocation_map_validated": bool(
            conditional_block_spec_map.get("validation", {}).get("passed")
        ),
        "one_prediction_slice_per_allocated_condition": len(entries)
        == conditional_block_spec_map.get("entry_count"),
        "every_slice_has_certified_candidate": bool(entries)
        and all(item["certified_candidate_count"] > 0 for item in entries),
        "no_contract_false_positive": bool(entries)
        and all(item["false_positive_count"] == 0 for item in entries),
        "all_independent_replays_match": bool(entries)
        and all(item["all_replays_match_sampled_evidence"] for item in entries),
        "unallocated_slices_preserved": len(
            conditional_block_spec_map.get("unallocated_slices", [])
        )
        == conditional_block_spec_map["validation"]["unallocated_slice_count"],
    }
    validation = {
        "passed": all(checks.values()),
        "checks": checks,
        "condition_count": len(entries),
        "candidate_count": sum(item["candidate_count"] for item in entries),
        "certified_candidate_count": sum(
            item["certified_candidate_count"] for item in entries
        ),
        "false_positive_count": sum(
            item["false_positive_count"] for item in entries
        ),
        "uncertified_systemtb_pass_count": sum(
            item["uncertified_systemtb_pass_count"] for item in entries
        ),
        "uncertified_systemtb_fail_count": sum(
            item["uncertified_systemtb_fail_count"] for item in entries
        ),
    }
    if not validation["passed"]:
        failed = sorted(name for name, passed in checks.items() if not passed)
        raise ValueError(f"conditional contract prediction failed: {failed}")

    artifact: Dict[str, Any] = {
        "schema_version": "v1.5-conditional-contract-prediction-1.0",
        "case_id": str(case["case_id"]),
        "status": "sufficient_condition_validated_on_mapped_slices",
        "method": "all_mapped_slice_candidates_independent_replay",
        "prediction_policy": "block_pass_must_imply_system_pass",
        "source_block_spec_map_sha256": conditional_block_spec_map[
            "block_spec_map_sha256"
        ],
        "entries": entries,
        "validation": validation,
        "claim_boundary": (
            "A BlockSpec-PASS candidate is shown to pass SystemTB on the "
            "listed discrete k1 slices. BlockSpec-FAIL candidates remain "
            "uncertified; no necessary-condition or continuous prediction "
            "claim is made."
        ),
        "provenance": {
            "builder": (
                "v1.allocation.conditional_allocation."
                "validate_conditional_contract_prediction"
            ),
            "deterministic": True,
            "random_seed": None,
        },
    }
    artifact["prediction_sha256"] = _digest(artifact)
    return artifact


__all__ = [
    "ALLOCATION_METHOD",
    "ALLOCATION_STATUS",
    "VALIDATION_METHOD",
    "WORKFLOW_OUTCOME",
    "build_conditional_block_spec_map",
    "validate_conditional_block_spec_map",
    "validate_conditional_contract_prediction",
]
