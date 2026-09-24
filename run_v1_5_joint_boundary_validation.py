"""Validate the provisional PN--Kvco joint rule near unseen boundaries.

This is a holdout experiment for the provisional V1.5 joint contract.  The
nine canonical rows are kept frozen.  For each off-grid k1 midpoint, a probe
measurement establishes the deterministic PN-anchor offset, then two
boundary-adjacent candidates are generated around the interpolated PN
contract: one 0.10 dB inside and one 0.10 dB outside.  Each candidate is
checked through the independent BlockTB/SystemTB verification service.

The script does not promote interpolation or a Kvco engineering margin to
canonical status.  It only tests the implication:

    joint contract PASS -> BlockTB PASS -> SystemTB PASS

on previously unused k1 slices.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any, Dict, Mapping

from v1.allocation.design_space import DesignPointDefinition, DesignSpaceDefinition
from v1.allocation.multidim_evaluator import evaluate_design_point
from v1.model.pll_behavioral import VCOParams
from v1.model.instances import build_vco_instance
from v1.io import evidence_digest, read_json, write_evidence_json
from v1.specs import SystemSpec, load_case

from run_v1_5_joint_contract import (
    _evaluate_candidate,
    _interpolate,
    _known_contract_rows,
)


ROOT = Path(__file__).resolve().parent
DEFAULT_CASE = ROOT / "v1" / "cases" / "vco_multidim_01.json"
DEFAULT_SOURCE = ROOT / "results" / "v1_5_kvco_mapping_v1_5"
DEFAULT_OUTPUT = ROOT / "results" / "v1_5_joint_boundary_validation_v1_5"


def _probe(
    case: Mapping[str, Any],
    system_spec: SystemSpec,
    base_vco: VCOParams,
    design_space: DesignSpaceDefinition,
    k1_hz_per_v: float,
    pn_anchor_dbc_hz: float,
) -> Dict[str, Any]:
    values = {
        "pn_anchor_1mhz_dbc_hz": float(pn_anchor_dbc_hz),
        "k1_hz_per_v": float(k1_hz_per_v),
    }
    point = DesignPointDefinition(
        point_id=design_space.point_id(values), ordinal=-1, values=values
    )
    return evaluate_design_point(case, system_spec, base_vco, point)


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
    axis_decision = read_json(source / "joint_contract_axis_decision.json")
    rows = _known_contract_rows(source)
    if len(rows) != 9:
        raise ValueError(f"expected nine mapped contract rows, got {len(rows)}")

    system_spec = SystemSpec.from_dict(case["system_spec"])
    base_vco = build_vco_instance(VCOParams(), case.get("base_vco", {}))
    design_space = DesignSpaceDefinition.from_dict(case["design_space"])

    # These are the eight midpoints used by the continuity holdout and are
    # absent from the nine canonical k1 rows.
    k1_values = [675e6 + i * 50e6 for i in range(8)]
    margin_db = 0.10
    probe_anchor = -121.0
    entries: list[Dict[str, Any]] = []
    probe_rows: list[Dict[str, Any]] = []

    for index, k1_hz_per_v in enumerate(k1_values):
        probe = _probe(
            case,
            system_spec,
            base_vco,
            design_space,
            k1_hz_per_v,
            probe_anchor,
        )
        behavior = probe["behavior_vector"]
        measured_kvco = float(behavior["kvco_max_hz_per_v"])
        measured_pn = float(behavior["worst_phase_noise_1mhz_dbc_hz"])
        pn_offset = measured_pn - probe_anchor
        predicted_spec = _interpolate(rows, measured_kvco)
        if predicted_spec is None:
            raise ValueError(f"off-grid k1={k1_hz_per_v} maps outside Kvco rows")
        target_anchor = float(predicted_spec - pn_offset)
        probe_rows.append(
            {
                "k1_hz_per_v": k1_hz_per_v,
                "k1_ghz_per_v": k1_hz_per_v / 1.0e9,
                "probe_anchor_dbc_hz": probe_anchor,
                "probe_measured_pn_dbc_hz": measured_pn,
                "pn_offset_dbc_hz": pn_offset,
                "measured_kvco_max_hz_per_v": measured_kvco,
                "predicted_pn_spec_dbc_hz": predicted_spec,
                "target_anchor_dbc_hz": target_anchor,
            }
        )

        for side, delta in (("inside", -margin_db), ("outside", margin_db)):
            candidate_anchor = target_anchor + delta
            candidate = _evaluate_candidate(
                case=case,
                system_spec=system_spec,
                base_vco=base_vco,
                design_space=design_space,
                rows=rows,
                candidate_id=f"offgrid_{index:02d}_{side}",
                k1_hz_per_v=k1_hz_per_v,
                pn_anchor_dbc_hz=candidate_anchor,
                candidate_class=f"offgrid_boundary_adjacent_{side}",
            )
            candidate["boundary_setup"] = {
                "predicted_boundary_pn_spec_dbc_hz": predicted_spec,
                "target_anchor_dbc_hz": target_anchor,
                "offset_from_target_dbc": delta,
                "offgrid_k1": True,
            }
            entries.append(candidate)

    inside = [e for e in entries if e["candidate_class"].endswith("_inside")]
    outside = [e for e in entries if e["candidate_class"].endswith("_outside")]
    validation = {
        "offgrid_k1_count": len(k1_values),
        "boundary_adjacent_candidate_count": len(entries),
        "inside_count": len(inside),
        "inside_joint_contract_all_pass": all(
            e["contract_prediction"]["joint_contract_pass"] for e in inside
        ),
        "inside_blocktb_all_pass": all(e["verification"]["blocktb_passed"] for e in inside),
        "inside_systemtb_all_pass": all(e["verification"]["systemtb_passed"] for e in inside),
        "inside_false_positive_count": sum(
            e["contract_prediction"]["joint_contract_pass"]
            and not e["verification"]["systemtb_passed"]
            for e in inside
        ),
        "outside_count": len(outside),
        "outside_all_rejected_by_joint_contract": all(
            not e["contract_prediction"]["joint_contract_pass"] for e in outside
        ),
        "outside_blocktb_all_rejected": all(
            not e["verification"]["blocktb_passed"] for e in outside
        ),
        "all_independent_systemtb_replays_identical": all(
            e["verification"]["systemtb_replay_identical"] for e in entries
        ),
    }
    artifact = {
        "schema_version": "v1.5-joint-boundary-validation-1.0",
        "status": "offgrid_boundary_adjacent_joint_contract_validated",
        "source": {
            "canonical_row_count": len(rows),
            "kvco_axis": "kvco_max_hz_per_v",
            "mapping_artifact": "measured_kvco_mapping.json",
            "mapping_sha256": mapping_artifact["mapping_sha256"],
            "axis_decision_artifact": "joint_contract_axis_decision.json",
            "decision_sha256": axis_decision["decision_sha256"],
        },
        "generation": {
            "k1_values_hz_per_v": k1_values,
            "probe_anchor_dbc_hz": probe_anchor,
            "boundary_offset_db": margin_db,
            "method": "probe_offset_then_piecewise_contract_target",
        },
        "probe_rows": probe_rows,
        "entries": entries,
        "validation": validation,
        "claim_boundary": (
            "Holdout validation of the provisional PN--Kvco sufficient-condition "
            "rule in the frozen synthetic behavioral context; no Kvco engineering "
            "margin, necessity, PVT or transistor-level signoff is claimed."
        ),
    }
    artifact["validation_sha256"] = evidence_digest(artifact)
    write_evidence_json(artifact, output / "joint_boundary_validation.json")

    csv_path = output / "joint_boundary_validation.csv"
    fields = [
        "candidate_id",
        "candidate_class",
        "k1_ghz_per_v",
        "pn_anchor_1mhz_dbc_hz",
        "measured_kvco_max_ghz_per_v",
        "predicted_pn_spec_dbc_hz",
        "measured_pn_dbc_hz",
        "joint_contract_pass",
        "blocktb_passed",
        "systemtb_passed",
        "systemtb_replay_identical",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in entries:
            prediction = item["contract_prediction"]
            verification = item["verification"]
            writer.writerow(
                {
                    "candidate_id": item["candidate_id"],
                    "candidate_class": item["candidate_class"],
                    "k1_ghz_per_v": item["design_vector"]["k1_hz_per_v"] / 1.0e9,
                    "pn_anchor_1mhz_dbc_hz": item["design_vector"]["pn_anchor_1mhz_dbc_hz"],
                    "measured_kvco_max_ghz_per_v": prediction["measured_kvco_max_hz_per_v"] / 1.0e9,
                    "predicted_pn_spec_dbc_hz": prediction["predicted_pn_spec_dbc_hz"],
                    "measured_pn_dbc_hz": prediction["measured_pn_dbc_hz"],
                    "joint_contract_pass": prediction["joint_contract_pass"],
                    "blocktb_passed": verification["blocktb_passed"],
                    "systemtb_passed": verification["systemtb_passed"],
                    "systemtb_replay_identical": verification["systemtb_replay_identical"],
                }
            )

    report_lines = [
        "# V1.5 off-grid joint-contract boundary validation",
        "",
        "Canonical nine PN–Kvco rows were frozen. Eight unseen k1 midpoints were evaluated with one candidate 0.10 dB inside and one 0.10 dB outside the interpolated PN relation.",
        "",
        f"- Off-grid k1 slices: `{validation['offgrid_k1_count']}`",
        f"- Boundary-adjacent candidates: `{validation['boundary_adjacent_candidate_count']}`",
        f"- Inside: joint contract `{validation['inside_joint_contract_all_pass']}`, BlockTB `{validation['inside_blocktb_all_pass']}`, SystemTB `{validation['inside_systemtb_all_pass']}`",
        f"- Inside false positives: `{validation['inside_false_positive_count']}`",
        f"- Outside candidates rejected by joint contract: `{validation['outside_all_rejected_by_joint_contract']}`",
        f"- Outside candidates rejected by BlockTB: `{validation['outside_blocktb_all_rejected']}`",
        f"- Independent SystemTB replay identical: `{validation['all_independent_systemtb_replays_identical']}`",
        "",
        "This is holdout evidence for a sufficient-condition rule. It does not promote the interpolated relation to the canonical allocation and does not define a Kvco engineering margin.",
    ]
    (output / "joint_boundary_validation_report.md").write_text(
        "\n".join(report_lines) + "\n", encoding="utf-8"
    )
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default=str(DEFAULT_CASE))
    parser.add_argument("--source-dir", default=str(DEFAULT_SOURCE))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    result = run(args.case, args.source_dir, args.output_dir)
    validation = result["validation"]
    print("Status:", result["status"])
    print("Inside joint/BlockTB/SystemTB:", validation["inside_joint_contract_all_pass"], validation["inside_blocktb_all_pass"], validation["inside_systemtb_all_pass"])
    print("Inside false positives:", validation["inside_false_positive_count"])
    print("Outside rejected:", validation["outside_all_rejected_by_joint_contract"])
    print("Artifacts:", Path(args.output_dir).resolve())


if __name__ == "__main__":
    main()
