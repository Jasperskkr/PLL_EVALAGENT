"""Build and replay a provisional PN--Kvco joint contract for V1.5.

The canonical V1.5 nine-entry PN conditional allocation remains untouched.
This experiment translates its condition axis into frozen-context measured
``kvco_max`` and checks a provisional joint rule:

    measured kvco_max is inside the mapped window, and
    measured worst PN <= piecewise PN_spec(kvco_max).

The Kvco window is a measured data domain, not an engineering-margin signoff.
The artifact therefore records margin policy as pending and keeps all claims
limited to the deterministic synthetic model and frozen context.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

from v1.allocation.design_space import DesignPointDefinition, DesignSpaceDefinition
from v1.allocation.multidim_evaluator import evaluate_design_point
from v1.backends.synthetic import SyntheticVCOBackend
from v1.io import evidence_digest, read_json, write_evidence_json
from v1.api.verification import VerificationRequest
from v1.model.pll_behavioral import VCOParams
from v1.model.instances import build_vco_instance
from v1.specs import SystemSpec, VCORequirement, load_case
from v1.verification.service import verify_block_assignment


ROOT = Path(__file__).resolve().parent
DEFAULT_CASE = ROOT / "v1" / "cases" / "vco_multidim_01.json"
DEFAULT_SOURCE = ROOT / "results" / "v1_5_kvco_mapping_v1_5"
DEFAULT_OUTPUT = ROOT / "results" / "v1_5_joint_contract_v1_5"


def _known_contract_rows(source: Path) -> list[Dict[str, float]]:
    mapping = read_json(source / "measured_kvco_mapping.json")
    rows = [row for row in mapping["rows"] if row["source"] == "mapped_boundary"]
    rows.sort(key=lambda row: float(row["kvco_max_hz_per_v"]))
    return [
        {
            "k1_hz_per_v": float(row["k1_hz_per_v"]),
            "k1_ghz_per_v": float(row["k1_ghz_per_v"]),
            "kvco_max_hz_per_v": float(row["kvco_max_hz_per_v"]),
            "kvco_max_ghz_per_v": float(row["kvco_max_hz_per_v"]) / 1.0e9,
            "boundary_measured_pn_dbc_hz": float(
                row["boundary_measured_pn_dbc_hz"]
            ),
            "pn_spec_dbc_hz": float(row["pn_spec_dbc_hz"]),
            "lock_time_s": float(row["lock_time_s"]),
        }
        for row in rows
    ]


def _interpolate(rows: Sequence[Mapping[str, float]], x: float) -> float | None:
    ordered = sorted(rows, key=lambda row: float(row["kvco_max_hz_per_v"]))
    if x < ordered[0]["kvco_max_hz_per_v"] or x > ordered[-1]["kvco_max_hz_per_v"]:
        return None
    for row in ordered:
        if x == row["kvco_max_hz_per_v"]:
            return float(row["pn_spec_dbc_hz"])
    lower = max(
        (row for row in ordered if row["kvco_max_hz_per_v"] < x),
        key=lambda row: row["kvco_max_hz_per_v"],
    )
    upper = min(
        (row for row in ordered if row["kvco_max_hz_per_v"] > x),
        key=lambda row: row["kvco_max_hz_per_v"],
    )
    weight = (x - lower["kvco_max_hz_per_v"]) / (
        upper["kvco_max_hz_per_v"] - lower["kvco_max_hz_per_v"]
    )
    return float(
        lower["pn_spec_dbc_hz"]
        + weight * (upper["pn_spec_dbc_hz"] - lower["pn_spec_dbc_hz"])
    )


def _evaluate_candidate(
    *,
    case: Mapping[str, Any],
    system_spec: SystemSpec,
    base_vco: VCOParams,
    design_space: DesignSpaceDefinition,
    rows: Sequence[Mapping[str, float]],
    candidate_id: str,
    k1_hz_per_v: float,
    pn_anchor_dbc_hz: float,
    candidate_class: str,
) -> Dict[str, Any]:
    values = {
        "pn_anchor_1mhz_dbc_hz": float(pn_anchor_dbc_hz),
        "k1_hz_per_v": float(k1_hz_per_v),
    }
    point = DesignPointDefinition(
        point_id=design_space.point_id(values),
        ordinal=-1,
        values=values,
    )
    evaluated = evaluate_design_point(case, system_spec, base_vco, point)
    behavior = evaluated["behavior_vector"]
    measured_kvco_max = float(behavior["kvco_max_hz_per_v"])
    measured_pn = float(behavior["worst_phase_noise_1mhz_dbc_hz"])
    kvco_min = float(rows[0]["kvco_max_hz_per_v"])
    kvco_max = float(rows[-1]["kvco_max_hz_per_v"])
    predicted_pn_spec = _interpolate(rows, measured_kvco_max)
    window_pass = kvco_min <= measured_kvco_max <= kvco_max
    pn_relation_pass = (
        predicted_pn_spec is not None and measured_pn <= predicted_pn_spec
    )
    joint_pass = window_pass and pn_relation_pass
    requirement = VCORequirement(
        phase_noise_1mhz_max_dbc_hz=(
            predicted_pn_spec if predicted_pn_spec is not None else measured_pn - 1.0
        ),
        kvco_max_hz_per_v=kvco_max,
        power_max_w=float(case["system_spec"]["limits"]["power_max_w"]),
        margin_db=1.5,
    )
    verification = verify_block_assignment(
        VerificationRequest(
            system_spec=system_spec,
            block_spec=requirement,
            realized_instance=VCOParams(
                **dict(evaluated["realized_instance"]["parameters"])
            ),
            operating_context=dict(case["block_context"]),
            block_id="VCO",
            backend_id="synthetic_vco_v1",
            request_id=f"{case['case_id']}:joint-contract:{candidate_id}",
            keep_raw=False,
        ),
        backend=SyntheticVCOBackend(),
    )
    replay_identical = (
        verification["system_tb"]["metrics"] == evaluated["system_tb"]["metrics"]
        and verification["system_tb"]["checks"] == evaluated["system_tb"]["checks"]
        and verification["system_tb"]["residuals"] == evaluated["system_tb"]["residuals"]
    )
    return {
        "candidate_id": candidate_id,
        "candidate_class": candidate_class,
        "design_vector": values,
        "point_id": evaluated["point_id"],
        "measured_behavior": dict(behavior),
        "system_metrics": dict(evaluated["system_tb"]["metrics"]),
        "system_checks": dict(evaluated["system_tb"]["checks"]),
        "contract_prediction": {
            "kvco_window_hz_per_v": [kvco_min, kvco_max],
            "measured_kvco_max_hz_per_v": measured_kvco_max,
            "predicted_pn_spec_dbc_hz": predicted_pn_spec,
            "measured_pn_dbc_hz": measured_pn,
            "kvco_window_pass": window_pass,
            "pn_relation_pass": pn_relation_pass,
            "joint_contract_pass": joint_pass,
        },
        "verification": {
            "blocktb_passed": bool(verification["block_tb"]["passed"]),
            "systemtb_passed": bool(verification["system_tb"]["passed"]),
            "context_covered": bool(verification["context_coverage"]["passed"]),
            "same_instance_used": bool(
                verification["provenance"][
                    "realized_instance_shared_by_block_and_system_tb"
                ]
            ),
            "systemtb_replay_identical": replay_identical,
            "blocktb_checks": dict(verification["block_tb"]["checks"]),
        },
    }


def run(
    case_path: str | Path = DEFAULT_CASE,
    source_dir: str | Path = DEFAULT_SOURCE,
    output_dir: str | Path = DEFAULT_OUTPUT,
) -> Dict[str, Any]:
    case = load_case(case_path)
    source = Path(source_dir).resolve()
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    mapping_artifact = read_json(source / "measured_kvco_mapping.json")
    rows = _known_contract_rows(source)
    if len(rows) != 9:
        raise ValueError(f"expected nine mapped contract rows, got {len(rows)}")
    axis_decision = read_json(
        source / "joint_contract_axis_decision.json"
    )
    if axis_decision["selected_primary_block_axis"] != "kvco_max_hz_per_v":
        raise ValueError("joint contract script requires the qualified kvco_max axis")

    system_spec = SystemSpec.from_dict(case["system_spec"])
    base_vco = build_vco_instance(VCOParams(), case.get("base_vco", {}))
    design_space = DesignSpaceDefinition.from_dict(case["design_space"])
    required_window = {
        "metric": "kvco_max_hz_per_v",
        "lower_hz_per_v": rows[0]["kvco_max_hz_per_v"],
        "upper_hz_per_v": rows[-1]["kvco_max_hz_per_v"],
        "lower_ghz_per_v": rows[0]["kvco_max_ghz_per_v"],
        "upper_ghz_per_v": rows[-1]["kvco_max_ghz_per_v"],
        "operator": "inclusive_window",
        "source": "nine canonical mapped boundary contracts",
        "engineering_margin": {
            "status": "pending",
            "value_hz_per_v": None,
            "data_derived": False,
        },
        "interpretation": (
            "measured contract domain for the provisional joint rule; a conservative "
            "sufficient-condition window, not a necessary condition for every feasible candidate"
        ),
    }
    contract = {
        "schema_version": "v1.5-provisional-joint-pn-kvco-contract-1.0",
        "status": "provisional_joint_contract_pending_kvco_margin",
        "contract_type": "measured_pn_by_measured_kvco_max",
        "canonical_v1_5_allocation_unchanged": True,
        "primary_measured_axis": "kvco_max_hz_per_v",
        "required_kvco_window": required_window,
        "pn_relation": {
            "metric": "worst_phase_noise_1mhz_dbc_hz",
            "requirement_metric": "phase_noise_1mhz_max_dbc_hz",
            "direction": "upper_bound_more_negative_is_tighter",
            "form": "piecewise_linear_provisional_between_nine_canonical_rows",
            "engineering_margin_db": 1.5,
            "rows": rows,
            "interpolation_promoted_to_canonical": False,
        },
        "source_evidence": {
            "measured_kvco_mapping": "measured_kvco_mapping.json",
            "mapping_sha256": mapping_artifact["mapping_sha256"],
            "axis_decision": "joint_contract_axis_decision.json",
            "decision_sha256": axis_decision["decision_sha256"],
        },
        "claim_boundary": (
            "Provisional measured PN--Kvco joint sufficiency contract in one frozen "
            "synthetic behavioral context; Kvco margin, necessity, PVT and transistor-level signoff remain pending."
        ),
    }
    contract["contract_sha256"] = evidence_digest(contract)
    write_evidence_json(contract, output / "provisional_joint_contract.json")

    candidates = [
        ("inside_joint_contract_080", "inside_joint_contract", 800_000_000.0, -120.63477630615234),
        ("inside_joint_contract_090", "inside_joint_contract", 900_000_000.0, -120.2515022277832),
        ("inside_joint_contract_100", "inside_joint_contract", 1_000_000_000.0, -119.88751430511475),
        ("pn_outside_relation_080", "pn_outside_relation", 800_000_000.0, -120.23477630615234),
        ("pn_outside_relation_100", "pn_outside_relation", 1_000_000_000.0, -119.48751430511475),
        ("kvco_below_window_but_system_pass", "kvco_below_window", 625_000_000.0, -124.0),
        ("kvco_above_window_and_lock_fail", "kvco_above_window", 1_075_000_000.0, -124.0),
    ]
    results = [
        _evaluate_candidate(
            case=case,
            system_spec=system_spec,
            base_vco=base_vco,
            design_space=design_space,
            rows=rows,
            candidate_id=candidate_id,
            k1_hz_per_v=k1,
            pn_anchor_dbc_hz=pn,
            candidate_class=candidate_class,
        )
        for candidate_id, candidate_class, k1, pn in candidates
    ]
    validation = {
        "inside_joint_contract_count": sum(
            item["candidate_class"] == "inside_joint_contract" for item in results
        ),
        "inside_joint_contract_all_contract_pass": all(
            item["contract_prediction"]["joint_contract_pass"]
            for item in results
            if item["candidate_class"] == "inside_joint_contract"
        ),
        "inside_joint_contract_all_systemtb_pass": all(
            item["verification"]["systemtb_passed"]
            for item in results
            if item["candidate_class"] == "inside_joint_contract"
        ),
        "inside_joint_contract_false_positive_count": sum(
            item["contract_prediction"]["joint_contract_pass"]
            and not item["verification"]["systemtb_passed"]
            for item in results
            if item["candidate_class"] == "inside_joint_contract"
        ),
        "all_independent_systemtb_replays_identical": all(
            item["verification"]["systemtb_replay_identical"] for item in results
        ),
        "pn_outside_candidates_rejected_by_contract": all(
            not item["contract_prediction"]["joint_contract_pass"]
            for item in results
            if item["candidate_class"] == "pn_outside_relation"
        ),
        "kvco_outside_candidates_rejected_by_contract": all(
            not item["contract_prediction"]["joint_contract_pass"]
            for item in results
            if item["candidate_class"] in {"kvco_below_window", "kvco_above_window"}
        ),
    }
    artifact = {
        "schema_version": "v1.5-joint-contract-candidate-validation-1.0",
        "status": "provisional_joint_contract_replay_completed",
        "source_contract_sha256": contract["contract_sha256"],
        "candidate_count": len(results),
        "entries": results,
        "validation": validation,
        "claim_boundary": contract["claim_boundary"],
    }
    artifact["validation_sha256"] = evidence_digest(artifact)
    write_evidence_json(artifact, output / "joint_contract_candidate_validation.json")

    summary = {
        "schema_version": "v1.5-joint-contract-summary-1.0",
        "status": "provisional_joint_contract_validated_as_sufficient_condition_on_selected_candidates",
        "source_axis": "kvco_max_hz_per_v",
        "required_window": required_window,
        "pn_relation_row_count": len(rows),
        "pn_engineering_margin_db": 1.5,
        "kvco_engineering_margin_status": "pending",
        "candidate_validation": validation,
        "canonical_v1_5_allocation_unchanged": True,
        "joint_contract_is_necessary_condition": False,
        "artifacts": {
            "provisional_joint_contract": "provisional_joint_contract.json",
            "candidate_validation": "joint_contract_candidate_validation.json",
            "report": "joint_contract_report.md",
        },
    }
    summary["summary_sha256"] = evidence_digest(summary)
    write_evidence_json(summary, output / "joint_contract_summary.json")
    (output / "joint_contract_report.md").write_text(
        "\n".join(
            [
                "# V1.5 provisional PN–Kvco joint contract",
                "",
                f"- Primary measured axis: `kvco_max_hz_per_v`",
                f"- Required measured window: `{required_window['lower_ghz_per_v']:.3f}` to `{required_window['upper_ghz_per_v']:.3f} GHz/V`",
                f"- PN relation rows: `{len(rows)}`",
                "- PN engineering margin: `1.5 dB`",
                "- Kvco engineering margin: `pending`",
                f"- Inside-contract candidates: `{validation['inside_joint_contract_count']}`",
                f"- Inside-contract false positives: `{validation['inside_joint_contract_false_positive_count']}`",
                f"- Independent replay identical: `{validation['all_independent_systemtb_replays_identical']}`",
                "",
                "The contract is a sufficient-condition experiment. Candidates outside the provisional window or PN relation remain informative but are not treated as necessary-condition failures.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default=str(DEFAULT_CASE))
    parser.add_argument("--source-dir", default=str(DEFAULT_SOURCE))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    result = run(args.case, args.source_dir, args.output_dir)
    print("Status:", result["status"])
    print("Kvco window (GHz/V):", result["required_window"]["lower_ghz_per_v"], "to", result["required_window"]["upper_ghz_per_v"])
    print("Inside false positives:", result["candidate_validation"]["inside_joint_contract_false_positive_count"])
    print("Replay identical:", result["candidate_validation"]["all_independent_systemtb_replays_identical"])
    print("Artifacts:", Path(args.output_dir).resolve())


if __name__ == "__main__":
    main()
