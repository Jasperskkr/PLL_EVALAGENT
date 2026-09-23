"""Evaluate the deterministic V1.5 PN-anchor by k1 design grid."""

from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Sequence

from v1.allocation.design_space import DesignSpaceDefinition
from v1.allocation.boundaries import build_system_boundary_map
from v1.allocation.boundary_contract import extract_boundary_block_contract
from v1.allocation.conditional_allocation import (
    build_conditional_block_spec_map,
    validate_conditional_contract_prediction,
    validate_conditional_block_spec_map,
)
from v1.allocation.multidim_evaluator import evaluate_design_point
from v1.allocation.regions import (
    build_capability_region,
    build_system_feasible_region,
)
from v1.allocation.selection import build_replay_evidence, select_candidate
from v1.model.pll_behavioral import VCOParams
from v1.graph.audit_v15 import audit_v15_graph
from v1.graph.compiler_v15 import build_v15_graph_artifact
from v1.graph.queries import factor_view
from v1.pipeline import build_vco_instance, write_json
from v1.specs import SystemSpec, load_case


ROOT = Path(__file__).resolve().parent
DEFAULT_CASE = ROOT / "v1" / "cases" / "vco_multidim_01.json"
DEFAULT_OUTPUT = ROOT / "results" / "v1_5_vco_multidim_01"


