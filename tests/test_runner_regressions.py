"""End-to-end scientific artifact regression tests for V1.0 and V1.5."""

from pathlib import Path

import pytest

from run_jitter_pn_roundtrip_demo import run as run_roundtrip
from run_v1_5_allocate import run as run_v15_allocate
from run_v1_5_continuity import run as run_v15_continuity
from run_v1_5_formal_joint_blockspec import run as run_v15_formal
from run_v1_5_joint_boundary_validation import run as run_v15_boundary
from run_v1_5_joint_contract import run as run_v15_joint
from run_v1_5_kvco_mapping import run as run_v15_mapping
from run_v1_prove import run as run_v10
from v1.io import file_sha256, read_json


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def completed_runs(tmp_path_factory):
    output = tmp_path_factory.mktemp("runner-regression")
    paths = {
        name: output / name
        for name in (
            "roundtrip",
            "v10",
            "allocate",
            "continuity",
            "mapping",
            "joint",
            "boundary",
            "formal",
        )
    }
    roundtrip = run_roundtrip(output_dir=paths["roundtrip"])
    v10 = run_v10(ROOT / "v1/cases/vco_mapping_01.json", paths["v10"])
    run_v15_allocate(output_dir=paths["allocate"])
    run_v15_continuity(
        source_dir=paths["allocate"], output_dir=paths["continuity"]
    )
    run_v15_mapping(source_dir=paths["continuity"], output_dir=paths["mapping"])
    run_v15_joint(source_dir=paths["mapping"], output_dir=paths["joint"])
    run_v15_boundary(source_dir=paths["mapping"], output_dir=paths["boundary"])
    run_v15_formal(
        source_dir=paths["mapping"],
        holdout_dir=paths["boundary"],
        output_dir=paths["formal"],
    )
    return {"paths": paths, "roundtrip": roundtrip, "v10": v10}


def test_v10_roundtrip_and_prove_regression(completed_runs):
    roundtrip = completed_runs["roundtrip"]
    v10 = completed_runs["v10"]

    assert roundtrip["passed"] is True
    assert roundtrip["allocation"]["allocated"] is True
    assert roundtrip["selection"]["selected_candidate_id"] == "candidate_low_noise"
    assert v10["initial_passed"] is False
    assert v10["search_knob_boundary"] == pytest.approx(-116.358121, abs=1e-6)
    assert v10["block_metric_at_boundary"] == pytest.approx(-113.511151, abs=1e-6)
    assert v10["selected_candidate"] == "candidate_low_noise"
    assert v10["final_passed"] is True
    assert v10["simulator_calls"] == 46


def test_v15_scientific_counts_and_statuses(completed_runs):
    paths = completed_runs["paths"]
    summary = read_json(paths["allocate"] / "evaluation_summary.json")
    counts = summary["classification_counts"]
    assert counts == {
        "block_feasible": 221,
        "block_infeasible": 13,
        "context_covered": 234,
        "jointly_feasible": 51,
        "system_constraints_passed": 51,
        "total": 234,
    }
    assert summary["selection_summary"]["selected_point_id"] == (
        "v15p-ee61a397f9c43184"
    )
    assert summary["graph_summary"]["audit_passed"] is True

    continuity = read_json(
        paths["continuity"] / "continuity_validation_summary.json"
    )
    assert continuity["boundary_prediction"]["holdout_count"] == 8
    assert continuity["boundary_prediction"]["pn_spec_mae_db"] == pytest.approx(
        0.0006121993064880371
    )
    assert continuity["candidate_replay"]["inside_contract_false_positive_count"] == 0

    formal = read_json(paths["formal"] / "formal_2d_blockspec.json")
    assert formal["status"] == "formal_2d_blockspec_allocated_and_validated"
    window = formal["required_measured_kvco_window"]
    assert {name: window[name] for name in (
        "lower_ghz_per_v", "lower_hz_per_v", "upper_ghz_per_v", "upper_hz_per_v"
    )} == {
        "lower_ghz_per_v": 1.54,
        "lower_hz_per_v": 1540000000.0,
        "upper_ghz_per_v": 1.84,
        "upper_hz_per_v": 1840000000.0,
    }


def test_v15_artifact_bytes_are_frozen(completed_runs):
    paths = completed_runs["paths"]
    expected = {
        "allocate/sampled_points.jsonl": "7e22650579d15d4de416800c9e2c63e2ed9da78b5e0b1c2e6d389702bb472623",
        "allocate/evaluation_summary.json": "9287a6ccdd1324490a0d7097b9e7fb42ef2fa5428ab03e55a3c9effc6dcc6a23",
        "continuity/frozen_conditional_contracts.json": "6784d9dd582da7c9397f2ebffe40e28d29184d15bc243e8444edf44dc5cd43ce",
        "continuity/continuity_validation_summary.json": "602ba5fba975734aa9df74b7d1c174ef17fb56254b439f4a41269b2287525bce",
        "mapping/measured_kvco_mapping.json": "2c9b8ffe34383966dd26f8edf4ebe516151e25833e88692306f1bbcd309fcd9d",
        "mapping/joint_contract_axis_decision.json": "1d1fe5dbea7cf7a8fbd063b57746835a4f31087a30c291bbbe012c9971f366cf",
        "mapping/measured_kvco_report.json": "14b6b5346070e58124f4c6a01f46d196c8049fca5c4d317321fb22f0cba1724e",
        "joint/provisional_joint_contract.json": "8ed49a9ae3757073ac47d4c70621b8537bd0dcc7c328af82047d63a36de7b5da",
        "joint/joint_contract_summary.json": "cc1772a1350d663af80038829e54780c6d4cd9a0a24b67c169a84a3fc591b93e",
        "boundary/joint_boundary_validation.json": "497e8c12b4e3a2b1df78673c5033ce6ef6aa046c81a054d7d52c219a1e555d37",
        "formal/formal_2d_blockspec.json": "44a2d14e68ae5f7512efa844d0c74e061304b63b4da159e80049f96ddc30d580",
    }
    for relative, digest in expected.items():
        stage, filename = relative.split("/", 1)
        assert file_sha256(paths[stage] / filename) == digest
