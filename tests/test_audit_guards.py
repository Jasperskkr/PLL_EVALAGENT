"""Regression guards for failure modes found during the architecture audit."""

from copy import deepcopy
from pathlib import Path

import pytest

from v1.allocation.design_vector import DesignVector
from v1.allocation.evaluator import evaluate_design_vector
from v1.allocation.service import allocate_system_spec
from v1.api.allocation import SpecAllocationRequest
from v1.api.verification import VerificationRequest
from v1.evaluation.system import evaluate_system
from v1.evaluation.vco import measure_vco_behavior
from v1.io import evidence_digest, write_evidence_json
from v1.model.pll_behavioral import CPPLLParams, VCOParams, simulate_cppll
from v1.specs import SystemSpec, VCORequirement, load_case
from v1.verification.constraints import evaluate_block_constraints
from v1.verification.service import verify_block_assignment


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def multidim_case():
    return load_case(ROOT / "v1/cases/vco_multidim_01.json")


def test_strict_evidence_json_rejects_non_finite_values(tmp_path):
    with pytest.raises(ValueError, match="Out of range float values"):
        evidence_digest({"invalid": float("nan")})
    with pytest.raises(ValueError, match="Out of range float values"):
        write_evidence_json({"invalid": float("inf")}, tmp_path / "invalid.json")


def test_constraint_references_fail_with_available_paths(multidim_case):
    constraints = deepcopy(multidim_case["block_constraints"])
    referenced = next(item for item in constraints if "limit_ref" in item)
    referenced["limit_ref"] = "system_spec.limits.power_typo_w"
    vector = {
        "worst_phase_noise_1mhz_dbc_hz": -120.0,
        "kvco_min_hz_per_v": 1.0e9,
        "kvco_max_hz_per_v": 2.0e9,
        "frequency_min_hz": 4.0e9,
        "frequency_max_hz": 6.0e9,
        "worst_power_w": 5.0e-3,
    }
    with pytest.raises(ValueError) as error:
        evaluate_block_constraints(
            {"system_spec": multidim_case["system_spec"]}, vector, constraints
        )
    message = str(error.value)
    assert "power_typo_w" in message
    assert "system_spec.limits.power_max_w" in message


def test_constraint_set_rejects_empty_duplicate_and_wrong_direction(multidim_case):
    vector = {
        "worst_phase_noise_1mhz_dbc_hz": -120.0,
        "kvco_min_hz_per_v": 1.0e9,
        "kvco_max_hz_per_v": 2.0e9,
        "frequency_min_hz": 4.0e9,
        "frequency_max_hz": 6.0e9,
        "worst_power_w": 5.0e-3,
    }
    references = {"system_spec": multidim_case["system_spec"]}
    with pytest.raises(ValueError, match="at least one"):
        evaluate_block_constraints(references, vector, [])
    duplicate = [
        {
            "constraint_id": "same",
            "kind": "lower_bound",
            "measured_metric": "kvco_min_hz_per_v",
            "operator": ">",
            "limit": 0.0,
        },
        {
            "constraint_id": "same",
            "kind": "upper_bound",
            "measured_metric": "worst_power_w",
            "operator": "<=",
            "limit": 1.0,
        },
    ]
    with pytest.raises(ValueError, match="unique"):
        evaluate_block_constraints(references, vector, duplicate)
    wrong_direction = [
        {
            "constraint_id": "wrong",
            "kind": "lower_bound",
            "measured_metric": "kvco_min_hz_per_v",
            "operator": "<=",
            "limit": 2.0e9,
        }
    ]
    with pytest.raises(ValueError, match="cannot use"):
        evaluate_block_constraints(references, vector, wrong_direction)


def test_unknown_backend_ids_fail_loudly(multidim_case):
    spec = SystemSpec.from_dict(multidim_case["system_spec"])
    allocation_request = SpecAllocationRequest(
        system_spec=spec,
        base_instance=VCOParams(),
        operating_context=multidim_case["block_context"],
        allocation_problem={},
        backend_id="typo-allocation-backend",
    )
    with pytest.raises(ValueError, match="unknown allocation backend_id"):
        allocate_system_spec(allocation_request)

    verification_request = VerificationRequest(
        spec,
        VCORequirement(-110.0),
        VCOParams(),
        multidim_case["block_context"],
        backend_id="typo-verification-backend",
    )
    with pytest.raises(ValueError, match="unknown verification backend_id"):
        verify_block_assignment(verification_request)


def test_context_semantics_are_explicit_and_legacy_aliases_match(multidim_case):
    spec = SystemSpec.from_dict(multidim_case["system_spec"])
    vco = VCOParams()
    system = evaluate_system(spec, vco, keep_raw=False)
    block = measure_vco_behavior(spec, vco, multidim_case["block_context"])

    assert system["trajectory_envelope"] == system["context"]
    assert system["trajectory_envelope"]["semantics"] == (
        "observed_simulation_trajectory_envelope"
    )
    assert "reached_lower_rail" in system["trajectory_envelope"]
    assert "settled_from" in system["trajectory_envelope"]
    assert block["characterization_window"] == block["context"]
    assert block["characterization_window"]["semantics"] == (
        "declared_block_characterization_window"
    )
    assert system["metrics"]["effective_noise_shaping_bandwidth_hz"] == (
        system["metrics"]["loop_bandwidth_hz"]
    )


def test_kvco_participates_in_the_feedback_plant():
    """Equal initial frequency with different Kvco must yield different dynamics."""

    pll = CPPLLParams(max_cycles=3000)
    lower_kvco = VCOParams(f0_hz=4.7e9, k1_hz_per_v=1.0e9, k2_hz_per_v2=0.0)
    higher_kvco = VCOParams(f0_hz=4.9e9, k1_hz_per_v=2.0e9, k2_hz_per_v2=0.0)
    lower = simulate_cppll(pll, lower_kvco)
    higher = simulate_cppll(pll, higher_kvco)

    assert lower["history"][0]["fosc_hz"] == higher["history"][0]["fosc_hz"]
    assert lower["history"][1]["relative_frequency_error"] != (
        higher["history"][1]["relative_frequency_error"]
    )
    assert lower["metrics"]["lock_time_s"] != higher["metrics"]["lock_time_s"]


def test_design_vector_evaluation_does_not_change_key_shape(multidim_case):
    spec = SystemSpec.from_dict(multidim_case["system_spec"])
    vector = DesignVector(
        values={"pn_anchor_1mhz_dbc_hz": -120.0},
        source="audit-test",
    )
    output = evaluate_design_vector(
        spec,
        VCOParams(),
        vector,
        block_context=multidim_case["block_context"],
        requirement=VCORequirement(-110.0),
    )
    assert "system_evaluation" in output
    assert "verification_system_tb" in output
    assert output["verification_system_tb"] == output["verification_report"]["system_tb"]
