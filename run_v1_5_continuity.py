"""Validate continuity of the frozen V1.5 conditional PN contracts.

This is a separate, holdout-only experiment.  It reads the completed V1.5
artifacts as immutable inputs, checks the sampled topology, builds a provisional
piecewise-linear PN_spec(k1) predictor, and evaluates new midpoint k1 values
through the same boundary -> BlockTB -> margin flow.  It does not modify the
canonical V1.5 allocation artifacts and it does not promote interpolation to a
production requirement.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

from v1.allocation.design_space import DesignPointDefinition, DesignSpaceDefinition
from v1.allocation.multidim_evaluator import evaluate_design_point
from v1.api.verification import VerificationRequest
from v1.backends.synthetic import SyntheticVCOBackend
from v1.model.pll_behavioral import VCOParams
from v1.model.instances import build_vco_instance
from v1.io import (
    evidence_digest,
    file_sha256,
    read_json,
    write_csv,
    write_evidence_json as write_json,
)
from v1.specs import SystemSpec, VCORequirement, load_case
from v1.verification.service import verify_block_assignment


ROOT = Path(__file__).resolve().parent
DEFAULT_CASE = ROOT / "v1" / "cases" / "vco_multidim_01.json"
DEFAULT_SOURCE_DIR = ROOT / "results" / "v1_5_vco_multidim_01"
DEFAULT_OUTPUT_DIR = ROOT / "results" / "v1_5_continuity_v1_5"
OFF_GRID_K1_HZ_PER_V = (
    675_000_000.0,
    725_000_000.0,
    775_000_000.0,
    825_000_000.0,
    875_000_000.0,
    925_000_000.0,
    975_000_000.0,
    1_025_000_000.0,
)
BOUNDARY_REFINEMENT_ITERATIONS = 20
EDGE_REFINEMENT_ITERATIONS = 20
PREDICTION_ACCEPTANCE_TOLERANCE_DB = 0.01
CONTRACT_EDGE_OFFSET_DB = 0.20


def _read_jsonl(path: Path) -> list[Dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _compact_record(record: Mapping[str, Any]) -> Dict[str, Any]:
    values = record["design_vector"]["values"]
    return {
        "point_id": str(record["point_id"]),
        "design_vector": dict(values),
        "system_passed": bool(record["system_tb"]["passed"]),
        "system_checks": dict(record["system_tb"]["checks"]),
        "system_metrics": dict(record["system_tb"]["metrics"]),
        "system_residuals": dict(record["system_tb"]["residuals"]),
        "block_tb_passed": bool(record["block_tb"]["passed"]),
        "context_covered": bool(record["context_coverage"]["passed"]),
        "behavior_vector": dict(record["behavior_vector"]),
    }


def _make_point(
    design_space: DesignSpaceDefinition,
    *,
    k1_hz_per_v: float,
    pn_anchor_dbc_hz: float,
    ordinal: int,
) -> DesignPointDefinition:
    values = {
        "pn_anchor_1mhz_dbc_hz": float(pn_anchor_dbc_hz),
        "k1_hz_per_v": float(k1_hz_per_v),
    }
    return DesignPointDefinition(
        point_id=design_space.point_id(values),
        ordinal=ordinal,
        values=values,
    )


def _evaluate(
    *,
    case: Mapping[str, Any],
    system_spec: SystemSpec,
    base_vco: VCOParams,
    design_space: DesignSpaceDefinition,
    k1_hz_per_v: float,
    pn_anchor_dbc_hz: float,
    ordinal: int,
) -> Dict[str, Any]:
    point = _make_point(
        design_space,
        k1_hz_per_v=k1_hz_per_v,
        pn_anchor_dbc_hz=pn_anchor_dbc_hz,
        ordinal=ordinal,
    )
    return evaluate_design_point(case, system_spec, base_vco, point)


def _pass_prefix_analysis(records: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    ordered = sorted(
        records,
        key=lambda record: float(
            record["design_vector"]["values"]["pn_anchor_1mhz_dbc_hz"]
        ),
    )
    flags = [bool(record["system_tb"]["passed"]) for record in ordered]
    transitions = [
        {
            "left_pn": float(
                left["design_vector"]["values"]["pn_anchor_1mhz_dbc_hz"]
            ),
            "right_pn": float(
                right["design_vector"]["values"]["pn_anchor_1mhz_dbc_hz"]
            ),
            "left_passed": bool(left["system_tb"]["passed"]),
            "right_passed": bool(right["system_tb"]["passed"]),
        }
        for left, right in zip(ordered, ordered[1:])
        if bool(left["system_tb"]["passed"])
        != bool(right["system_tb"]["passed"])
    ]
    pass_count = sum(flags)
    prefix_expected = flags == [True] * pass_count + [False] * (len(flags) - pass_count)
    jitters = [
        float(record["system_tb"]["metrics"]["integrated_jitter_s"])
        for record in ordered
    ]
    jitter_monotonic = all(
        right + 1.0e-30 >= left for left, right in zip(jitters, jitters[1:])
    )
    if pass_count == 0:
        classification = "no_feasible_point_in_sampled_pn_range"
    elif pass_count == len(flags):
        classification = "no_fail_point_in_sampled_pn_range"
    elif len(transitions) == 1 and prefix_expected:
        classification = "single_crossing"
    else:
        classification = "multiple_or_nonmonotonic_crossings"
    return {
        "pn_values_ascending": [
            float(record["design_vector"]["values"]["pn_anchor_1mhz_dbc_hz"])
            for record in ordered
        ],
        "system_pass_sequence": flags,
        "system_pass_sequence_compact": "".join("1" if flag else "0" for flag in flags),
        "system_pass_count": pass_count,
        "system_fail_count": len(flags) - pass_count,
        "transition_count": len(transitions),
        "transitions": transitions,
        "pass_region_is_prefix": prefix_expected,
        "integrated_jitter_non_decreasing_with_pn": jitter_monotonic,
        "classification": classification,
    }


def _analyze_original_slices(
    records: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    grouped: Dict[float, list[Mapping[str, Any]]] = {}
    for record in records:
        k1 = float(record["design_vector"]["values"]["k1_hz_per_v"])
        grouped.setdefault(k1, []).append(record)
    slices = []
    for k1 in sorted(grouped):
        analysis = _pass_prefix_analysis(grouped[k1])
        slices.append(
            {
                "k1_hz_per_v": k1,
                "k1_ghz_per_v": k1 / 1.0e9,
                **analysis,
            }
        )
    mapped = [item for item in slices if item["classification"] == "single_crossing"]
    return {
        "source": "sampled_points.jsonl",
        "pn_order": "ascending; more-negative values are tested first",
        "slice_count": len(slices),
        "mapped_single_crossing_slice_count": len(mapped),
        "slices": slices,
        "checks": {
            "all_slices_have_prefix_pass_region": all(
                item["pass_region_is_prefix"] for item in slices
            ),
            "all_slices_have_monotonic_jitter": all(
                item["integrated_jitter_non_decreasing_with_pn"] for item in slices
            ),
            "all_mapped_slices_have_exactly_one_crossing": bool(mapped)
            and all(item["transition_count"] == 1 for item in mapped),
            "unmapped_slices_have_no_sampled_feasible_point": all(
                item["classification"] == "no_feasible_point_in_sampled_pn_range"
                for item in slices
                if item["system_pass_count"] == 0
            ),
        },
    }


def _system_evaluation_for_k1(
    *,
    case: Mapping[str, Any],
    system_spec: SystemSpec,
    base_vco: VCOParams,
    design_space: DesignSpaceDefinition,
    k1_hz_per_v: float,
    pn_anchor_dbc_hz: float,
    ordinal: int,
) -> Dict[str, Any]:
    return _evaluate(
        case=case,
        system_spec=system_spec,
        base_vco=base_vco,
        design_space=design_space,
        k1_hz_per_v=k1_hz_per_v,
        pn_anchor_dbc_hz=pn_anchor_dbc_hz,
        ordinal=ordinal,
    )


def _refine_k1_edge(
    *,
    case: Mapping[str, Any],
    system_spec: SystemSpec,
    base_vco: VCOParams,
    design_space: DesignSpaceDefinition,
    pn_anchor_dbc_hz: float,
    failing_k1_hz_per_v: float,
    passing_k1_hz_per_v: float,
    edge: str,
) -> Dict[str, Any]:
    failing = float(failing_k1_hz_per_v)
    passing = float(passing_k1_hz_per_v)
    history = []
    for phase, value in (("failing_bracket", failing), ("passing_bracket", passing)):
        record = _system_evaluation_for_k1(
            case=case,
            system_spec=system_spec,
            base_vco=base_vco,
            design_space=design_space,
            k1_hz_per_v=value,
            pn_anchor_dbc_hz=pn_anchor_dbc_hz,
            ordinal=-1000 - len(history),
        )
        history.append(
            {
                "phase": phase,
                "k1_hz_per_v": value,
                "system_passed": bool(record["system_tb"]["passed"]),
                "system_checks": dict(record["system_tb"]["checks"]),
                "system_metrics": dict(record["system_tb"]["metrics"]),
                "system_residuals": dict(record["system_tb"]["residuals"]),
            }
        )
    for iteration in range(EDGE_REFINEMENT_ITERATIONS):
        midpoint = 0.5 * (passing + failing)
        record = _system_evaluation_for_k1(
            case=case,
            system_spec=system_spec,
            base_vco=base_vco,
            design_space=design_space,
            k1_hz_per_v=midpoint,
            pn_anchor_dbc_hz=pn_anchor_dbc_hz,
            ordinal=-2000 - iteration,
        )
        passed = bool(record["system_tb"]["passed"])
        history.append(
            {
                "phase": "bisection",
                "iteration": iteration,
                "k1_hz_per_v": midpoint,
                "system_passed": passed,
                "system_checks": dict(record["system_tb"]["checks"]),
                "system_metrics": dict(record["system_tb"]["metrics"]),
                "system_residuals": dict(record["system_tb"]["residuals"]),
            }
        )
        if passed:
            passing = midpoint
        else:
            failing = midpoint
    return {
        "edge": edge,
        "probe_pn_anchor_dbc_hz": pn_anchor_dbc_hz,
        "passing_k1_hz_per_v": passing,
        "nearest_failing_k1_hz_per_v": failing,
        "bracket_width_hz_per_v": abs(failing - passing),
        "limiting_system_checks": [
            name
            for name, passed in _system_evaluation_for_k1(
                case=case,
                system_spec=system_spec,
                base_vco=base_vco,
                design_space=design_space,
                k1_hz_per_v=failing,
                pn_anchor_dbc_hz=pn_anchor_dbc_hz,
                ordinal=-2500,
            )["system_tb"]["checks"].items()
            if not passed
        ],
        "iterations": EDGE_REFINEMENT_ITERATIONS,
        "history": history,
    }


def _find_feasible_k1_interval(
    *,
    case: Mapping[str, Any],
    system_spec: SystemSpec,
    base_vco: VCOParams,
    design_space: DesignSpaceDefinition,
) -> Dict[str, Any]:
    # The extreme PN in the frozen design space is the best-noise probe.  The
    # result is deliberately labelled a local interval under this probe; it is
    # not a claim that every PN value is feasible throughout the interval.
    pn_axis = next(
        axis for axis in design_space.axes if axis.name == "pn_anchor_1mhz_dbc_hz"
    )
    best_pn = float(min(pn_axis.values()))
    lower = _refine_k1_edge(
        case=case,
        system_spec=system_spec,
        base_vco=base_vco,
        design_space=design_space,
        pn_anchor_dbc_hz=best_pn,
        failing_k1_hz_per_v=600_000_000.0,
        passing_k1_hz_per_v=650_000_000.0,
        edge="lower_feasible_edge",
    )
    upper = _refine_k1_edge(
        case=case,
        system_spec=system_spec,
        base_vco=base_vco,
        design_space=design_space,
        pn_anchor_dbc_hz=best_pn,
        failing_k1_hz_per_v=1_100_000_000.0,
        passing_k1_hz_per_v=1_050_000_000.0,
        edge="upper_feasible_edge",
    )
    return {
        "status": "local_continuous_interval_refined_under_best_pn_probe",
        "probe": {
            "pn_anchor_1mhz_dbc_hz": best_pn,
            "interpretation": (
                "best-noise probe; the interval is not a claim that every PN "
                "value is feasible at every k1"
            ),
        },
        "sampled_mapped_interval": {
            "lower_k1_hz_per_v": 650_000_000.0,
            "upper_k1_hz_per_v": 1_050_000_000.0,
            "source": "nine mapped discrete conditional contracts",
        },
        "refined_best_pn_interval": {
            "lower_k1_hz_per_v": lower["passing_k1_hz_per_v"],
            "upper_k1_hz_per_v": upper["passing_k1_hz_per_v"],
            "lower_k1_ghz_per_v": lower["passing_k1_hz_per_v"] / 1.0e9,
            "upper_k1_ghz_per_v": upper["passing_k1_hz_per_v"] / 1.0e9,
            "nearest_lower_fail_k1_hz_per_v": lower[
                "nearest_failing_k1_hz_per_v"
            ],
            "nearest_upper_fail_k1_hz_per_v": upper[
                "nearest_failing_k1_hz_per_v"
            ],
        },
        "edges": {"lower": lower, "upper": upper},
        "checks": {
            "lower_bracket_is_fail_to_pass": (
                lower["history"][0]["system_passed"] is False
                and lower["history"][1]["system_passed"] is True
            ),
            "upper_bracket_is_fail_at_high_k1_and_pass_at_low_k1": (
                upper["history"][0]["system_passed"] is False
                and upper["history"][1]["system_passed"] is True
            ),
            "lower_edge_is_narrow": lower["bracket_width_hz_per_v"] < 100.0,
            "upper_edge_is_narrow": upper["bracket_width_hz_per_v"] < 100.0,
        },
    }


def _refine_off_grid_boundary(
    *,
    case: Mapping[str, Any],
    system_spec: SystemSpec,
    base_vco: VCOParams,
    design_space: DesignSpaceDefinition,
    k1_hz_per_v: float,
    pn_values: Sequence[float],
) -> Dict[str, Any]:
    sampled = [
        _evaluate(
            case=case,
            system_spec=system_spec,
            base_vco=base_vco,
            design_space=design_space,
            k1_hz_per_v=k1_hz_per_v,
            pn_anchor_dbc_hz=float(pn),
            ordinal=-3000 - index,
        )
        for index, pn in enumerate(pn_values)
    ]
    analysis = _pass_prefix_analysis(sampled)
    transitions = [
        (left, right)
        for left, right in zip(sampled, sampled[1:])
        if bool(left["system_tb"]["passed"])
        != bool(right["system_tb"]["passed"])
    ]
    if len(transitions) != 1 or not analysis["pass_region_is_prefix"]:
        raise ValueError(
            f"off-grid k1={k1_hz_per_v} did not produce one PASS-to-FAIL PN crossing"
        )
    left, right = transitions[0]
    if not left["system_tb"]["passed"]:
        left, right = right, left
    passing = float(left["design_vector"]["values"]["pn_anchor_1mhz_dbc_hz"])
    failing = float(right["design_vector"]["values"]["pn_anchor_1mhz_dbc_hz"])
    history = [
        {"phase": "sampled_passing_bracket", **_compact_record(left)},
        {"phase": "sampled_failing_bracket", **_compact_record(right)},
    ]
    passing_record = left
    failing_record = right
    for iteration in range(BOUNDARY_REFINEMENT_ITERATIONS):
        midpoint = 0.5 * (passing + failing)
        trial = _evaluate(
            case=case,
            system_spec=system_spec,
            base_vco=base_vco,
            design_space=design_space,
            k1_hz_per_v=k1_hz_per_v,
            pn_anchor_dbc_hz=midpoint,
            ordinal=-4000 - iteration,
        )
        history.append(
            {"phase": "bisection", "iteration": iteration, **_compact_record(trial)}
        )
        if bool(trial["system_tb"]["passed"]):
            passing = midpoint
            passing_record = trial
        else:
            failing = midpoint
            failing_record = trial

    boundary_replay = _evaluate(
        case=case,
        system_spec=system_spec,
        base_vco=base_vco,
        design_space=design_space,
        k1_hz_per_v=k1_hz_per_v,
        pn_anchor_dbc_hz=passing,
        ordinal=-5000,
    )
    measured_pn = float(
        boundary_replay["behavior_vector"]["worst_phase_noise_1mhz_dbc_hz"]
    )
    power_limit = float(case["system_spec"]["limits"]["power_max_w"])
    required = VCORequirement(
        phase_noise_1mhz_max_dbc_hz=measured_pn,
        power_max_w=power_limit,
        margin_db=0.0,
    )
    direct_boundary_replay = verify_block_assignment(
        VerificationRequest(
            system_spec=system_spec,
            block_spec=required,
            realized_instance=VCOParams(
                **dict(boundary_replay["realized_instance"]["parameters"])
            ),
            operating_context=dict(case["block_context"]),
            block_id="VCO",
            backend_id="synthetic_vco_v1",
            request_id=f"{case['case_id']}:off-grid-boundary:{k1_hz_per_v}",
            keep_raw=False,
        ),
        backend=SyntheticVCOBackend(),
    )
    return {
        "condition": {
            "axis": "k1_hz_per_v",
            "value": float(k1_hz_per_v),
            "unit": "Hz/V",
        },
        "sampled_analysis": analysis,
        "sampled_records": [_compact_record(record) for record in sampled],
        "initial_bracket": {
            "passing_value": float(
                left["design_vector"]["values"]["pn_anchor_1mhz_dbc_hz"]
            ),
            "failing_value": float(
                right["design_vector"]["values"]["pn_anchor_1mhz_dbc_hz"]
            ),
        },
        "refinement": {
            "method": "deterministic_bisection",
            "iterations": BOUNDARY_REFINEMENT_ITERATIONS,
            "passing_value": passing,
            "nearest_failing_value": failing,
            "bracket_width": failing - passing,
            "passing_evidence": _compact_record(passing_record),
            "nearest_failing_evidence": _compact_record(failing_record),
            "history": history,
        },
        "boundary_replay": {
            "identical_to_passing_evidence": (
                boundary_replay["design_vector"] == passing_record["design_vector"]
                and boundary_replay["behavior_vector"] == passing_record["behavior_vector"]
                and boundary_replay["system_tb"] == passing_record["system_tb"]
            ),
            "system_tb_passed": bool(boundary_replay["system_tb"]["passed"]),
            "block_tb_passed": bool(boundary_replay["block_tb"]["passed"]),
            "context_covered": bool(boundary_replay["context_coverage"]["passed"]),
            "behavior_vector": dict(boundary_replay["behavior_vector"]),
            "system_metrics": dict(boundary_replay["system_tb"]["metrics"]),
            "system_checks": dict(boundary_replay["system_tb"]["checks"]),
            "direct_required_pn_blocktb_passed": bool(
                direct_boundary_replay["block_tb"]["passed"]
            ),
            "direct_systemtb_passed": bool(direct_boundary_replay["system_tb"]["passed"]),
            "direct_replay_system_identical": (
                direct_boundary_replay["system_tb"]["metrics"]
                == boundary_replay["system_tb"]["metrics"]
                and direct_boundary_replay["system_tb"]["checks"]
                == boundary_replay["system_tb"]["checks"]
            ),
            "required_block_spec": required.to_dict(),
        },
        "actual_allocation": {
            "boundary_pn_anchor_dbc_hz": passing,
            "boundary_measured_worst_pn_dbc_hz": measured_pn,
            "engineering_margin_db": float(
                case["conditional_block_spec_allocation"]["engineering_margin"][
                    "value_db"
                ]
            ),
            "allocated_pn_spec_dbc_hz": measured_pn
            - float(
                case["conditional_block_spec_allocation"]["engineering_margin"][
                    "value_db"
                ]
            ),
        },
    }


def _known_contract_table(
    boundary_contract: Mapping[str, Any],
    block_spec_map: Mapping[str, Any],
) -> list[Dict[str, float]]:
    block_by_k1 = {
        float(entry["condition"]["value"]): entry
        for entry in block_spec_map["entries"]
    }
    rows = []
    for entry in boundary_contract["entries"]:
        k1 = float(entry["condition"]["value"])
        spec_entry = block_by_k1[k1]
        rows.append(
            {
                "k1_hz_per_v": k1,
                "k1_ghz_per_v": k1 / 1.0e9,
                "boundary_pn_anchor_dbc_hz": float(
                    entry["source_system_boundary"]["passing_value"]
                ),
                "boundary_measured_worst_pn_dbc_hz": float(
                    entry["measured_block_behavior"][
                        "worst_phase_noise_1mhz_dbc_hz"
                    ]
                ),
                "pn_spec_dbc_hz": float(
                    spec_entry["allocated_block_spec"][
                        "phase_noise_1mhz_max_dbc_hz"
                    ]
                ),
            }
        )
    return sorted(rows, key=lambda row: row["k1_hz_per_v"])


def _interpolate(
    rows: Sequence[Mapping[str, float]], key: str, k1_hz_per_v: float
) -> float:
    ordered = sorted(rows, key=lambda row: float(row["k1_hz_per_v"]))
    if not (ordered[0]["k1_hz_per_v"] <= k1_hz_per_v <= ordered[-1]["k1_hz_per_v"]):
        raise ValueError("prediction requested outside mapped k1 domain")
    for row in ordered:
        if float(row["k1_hz_per_v"]) == float(k1_hz_per_v):
            return float(row[key])
    lower = max(
        (row for row in ordered if float(row["k1_hz_per_v"]) < k1_hz_per_v),
        key=lambda row: float(row["k1_hz_per_v"]),
    )
    upper = min(
        (row for row in ordered if float(row["k1_hz_per_v"]) > k1_hz_per_v),
        key=lambda row: float(row["k1_hz_per_v"]),
    )
    weight = (k1_hz_per_v - lower["k1_hz_per_v"]) / (
        upper["k1_hz_per_v"] - lower["k1_hz_per_v"]
    )
    return float(lower[key] + weight * (upper[key] - lower[key]))


def _coupling_rows(rows: Sequence[Mapping[str, float]]) -> list[Dict[str, float]]:
    ordered = sorted(rows, key=lambda row: float(row["k1_hz_per_v"]))
    result = []
    for left, right in zip(ordered, ordered[1:]):
        delta_k1_ghz = (right["k1_hz_per_v"] - left["k1_hz_per_v"]) / 1.0e9
        result.append(
            {
                "lower_k1_ghz_per_v": left["k1_ghz_per_v"],
                "upper_k1_ghz_per_v": right["k1_ghz_per_v"],
                "delta_k1_ghz_per_v": delta_k1_ghz,
                "delta_boundary_pn_anchor_db": right["boundary_pn_anchor_dbc_hz"]
                - left["boundary_pn_anchor_dbc_hz"],
                "delta_boundary_measured_pn_db": right[
                    "boundary_measured_worst_pn_dbc_hz"
                ]
                - left["boundary_measured_worst_pn_dbc_hz"],
                "delta_pn_spec_db": right["pn_spec_dbc_hz"] - left["pn_spec_dbc_hz"],
                "d_pn_spec_d_k1_db_per_ghz_per_v": (
                    right["pn_spec_dbc_hz"] - left["pn_spec_dbc_hz"]
                )
                / delta_k1_ghz,
            }
        )
    return result


def _candidate_replay(
    *,
    case: Mapping[str, Any],
    system_spec: SystemSpec,
    base_vco: VCOParams,
    design_space: DesignSpaceDefinition,
    k1_hz_per_v: float,
    predicted_boundary_anchor: float,
    predicted_pn_spec: float,
    kind: str,
    ordinal: int,
) -> Dict[str, Any]:
    margin_db = float(
        case["conditional_block_spec_allocation"]["engineering_margin"]["value_db"]
    )
    if kind == "predicted_contract_inside":
        pn_anchor = predicted_boundary_anchor - margin_db - CONTRACT_EDGE_OFFSET_DB
    elif kind == "predicted_contract_outside":
        pn_anchor = predicted_boundary_anchor - margin_db + CONTRACT_EDGE_OFFSET_DB
    else:
        raise ValueError(f"unsupported candidate kind: {kind}")
    sampled = _evaluate(
        case=case,
        system_spec=system_spec,
        base_vco=base_vco,
        design_space=design_space,
        k1_hz_per_v=k1_hz_per_v,
        pn_anchor_dbc_hz=pn_anchor,
        ordinal=ordinal,
    )
    requirement = VCORequirement(
        phase_noise_1mhz_max_dbc_hz=predicted_pn_spec,
        power_max_w=float(case["system_spec"]["limits"]["power_max_w"]),
        margin_db=margin_db,
    )
    direct = verify_block_assignment(
        VerificationRequest(
            system_spec=system_spec,
            block_spec=requirement,
            realized_instance=VCOParams(
                **dict(sampled["realized_instance"]["parameters"])
            ),
            operating_context=dict(case["block_context"]),
            block_id="VCO",
            backend_id="synthetic_vco_v1",
            request_id=f"{case['case_id']}:continuity-candidate:{kind}:{k1_hz_per_v}",
            keep_raw=False,
        ),
        backend=SyntheticVCOBackend(),
    )
    measured = float(
        sampled["behavior_vector"]["worst_phase_noise_1mhz_dbc_hz"]
    )
    contract_margin = predicted_pn_spec - measured
    system_identical = (
        direct["system_tb"]["metrics"] == sampled["system_tb"]["metrics"]
        and direct["system_tb"]["checks"] == sampled["system_tb"]["checks"]
        and direct["system_tb"]["residuals"] == sampled["system_tb"]["residuals"]
    )
    return {
        "candidate_kind": kind,
        "condition": {"k1_hz_per_v": k1_hz_per_v, "k1_ghz_per_v": k1_hz_per_v / 1.0e9},
        "design_vector": dict(sampled["design_vector"]["values"]),
        "point_id": str(sampled["point_id"]),
        "predicted_contract": {
            "boundary_pn_anchor_dbc_hz": predicted_boundary_anchor,
            "allocated_pn_spec_dbc_hz": predicted_pn_spec,
            "contract_edge_offset_db": CONTRACT_EDGE_OFFSET_DB,
        },
        "measured_behavior": dict(sampled["behavior_vector"]),
        "checks": {
            "predicted_contract_passed": bool(direct["block_tb"]["passed"]),
            "independent_systemtb_passed": bool(direct["system_tb"]["passed"]),
            "context_covered": bool(direct["context_coverage"]["passed"]),
            "independent_systemtb_replay_identical": system_identical,
            "same_instance_used_by_both_tbs": bool(
                direct["provenance"]["realized_instance_shared_by_block_and_system_tb"]
            ),
        },
        "predicted_contract_margin_db": contract_margin,
        "system_metrics": dict(sampled["system_tb"]["metrics"]),
        "block_spec_verification": direct,
    }


def _build_plot(
    *,
    known_rows: Sequence[Mapping[str, float]],
    offgrid_rows: Sequence[Mapping[str, Any]],
    coupling_rows: Sequence[Mapping[str, float]],
    output: Path,
) -> str | None:
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return None
    output.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), constrained_layout=True)
    known_x = [row["k1_ghz_per_v"] for row in known_rows]
    known_y = [row["pn_spec_dbc_hz"] for row in known_rows]
    axes[0].plot(known_x, known_y, "o-", label="frozen 9-slice PN_spec")
    hold_x = [row["k1_ghz_per_v"] for row in offgrid_rows]
    actual_y = [row["actual_pn_spec_dbc_hz"] for row in offgrid_rows]
    predicted_y = [row["predicted_pn_spec_dbc_hz"] for row in offgrid_rows]
    axes[0].plot(hold_x, predicted_y, "x--", label="piecewise-linear prediction")
    axes[0].plot(hold_x, actual_y, "s", label="off-grid actual allocation")
    axes[0].set_xlabel("k1 (GHz/V)")
    axes[0].set_ylabel("PN_spec (dBc/Hz)")
    axes[0].set_title("Boundary evolution")
    axes[0].grid(True, alpha=0.3)
    axes[0].legend(fontsize=8)
    slope_x = [
        0.5 * (row["lower_k1_ghz_per_v"] + row["upper_k1_ghz_per_v"])
        for row in coupling_rows
    ]
    slopes = [row["d_pn_spec_d_k1_db_per_ghz_per_v"] for row in coupling_rows]
    axes[1].plot(slope_x, slopes, "o-")
    axes[1].set_xlabel("k1 interval midpoint (GHz/V)")
    axes[1].set_ylabel("ΔPN_spec/Δk1 (dB/(GHz/V))")
    axes[1].set_title("Coupling finite difference")
    axes[1].grid(True, alpha=0.3)
    fig.savefig(output, dpi=160)
    plt.close(fig)
    return str(output.name)


def run(
    case_path: str | Path = DEFAULT_CASE,
    source_dir: str | Path = DEFAULT_SOURCE_DIR,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> Dict[str, Any]:
    case = load_case(case_path)
    source = Path(source_dir).resolve()
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    boundary_contract_path = source / "boundary_block_contract.json"
    block_spec_map_path = source / "conditional_block_spec_map.json"
    sampled_points_path = source / "sampled_points.jsonl"
    boundary_contract = read_json(boundary_contract_path)
    block_spec_map = read_json(block_spec_map_path)
    sampled_records = _read_jsonl(sampled_points_path)

    if boundary_contract.get("entry_count") != 9 or block_spec_map.get("entry_count") != 9:
        raise ValueError("continuity experiment requires exactly nine frozen contracts")
    if boundary_contract.get("interpolation_allowed") is not False:
        raise ValueError("frozen boundary contract unexpectedly allows interpolation")
    if block_spec_map.get("interpolation_allowed") is not False:
        raise ValueError("frozen BlockSpec map unexpectedly allows interpolation")
    if not boundary_contract.get("validation", {}).get("passed"):
        raise ValueError("frozen boundary contract is not validated")
    if not block_spec_map.get("validation", {}).get("passed"):
        raise ValueError("frozen BlockSpec map is not validated")
    if block_spec_map.get("source_boundary_block_contract_sha256") != boundary_contract.get(
        "contract_sha256"
    ):
        raise ValueError("frozen BlockSpec map does not derive from frozen boundary contract")

    frozen_manifest = {
        "status": "frozen_for_continuity_experiment",
        "source_artifacts": {
            "boundary_block_contract.json": {
                "file_sha256": file_sha256(boundary_contract_path),
                "internal_contract_sha256": boundary_contract["contract_sha256"],
            },
            "conditional_block_spec_map.json": {
                "file_sha256": file_sha256(block_spec_map_path),
                "internal_block_spec_map_sha256": block_spec_map[
                    "block_spec_map_sha256"
                ],
            },
            "sampled_points.jsonl": {
                "file_sha256": file_sha256(sampled_points_path),
                "record_count": len(sampled_records),
            },
        },
        "entry_count": 9,
        "condition_values_hz_per_v": sorted(
            float(entry["condition"]["value"])
            for entry in block_spec_map["entries"]
        ),
        "interpolation_allowed_in_frozen_artifacts": False,
        "snapshot": {
            "boundary_block_contract": boundary_contract,
            "conditional_block_spec_map": block_spec_map,
        },
    }
    write_json(frozen_manifest, output / "frozen_conditional_contracts.json")

    system_spec = SystemSpec.from_dict(case["system_spec"])
    base_vco = build_vco_instance(VCOParams(), case.get("base_vco", {}))
    design_space = DesignSpaceDefinition.from_dict(case["design_space"])
    original_analysis = _analyze_original_slices(sampled_records)
    write_json(original_analysis, output / "slice_single_crossing_analysis.json")

    feasible_interval = _find_feasible_k1_interval(
        case=case,
        system_spec=system_spec,
        base_vco=base_vco,
        design_space=design_space,
    )
    write_json(feasible_interval, output / "feasible_k1_interval.json")

    known_rows = _known_contract_table(boundary_contract, block_spec_map)
    coupling_rows = _coupling_rows(known_rows)
    predictor = {
        "type": "piecewise_linear_between_frozen_k1_slices",
        "status": "provisional_holdout_predictor",
        "source": "frozen_conditional_block_spec_map.json",
        "validity_domain_hz_per_v": [
            known_rows[0]["k1_hz_per_v"],
            known_rows[-1]["k1_hz_per_v"],
        ],
        "interpolation_is_not_promoted_to_canonical_allocation": True,
        "known_rows": known_rows,
        "coupling_rows": coupling_rows,
    }
    write_json(predictor, output / "continuous_boundary_prediction.json")
    write_csv(known_rows, output / "boundary_evolution.csv")
    write_csv(coupling_rows, output / "coupling_analysis.csv")

    pn_axis = next(
        axis for axis in design_space.axes if axis.name == "pn_anchor_1mhz_dbc_hz"
    )
    offgrid_allocations = []
    candidate_replays = []
    for index, k1 in enumerate(OFF_GRID_K1_HZ_PER_V):
        actual = _refine_off_grid_boundary(
            case=case,
            system_spec=system_spec,
            base_vco=base_vco,
            design_space=design_space,
            k1_hz_per_v=k1,
            pn_values=pn_axis.values(),
        )
        predicted_anchor = _interpolate(
            known_rows, "boundary_pn_anchor_dbc_hz", k1
        )
        predicted_measured = _interpolate(
            known_rows, "boundary_measured_worst_pn_dbc_hz", k1
        )
        predicted_spec = _interpolate(known_rows, "pn_spec_dbc_hz", k1)
        actual_anchor = float(actual["actual_allocation"]["boundary_pn_anchor_dbc_hz"])
        actual_measured = float(
            actual["actual_allocation"]["boundary_measured_worst_pn_dbc_hz"]
        )
        actual_spec = float(actual["actual_allocation"]["allocated_pn_spec_dbc_hz"])
        row = {
            "k1_hz_per_v": k1,
            "k1_ghz_per_v": k1 / 1.0e9,
            "holdout_point_is_off_grid": k1
            not in {row["k1_hz_per_v"] for row in known_rows},
            "predicted_boundary_pn_anchor_dbc_hz": predicted_anchor,
            "actual_boundary_pn_anchor_dbc_hz": actual_anchor,
            "boundary_pn_anchor_error_db": actual_anchor - predicted_anchor,
            "predicted_boundary_measured_worst_pn_dbc_hz": predicted_measured,
            "actual_boundary_measured_worst_pn_dbc_hz": actual_measured,
            "boundary_measured_pn_error_db": actual_measured - predicted_measured,
            "predicted_pn_spec_dbc_hz": predicted_spec,
            "actual_pn_spec_dbc_hz": actual_spec,
            "pn_spec_error_db": actual_spec - predicted_spec,
            "system_boundary_passed": actual["boundary_replay"]["system_tb_passed"],
            "boundary_blocktb_passed": actual["boundary_replay"][
                "direct_required_pn_blocktb_passed"
            ],
            "context_covered": actual["boundary_replay"]["context_covered"],
            "single_crossing": actual["sampled_analysis"]["classification"]
            == "single_crossing",
            "sampled_system_pass_sequence": actual["sampled_analysis"][
                "system_pass_sequence_compact"
            ],
            "boundary_bracket_width_db": actual["refinement"]["bracket_width"],
        }
        offgrid_allocations.append({**row, "detail": actual})
        for kind in ("predicted_contract_inside", "predicted_contract_outside"):
            candidate_replays.append(
                _candidate_replay(
                    case=case,
                    system_spec=system_spec,
                    base_vco=base_vco,
                    design_space=design_space,
                    k1_hz_per_v=k1,
                    predicted_boundary_anchor=predicted_anchor,
                    predicted_pn_spec=predicted_spec,
                    kind=kind,
                    ordinal=-6000 - index * 2 - (0 if kind.endswith("inside") else 1),
                )
            )
    write_json(
        {
            "status": "off_grid_boundary_allocation_completed",
            "predictor": predictor,
            "entries": offgrid_allocations,
            "entry_count": len(offgrid_allocations),
            "validation": {
                "all_off_grid": all(
                    entry["holdout_point_is_off_grid"] for entry in offgrid_allocations
                ),
                "all_single_crossing": all(
                    entry["single_crossing"] for entry in offgrid_allocations
                ),
                "all_boundary_systemtb_pass": all(
                    entry["system_boundary_passed"] for entry in offgrid_allocations
                ),
                "all_boundary_blocktb_pass": all(
                    entry["boundary_blocktb_passed"] for entry in offgrid_allocations
                ),
                "all_context_covered": all(
                    entry["context_covered"] for entry in offgrid_allocations
                ),
            },
        },
        output / "offgrid_boundary_allocations.json",
    )
    write_csv(
        [
            {
                key: value
                for key, value in entry.items()
                if key != "detail"
            }
            for entry in offgrid_allocations
        ],
        output / "offgrid_holdout.csv",
    )
    write_json(
        {
            "status": "independent_systemtb_replay_completed",
            "candidate_count": len(candidate_replays),
            "entries": candidate_replays,
            "validation": {
                "all_replays_systemtb_identical": all(
                    entry["checks"]["independent_systemtb_replay_identical"]
                    for entry in candidate_replays
                ),
                "all_inside_contract_candidates_pass_contract": all(
                    entry["checks"]["predicted_contract_passed"]
                    for entry in candidate_replays
                    if entry["candidate_kind"] == "predicted_contract_inside"
                ),
                "all_inside_contract_candidates_pass_systemtb": all(
                    entry["checks"]["independent_systemtb_passed"]
                    for entry in candidate_replays
                    if entry["candidate_kind"] == "predicted_contract_inside"
                ),
                "all_outside_candidates_fail_predicted_contract": all(
                    not entry["checks"]["predicted_contract_passed"]
                    for entry in candidate_replays
                    if entry["candidate_kind"] == "predicted_contract_outside"
                ),
                "inside_contract_false_positive_count": sum(
                    entry["checks"]["predicted_contract_passed"]
                    and not entry["checks"]["independent_systemtb_passed"]
                    for entry in candidate_replays
                    if entry["candidate_kind"] == "predicted_contract_inside"
                ),
            },
        },
        output / "offgrid_candidate_replay.json",
    )
    write_csv(
        [
            {
                "k1_ghz_per_v": entry["condition"]["k1_ghz_per_v"],
                "candidate_kind": entry["candidate_kind"],
                "pn_anchor_dbc_hz": entry["design_vector"][
                    "pn_anchor_1mhz_dbc_hz"
                ],
                "predicted_contract_passed": entry["checks"][
                    "predicted_contract_passed"
                ],
                "systemtb_passed": entry["checks"]["independent_systemtb_passed"],
                "systemtb_replay_identical": entry["checks"][
                    "independent_systemtb_replay_identical"
                ],
                "predicted_contract_margin_db": entry[
                    "predicted_contract_margin_db"
                ],
            }
            for entry in candidate_replays
        ],
        output / "offgrid_candidate_replay.csv",
    )

    abs_spec_errors = [abs(float(entry["pn_spec_error_db"])) for entry in offgrid_allocations]
    abs_anchor_errors = [
        abs(float(entry["boundary_pn_anchor_error_db"])) for entry in offgrid_allocations
    ]
    replay_validation = read_json(output / "offgrid_candidate_replay.json")
    plot_name = "boundary_evolution.png"
    _build_plot(
        known_rows=known_rows,
        offgrid_rows=offgrid_allocations,
        coupling_rows=coupling_rows,
        output=output / plot_name,
    )
    summary = {
        "schema_version": "v1.5-continuity-validation-summary-1.0",
        "case_id": str(case["case_id"]),
        "status": "provisional_piecewise_continuity_validated_on_midpoint_holdouts",
        "canonical_allocation_unchanged": True,
        "frozen_contract_entry_count": len(known_rows),
        "frozen_contracts_file": "frozen_conditional_contracts.json",
        "slice_analysis": {
            "slice_count": original_analysis["slice_count"],
            "mapped_single_crossing_slice_count": original_analysis[
                "mapped_single_crossing_slice_count"
            ],
            "checks": original_analysis["checks"],
        },
        "feasible_k1_interval": {
            "sampled_mapped_lower_ghz_per_v": 0.65,
            "sampled_mapped_upper_ghz_per_v": 1.05,
            "best_pn_refined_lower_ghz_per_v": feasible_interval[
                "refined_best_pn_interval"
            ]["lower_k1_ghz_per_v"],
            "best_pn_refined_upper_ghz_per_v": feasible_interval[
                "refined_best_pn_interval"
            ]["upper_k1_ghz_per_v"],
            "checks": feasible_interval["checks"],
        },
        "boundary_prediction": {
            "predictor": predictor["type"],
            "holdout_count": len(offgrid_allocations),
            "pn_spec_mae_db": sum(abs_spec_errors) / len(abs_spec_errors),
            "pn_spec_max_abs_error_db": max(abs_spec_errors),
            "pn_anchor_max_abs_error_db": max(abs_anchor_errors),
            "acceptance_tolerance_db": PREDICTION_ACCEPTANCE_TOLERANCE_DB,
            "within_acceptance_tolerance": max(abs_spec_errors)
            <= PREDICTION_ACCEPTANCE_TOLERANCE_DB,
            "all_off_grid": all(
                entry["holdout_point_is_off_grid"] for entry in offgrid_allocations
            ),
            "all_single_crossing": all(
                entry["single_crossing"] for entry in offgrid_allocations
            ),
            "all_boundary_systemtb_pass": all(
                entry["system_boundary_passed"] for entry in offgrid_allocations
            ),
            "all_boundary_blocktb_pass": all(
                entry["boundary_blocktb_passed"] for entry in offgrid_allocations
            ),
        },
        "candidate_replay": {
            "candidate_count": len(candidate_replays),
            "inside_count": sum(
                entry["candidate_kind"] == "predicted_contract_inside"
                for entry in candidate_replays
            ),
            "outside_count": sum(
                entry["candidate_kind"] == "predicted_contract_outside"
                for entry in candidate_replays
            ),
            **replay_validation["validation"],
        },
        "allocation_authority": {
            "continuous_mapping_promoted_to_canonical_v1_5": False,
            "reason": (
                "midpoint holdout evidence validates a provisional predictor; "
                "the frozen canonical map remains a nine-entry discrete table"
            ),
        },
        "artifacts": {
            "frozen_contracts": "frozen_conditional_contracts.json",
            "slice_single_crossing": "slice_single_crossing_analysis.json",
            "feasible_k1_interval": "feasible_k1_interval.json",
            "boundary_prediction": "continuous_boundary_prediction.json",
            "boundary_evolution_csv": "boundary_evolution.csv",
            "coupling_analysis_csv": "coupling_analysis.csv",
            "offgrid_boundary_allocations": "offgrid_boundary_allocations.json",
            "offgrid_holdout_csv": "offgrid_holdout.csv",
            "offgrid_candidate_replay": "offgrid_candidate_replay.json",
            "offgrid_candidate_replay_csv": "offgrid_candidate_replay.csv",
            "boundary_evolution_plot": plot_name,
        },
    }
    summary["summary_sha256"] = evidence_digest(summary)
    write_json(summary, output / "continuity_validation_summary.json")
    lines = [
        f"# V1.5 continuity validation: `{summary['case_id']}`",
        "",
        "## Result",
        "",
        "- Frozen conditional contracts: `9`",
        f"- Original slices: `{original_analysis['slice_count']}`",
        f"- Mapped single-crossing slices: `{original_analysis['mapped_single_crossing_slice_count']}`",
        f"- Off-grid midpoint holdouts: `{len(offgrid_allocations)}`",
        f"- PN_spec holdout MAE: `{summary['boundary_prediction']['pn_spec_mae_db']:.9f} dB`",
        f"- PN_spec holdout maximum absolute error: `{summary['boundary_prediction']['pn_spec_max_abs_error_db']:.9f} dB`",
        f"- Holdout within `{PREDICTION_ACCEPTANCE_TOLERANCE_DB} dB`: `{summary['boundary_prediction']['within_acceptance_tolerance']}`",
        f"- Boundary SystemTB / BlockTB: `{summary['boundary_prediction']['all_boundary_systemtb_pass']}` / `{summary['boundary_prediction']['all_boundary_blocktb_pass']}`",
        f"- Candidate replay count: `{len(candidate_replays)}`",
        f"- Inside-contract false positives: `{replay_validation['validation']['inside_contract_false_positive_count']}`",
        "",
        "## Interpretation",
        "",
        "The midpoint holdouts support a provisional piecewise-linear PN_spec(k1) predictor in the mapped domain.",
        "The canonical V1.5 allocation remains a discrete nine-entry table; continuous interpolation is not promoted as a production requirement.",
        "The refined k1 interval is a best-PN local feasibility interval, not a statement that every PN value is feasible throughout it.",
    ]
    (output / "continuity_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default=str(DEFAULT_CASE))
    parser.add_argument("--source-dir", default=str(DEFAULT_SOURCE_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    summary = run(args.case, args.source_dir, args.output_dir)
    print("Case:", summary["case_id"])
    print("Frozen contracts:", summary["frozen_contract_entry_count"])
    print("Off-grid holdouts:", summary["boundary_prediction"]["holdout_count"])
    print("PN_spec holdout MAE (dB):", summary["boundary_prediction"]["pn_spec_mae_db"])
    print("PN_spec max abs error (dB):", summary["boundary_prediction"]["pn_spec_max_abs_error_db"])
    print("Boundary SystemTB PASS:", summary["boundary_prediction"]["all_boundary_systemtb_pass"])
    print("Boundary BlockTB PASS:", summary["boundary_prediction"]["all_boundary_blocktb_pass"])
    print("Inside-contract false positives:", summary["candidate_replay"]["inside_contract_false_positive_count"])
    print("Artifacts:", Path(args.output_dir).resolve())


if __name__ == "__main__":
    main()