def _json_line(value: Mapping[str, Any]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _write_jsonl(
    records: Iterable[Mapping[str, Any]], path: Path
) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = sha256()
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            line = _json_line(record) + "\n"
            handle.write(line)
            digest.update(line.encode("utf-8"))
    return digest.hexdigest()


def _csv_row(record: Mapping[str, Any]) -> Dict[str, Any]:
    values = record["design_vector"]["values"]
    behavior = record["behavior_vector"]
    metrics = record["system_tb"]["metrics"]
    residuals = record["system_tb"]["residuals"]
    status = record["status"]
    return {
        "point_id": record["point_id"],
        "ordinal": record["ordinal"],
        "pn_anchor_1mhz_dbc_hz": values["pn_anchor_1mhz_dbc_hz"],
        "k1_hz_per_v": values["k1_hz_per_v"],
        "block_feasible": status["block_feasible"],
        "system_constraints_passed": status["system_constraints_passed"],
        "context_covered": status["context_covered"],
        "jointly_feasible": status["jointly_feasible"],
        "worst_phase_noise_1mhz_dbc_hz": behavior[
            "worst_phase_noise_1mhz_dbc_hz"
        ],
        "kvco_min_hz_per_v": behavior["kvco_min_hz_per_v"],
        "kvco_max_hz_per_v": behavior["kvco_max_hz_per_v"],
        "frequency_min_hz": behavior["frequency_min_hz"],
        "frequency_max_hz": behavior["frequency_max_hz"],
        "worst_power_w": behavior["worst_power_w"],
        "integrated_jitter_s": metrics["integrated_jitter_s"],
        "lock_time_s": metrics["lock_time_s"],
        "output_frequency_hz": metrics["output_frequency_hz"],
        "system_power_w": metrics["power_w"],
        "locked_all_contexts": metrics["locked_all_contexts"],
        "integrated_jitter_residual_s": residuals[
            "integrated_jitter_residual_s_max"
        ],
        "lock_time_residual_s": residuals["lock_time_residual_s_max"],
        "output_frequency_residual_hz": residuals[
            "output_frequency_residual_hz_max"
        ],
        "power_residual_w": residuals["power_residual_w_max"],
        "failure_reasons": ";".join(status["failure_reasons"]),
    }


def _contract_csv_row(entry: Mapping[str, Any]) -> Dict[str, Any]:
    boundary = entry["source_system_boundary"]
    behavior = entry["measured_block_behavior"]
    system = entry["system_boundary_confirmation"]
    replay = entry["independent_replay_validation"]
    return {
        "k1_hz_per_v": entry["condition"]["value"],
        "pn_anchor_boundary_pass_dbc_hz": boundary["passing_value"],
        "pn_anchor_nearest_fail_dbc_hz": boundary["nearest_failing_value"],
        "boundary_bracket_width_db": boundary["bracket_width"],
        "worst_measured_phase_noise_1mhz_dbc_hz": behavior[
            "worst_phase_noise_1mhz_dbc_hz"
        ],
        "kvco_min_hz_per_v": behavior["kvco_min_hz_per_v"],
        "kvco_max_hz_per_v": behavior["kvco_max_hz_per_v"],
        "frequency_min_hz": behavior["frequency_min_hz"],
        "frequency_max_hz": behavior["frequency_max_hz"],
        "worst_power_w": behavior["worst_power_w"],
        "integrated_jitter_s": system["metrics"]["integrated_jitter_s"],
        "lock_time_s": system["metrics"]["lock_time_s"],
        "limiting_system_checks": ";".join(
            boundary["limiting_system_checks"]
        ),
        "block_tb_passed": entry["block_tb"]["passed"],
        "system_boundary_passed": system["passed"],
        "independent_replay_passed": replay["passed"],
        "hidden_parameters_invariant": replay[
            "non_design_parameters_unchanged"
        ],
        "frozen_context_matches": replay["frozen_context_matches"],
    }


def _block_spec_csv_row(entry: Mapping[str, Any]) -> Dict[str, Any]:
    boundary = entry["source_boundary"]
    behavior = entry["source_boundary_behavior"]
    allocated = entry["allocated_block_spec"]
    return {
        "k1_hz_per_v": entry["condition"]["value"],
        "pn_anchor_boundary_pass_dbc_hz": boundary["passing_value"],
        "worst_measured_phase_noise_at_boundary_dbc_hz": behavior[
            "worst_phase_noise_1mhz_dbc_hz"
        ],
        "engineering_margin_db": allocated["margin_db"],
        "allocated_phase_noise_1mhz_max_dbc_hz": allocated[
            "phase_noise_1mhz_max_dbc_hz"
        ],
        "power_max_w": allocated["power_max_w"],
        "condition_semantics": entry["condition_semantics"],
    }


def _write_csv(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _exclusive_failure_counts(
    records: Sequence[Mapping[str, Any]], active_checks: Sequence[str]
) -> Dict[str, int]:
    counts = {check: 0 for check in active_checks}
    for record in records:
        if not record["status"]["block_feasible"]:
            continue
        if not record["status"]["context_covered"]:
            continue
        failed = {
            str(name)
            for name, passed in record["system_tb"]["checks"].items()
            if not passed
        }
        for check in active_checks:
            if failed == {check}:
                counts[check] += 1
    return counts


def _write_summary_markdown(path: Path, summary: Mapping[str, Any]) -> None:
    counts = summary["classification_counts"]
    effects = summary["exclusive_active_constraint_failure_counts"]
    regions = summary["region_summary"]
    selection = summary["selection_summary"]
    graph = summary["graph_summary"]
    boundaries = summary["system_boundary_summary"]
    contract = summary["boundary_contract_summary"]
    allocation = summary["conditional_allocation_summary"]
    lines = [
        f"# V1.5 multidimensional evaluation: `{summary['case_id']}`",
        "",
        "## Deterministic result",
        "",
        f"- Sampled design points: `{counts['total']}`",
        f"- Block-feasible points: `{counts['block_feasible']}`",
        f"- Block-infeasible points: `{counts['block_infeasible']}`",
        f"- SystemTB PASS points: `{counts['system_constraints_passed']}`",
        f"- Context-covered points: `{counts['context_covered']}`",
        f"- Jointly feasible points: `{counts['jointly_feasible']}`",
        f"- Capability Region members: `{regions['capability_member_count']}`",
        f"- System-feasible Region members: `{regions['system_feasible_member_count']}`",
        f"- Capability boundary transitions: `{regions['capability_boundary_transition_count']}`",
        f"- System-feasible boundary transitions: `{regions['system_boundary_transition_count']}`",
        f"- Refined conditional system boundaries: `{boundaries['mapped_boundary_count']}`",
        f"- Unmapped k1 slices: `{boundaries['unmapped_slice_count']}`",
        f"- Extracted boundary Block contracts: `{contract['entry_count']}`",
        f"- Boundary contract validation PASS: `{contract['validation_passed']}`",
        f"- Hidden-parameter invariance PASS: `{contract['hidden_parameters_invariant']}`",
        f"- Conditional BlockSpec entries: `{allocation['allocated_entry_count']}`",
        f"- Conditional candidate validations: `{allocation['validated_condition_count']}`",
        f"- Contract-prediction candidates replayed: `{allocation['contract_prediction_candidate_count']}`",
        f"- Contract-certified candidates: `{allocation['contract_prediction_certified_count']}`",
        f"- Contract false positives: `{allocation['contract_prediction_false_positive_count']}`",
        f"- Uncertified SystemTB PASS candidates: `{allocation['contract_prediction_uncertified_system_pass_count']}`",
        f"- Contract prediction PASS: `{allocation['contract_prediction_passed']}`",
        f"- Engineering margin: `{allocation['engineering_margin_db']} dB`",
        f"- BlockSpec mapping status: `{allocation['block_spec_mapping_status']}`",
        f"- Selected point: `{selection['selected_point_id']}`",
        f"- Selected DesignVector: `{selection['selected_design_vector']}`",
        f"- Independent replay identical: `{selection['replay_identical']}`",
        f"- Graph audit PASS: `{graph['audit_passed']}`",
        f"- Graph nodes / edges: `{graph['node_count']} / {graph['edge_count']}`",
        f"- Sample-set SHA-256: `{summary['sample_set_sha256']}`",
        "",
        "## Active constraint evidence",
        "",
    ]
    for name, count in effects.items():
        lines.append(f"- `{name}`-only failing Block-valid points: `{count}`")
    lines.extend(
        [
            "",
            "Every point uses one realized VCO instance for frozen-context BlockTB and SystemTB.",
            "The two regions preserve their sampled point topology; reported min/max bounds are summaries only.",
            "The conditional SystemSpec boundary is refined per k1 slice and recorded in system_boundary_map.json.",
            "Each mapped passing boundary is independently replayed through frozen-context BlockTB and recorded in boundary_block_contract.json.",
            "The boundary contract is a discrete validated table; interpolation is not claimed.",
            "A fixed V1.0-baseline engineering margin is applied independently to every mapped k1 slice.",
            "Each allocated conditional BlockSpec has one least-overdesigned candidate validated by BlockTB and independent SystemTB replay.",
            "Across all mapped-slice implementation candidates, every BlockSpec-PASS replay passed SystemTB; BlockSpec-FAIL candidates remain uncertified rather than being used as necessary-condition evidence.",
            "Unmapped k1 slices remain explicitly unallocated; interpolation is not claimed.",
            "The selected point is an interior sampled point chosen by minimum normalized distance from the base VCO.",
            "No Pareto claim is made. TypedGraph v2 records every sampled point, both regions, selection, and replay evidence.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(
    case_path: str | Path = DEFAULT_CASE,
    output_dir: str | Path = DEFAULT_OUTPUT,
) -> Dict[str, Any]:
    case = load_case(case_path)
    system_spec = SystemSpec.from_dict(case["system_spec"])
    base_vco = build_vco_instance(VCOParams(), case.get("base_vco", {}))
    design_space = DesignSpaceDefinition.from_dict(case["design_space"])
    points = list(design_space.iter_points())

    records = [
        evaluate_design_point(case, system_spec, base_vco, point)
        for point in points
    ]
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)

    write_json(
        {
            "schema_version": "v1.5-design-space-artifact-1.0",
            "case_id": case["case_id"],
            "definition": design_space.to_dict(),
            "points": [point.to_dict() for point in points],
        },
        output / "design_space.json",
    )
    sample_set_sha256 = _write_jsonl(records, output / "sampled_points.jsonl")
    _write_csv([_csv_row(record) for record in records], output / "sampled_points.csv")

    system_boundary_map = build_system_boundary_map(
        case=case,
        records=records,
        design_space=design_space,
        system_spec=system_spec,
        base_vco=base_vco,
        sample_set_sha256=sample_set_sha256,
    )
    write_json(system_boundary_map, output / "system_boundary_map.json")

    boundary_block_contract = extract_boundary_block_contract(
        case=case,
        system_boundary_map=system_boundary_map,
        design_space=design_space,
        system_spec=system_spec,
        base_vco=base_vco,
    )
    write_json(
        boundary_block_contract,
        output / "boundary_block_contract.json",
    )
    _write_csv(
        [
            _contract_csv_row(entry)
            for entry in boundary_block_contract["entries"]
        ],
        output / "boundary_block_contract.csv",
    )

    conditional_block_spec_map = build_conditional_block_spec_map(
        case=case,
        boundary_block_contract=boundary_block_contract,
    )
    write_json(
        conditional_block_spec_map,
        output / "conditional_block_spec_map.json",
    )
    _write_csv(
        [
            _block_spec_csv_row(entry)
            for entry in conditional_block_spec_map["entries"]
        ],
        output / "conditional_block_spec_map.csv",
    )

    capability_region = build_capability_region(
        str(case["case_id"]),
        records,
        design_space,
        sample_set_sha256,
    )
    system_feasible_region = build_system_feasible_region(
        str(case["case_id"]),
        records,
        design_space,
        sample_set_sha256,
    )
    write_json(capability_region, output / "capability_region.json")
    write_json(system_feasible_region, output / "system_feasible_region.json")

    selection_decision = select_candidate(
        case,
        records,
        design_space,
        base_vco,
    )
    selected_point_id = str(
        selection_decision["selected_candidate"]["point_id"]
    )
    point_by_id = {point.point_id: point for point in points}
    record_by_id = {str(record["point_id"]): record for record in records}
    if selected_point_id not in point_by_id or selected_point_id not in record_by_id:
        raise ValueError("selected point does not resolve to sampled evidence")
    replay_record = evaluate_design_point(
        case,
        system_spec,
        base_vco,
        point_by_id[selected_point_id],
    )
    replay_evidence = build_replay_evidence(
        selection_decision,
        record_by_id[selected_point_id],
        replay_record,
    )
    if not (
        replay_evidence["identical_to_sampled_evaluation"]
        and replay_evidence["replay_jointly_feasible"]
    ):
        raise ValueError("selected candidate independent replay failed")
    write_json(selection_decision, output / "selection_decision.json")
    write_json(replay_evidence, output / "selected_candidate_replay.json")

    conditional_candidate_validation = validate_conditional_block_spec_map(
        case=case,
        system_boundary_map=system_boundary_map,
        conditional_block_spec_map=conditional_block_spec_map,
        records=records,
        design_space=design_space,
        system_spec=system_spec,
        base_vco=base_vco,
        selected_point_id=selected_point_id,
    )
    write_json(
        conditional_candidate_validation,
        output / "conditional_candidate_validation.json",
    )

    conditional_contract_prediction = validate_conditional_contract_prediction(
        case=case,
        conditional_block_spec_map=conditional_block_spec_map,
        records=records,
        system_spec=system_spec,
    )
    write_json(
        conditional_contract_prediction,
        output / "conditional_contract_prediction.json",
    )

    graph_artifact = build_v15_graph_artifact(
        case=case,
        records=records,
        sample_set_sha256=sample_set_sha256,
        system_boundary_map=system_boundary_map,
        boundary_block_contract=boundary_block_contract,
        conditional_block_spec_map=conditional_block_spec_map,
        conditional_candidate_validation=conditional_candidate_validation,
        conditional_contract_prediction=conditional_contract_prediction,
        capability_region=capability_region,
        system_feasible_region=system_feasible_region,
        selection_decision=selection_decision,
        replay_evidence=replay_evidence,
    )
    graph_audit = audit_v15_graph(
        graph_artifact,
        records=records,
        sample_set_sha256=sample_set_sha256,
        system_boundary_map=system_boundary_map,
        boundary_block_contract=boundary_block_contract,
        conditional_block_spec_map=conditional_block_spec_map,
        conditional_candidate_validation=conditional_candidate_validation,
        conditional_contract_prediction=conditional_contract_prediction,
        capability_region=capability_region,
        system_feasible_region=system_feasible_region,
        selection_decision=selection_decision,
        replay_evidence=replay_evidence,
    )
    if not graph_audit["passed"]:
        raise ValueError(f"V1.5 Graph audit failed: {graph_audit}")
    write_json(graph_artifact, output / "vco_pll_graph_v2.json")
    write_json(graph_audit, output / "graph_audit.json")
    write_json(factor_view(graph_artifact), output / "graph_factor_view.json")

    active_checks = [
        str(item["check"])
        for item in case["system_constraints"]["active_for_region"]
    ]
    exclusive_counts = _exclusive_failure_counts(records, active_checks)
    classification_counts = {
        "total": len(records),
        "block_feasible": sum(
            bool(record["status"]["block_feasible"]) for record in records
        ),
        "block_infeasible": sum(
            not bool(record["status"]["block_feasible"]) for record in records
        ),
        "system_constraints_passed": sum(
            bool(record["status"]["system_constraints_passed"])
            for record in records
        ),
        "context_covered": sum(
            bool(record["status"]["context_covered"]) for record in records
        ),
        "jointly_feasible": sum(
            bool(record["status"]["jointly_feasible"]) for record in records
        ),
    }
    summary: Dict[str, Any] = {
        "schema_version": "v1.5-multidim-evaluation-summary-1.0",
        "case_id": str(case["case_id"]),
        "deterministic": True,
        "random_seed": None,
        "model": "averaged_integer_n_cppll_v1 + synthetic_behavioral_vco_v1",
        "classification_counts": classification_counts,
        "exclusive_active_constraint_failure_counts": exclusive_counts,
        "active_constraints_effective": all(
            count > 0 for count in exclusive_counts.values()
        ),
        "sample_set_sha256": sample_set_sha256,
        "system_boundary_summary": {
            "status": system_boundary_map["status"],
            "block_spec_mapping_status": system_boundary_map[
                "block_spec_mapping_status"
            ],
            "slice_count": system_boundary_map["slice_count"],
            "mapped_boundary_count": system_boundary_map[
                "mapped_boundary_count"
            ],
            "unmapped_slice_count": system_boundary_map[
                "unmapped_slice_count"
            ],
            "boundary_map_sha256": system_boundary_map[
                "boundary_map_sha256"
            ],
        },
        "boundary_contract_summary": {
            "status": boundary_block_contract["status"],
            "workflow_outcome": boundary_block_contract["workflow_outcome"],
            "block_spec_mapping_status": boundary_block_contract[
                "block_spec_mapping_status"
            ],
            "entry_count": boundary_block_contract["entry_count"],
            "unmapped_slice_count": boundary_block_contract["validation"][
                "unmapped_slice_count"
            ],
            "validation_passed": boundary_block_contract["validation"][
                "passed"
            ],
            "hidden_parameters_invariant": boundary_block_contract[
                "validation"
            ]["checks"]["all_hidden_parameters_invariant"],
            "all_contexts_frozen_and_covered": boundary_block_contract[
                "validation"
            ]["checks"]["all_contexts_frozen_and_covered"],
            "interpolation_allowed": boundary_block_contract[
                "interpolation_allowed"
            ],
            "contract_sha256": boundary_block_contract["contract_sha256"],
        },
        "conditional_allocation_summary": {
            "status": conditional_block_spec_map["status"],
            "workflow_outcome": conditional_candidate_validation[
                "workflow_outcome"
            ],
            "block_spec_mapping_status": conditional_candidate_validation[
                "block_spec_mapping_status"
            ],
            "allocated_entry_count": conditional_block_spec_map[
                "entry_count"
            ],
            "unallocated_slice_count": conditional_block_spec_map[
                "validation"
            ]["unallocated_slice_count"],
            "engineering_margin_db": conditional_block_spec_map[
                "engineering_margin"
            ]["value_db"],
            "interpolation_allowed": conditional_block_spec_map[
                "interpolation_allowed"
            ],
            "allocation_validation_passed": conditional_block_spec_map[
                "validation"
            ]["passed"],
            "candidate_validation_passed": conditional_candidate_validation[
                "validation"
            ]["passed"],
            "validated_condition_count": conditional_candidate_validation[
                "validation"
            ]["validated_condition_count"],
            "block_spec_map_sha256": conditional_block_spec_map[
                "block_spec_map_sha256"
            ],
            "candidate_validation_sha256": conditional_candidate_validation[
                "validation_sha256"
            ],
            "contract_prediction_passed": conditional_contract_prediction[
                "validation"
            ]["passed"],
            "contract_prediction_candidate_count": conditional_contract_prediction[
                "validation"
            ]["candidate_count"],
            "contract_prediction_certified_count": conditional_contract_prediction[
                "validation"
            ]["certified_candidate_count"],
            "contract_prediction_false_positive_count": conditional_contract_prediction[
                "validation"
            ]["false_positive_count"],
            "contract_prediction_uncertified_system_pass_count": conditional_contract_prediction[
                "validation"
            ]["uncertified_systemtb_pass_count"],
            "contract_prediction_sha256": conditional_contract_prediction[
                "prediction_sha256"
            ],
        },
        "region_summary": {
            "capability_member_count": capability_region["member_count"],
            "system_feasible_member_count": system_feasible_region[
                "member_count"
            ],
            "capability_boundary_transition_count": len(
                capability_region["boundary_transitions"]
            ),
            "system_boundary_transition_count": len(
                system_feasible_region["boundary_transitions"]
            ),
            "capability_region_sha256": capability_region["region_sha256"],
            "system_feasible_region_sha256": system_feasible_region[
                "region_sha256"
            ],
        },
        "selection_summary": {
            "selected_point_id": selected_point_id,
            "selected_candidate_id": selection_decision["selected_candidate"][
                "candidate_id"
            ],
            "selected_design_vector": selection_decision[
                "selected_candidate"
            ]["design_vector"],
            "engineering_cost": selection_decision["selected_candidate"][
                "engineering_cost"
            ],
            "minimum_normalized_active_margin": selection_decision[
                "selected_candidate"
            ]["minimum_normalized_active_margin"],
            "interior_candidate_count": selection_decision["eligible_counts"][
                "interior_jointly_feasible"
            ],
            "selection_sha256": selection_decision["selection_sha256"],
            "replay_sha256": replay_evidence["replay_sha256"],
            "replay_identical": replay_evidence[
                "identical_to_sampled_evaluation"
            ],
            "replay_jointly_feasible": replay_evidence[
                "replay_jointly_feasible"
            ],
            "pareto_claimed": False,
        },
        "selection_performed": True,
        "regions_generated": True,
        "graph_summary": {
            "audit_passed": graph_audit["passed"],
            "node_count": graph_audit["counts"]["nodes"],
            "edge_count": graph_audit["counts"]["edges"],
            "sampled_candidate_count": graph_audit["counts"][
                "sampled_candidates"
            ],
            "audit_schema_version": graph_audit["schema_version"],
        },
        "graph_compiled": True,
        "claim_boundary": case.get("claim_boundary"),
        "artifacts": {
            "design_space": "design_space.json",
            "sampled_points_jsonl": "sampled_points.jsonl",
            "sampled_points_csv": "sampled_points.csv",
            "system_boundary_map": "system_boundary_map.json",
            "boundary_block_contract_json": "boundary_block_contract.json",
            "boundary_block_contract_csv": "boundary_block_contract.csv",
            "conditional_block_spec_map_json": "conditional_block_spec_map.json",
            "conditional_block_spec_map_csv": "conditional_block_spec_map.csv",
            "conditional_candidate_validation": "conditional_candidate_validation.json",
            "conditional_contract_prediction": "conditional_contract_prediction.json",
            "capability_region": "capability_region.json",
            "system_feasible_region": "system_feasible_region.json",
            "selection_decision": "selection_decision.json",
            "selected_candidate_replay": "selected_candidate_replay.json",
            "typed_graph_v2": "vco_pll_graph_v2.json",
            "graph_audit": "graph_audit.json",
            "graph_factor_view": "graph_factor_view.json",
        },
    }
    write_json(summary, output / "evaluation_summary.json")
    _write_summary_markdown(output / "summary.md", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default=str(DEFAULT_CASE))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    summary = run(args.case, args.output_dir)
    counts = summary["classification_counts"]
    print("Case:", summary["case_id"])
    print("Sampled points:", counts["total"])
    print("Block feasible:", counts["block_feasible"])
    print("SystemTB PASS:", counts["system_constraints_passed"])
    print("Jointly feasible:", counts["jointly_feasible"])
    print("Capability Region members:", summary["region_summary"]["capability_member_count"])
    print("System-feasible Region members:", summary["region_summary"]["system_feasible_member_count"])
    print("Refined system boundaries:", summary["system_boundary_summary"]["mapped_boundary_count"])
    print("Extracted boundary Block contracts:", summary["boundary_contract_summary"]["entry_count"])
    print("Boundary contract validation PASS:", summary["boundary_contract_summary"]["validation_passed"])
    print("Conditional BlockSpec entries:", summary["conditional_allocation_summary"]["allocated_entry_count"])
    print("Validated BlockSpec slices:", summary["conditional_allocation_summary"]["validated_condition_count"])
    print("BlockSpec mapping status:", summary["conditional_allocation_summary"]["block_spec_mapping_status"])
    print("Selected point:", summary["selection_summary"]["selected_point_id"])
    print("Selected DesignVector:", summary["selection_summary"]["selected_design_vector"])
    print("Independent replay identical:", summary["selection_summary"]["replay_identical"])
    print("Graph audit PASS:", summary["graph_summary"]["audit_passed"])
    print("Active constraints effective:", summary["active_constraints_effective"])
    print("Sample-set SHA-256:", summary["sample_set_sha256"])
    print("Artifacts:", Path(args.output_dir).resolve())


if __name__ == "__main__":
    main()
