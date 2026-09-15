from __future__ import annotations

import unittest
from pathlib import Path
import tempfile

from v1.model.pll_behavioral import VCOParams
from v1.pipeline import (
    build_vco_instance,
    characterize_vco,
    evaluate_system,
    run_sensitivity_suite,
    search_required_pn_boundary,
)
from v1.contract import build_contract_evidence
from run_v1_prove import run
from v1.agent_actions import validate_agent_action
from v1.allocation.evaluator import evaluate_spec_vector
from v1.allocation.spec_vector import SpecVector
from v1.graph.compiler import build_v1_graph_artifact
from v1.schema.envelopes import make_envelope
from v1.schema.validators import validate_envelope, validate_system_spec_payload
from v1.specs import SystemSpec, VCORequirement, load_case


ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = ROOT / "v1" / "cases" / "vco_mapping_01.json"
CASE = load_case(CASE_PATH)
SYSTEM_SPEC = SystemSpec.from_dict(CASE["system_spec"])
BASE_VCO = build_vco_instance(VCOParams(), CASE.get("base_vco", {}))


class V1PipelineTests(unittest.TestCase):
    def test_baseline_is_deterministic_and_intentionally_fails_jitter(self) -> None:
        first = evaluate_system(SYSTEM_SPEC, BASE_VCO, keep_raw=False)
        second = evaluate_system(SYSTEM_SPEC, BASE_VCO, keep_raw=False)
        self.assertEqual(first, second)
        self.assertFalse(first["passed"])
        self.assertGreater(first["residuals"]["integrated_jitter_residual_s_max"], 0.0)
        self.assertLess(first["residuals"]["lock_time_residual_s_max"], 0.0)

    def test_phase_noise_sweep_is_monotonic_for_jitter(self) -> None:
        sweep = run_sensitivity_suite(
            SYSTEM_SPEC,
            BASE_VCO,
            {"pn_1mhz_dbc_hz": [-120.0, -118.0, -116.0, -114.0]},
        )["sweeps"]["pn_1mhz_dbc_hz"]["rows"]
        jitter = [row["integrated_jitter_s"] for row in sweep]
        self.assertEqual(jitter, sorted(jitter))
        self.assertLess(jitter[0], jitter[-1])

    def test_required_boundary_has_pass_fail_bracket(self) -> None:
        boundary = search_required_pn_boundary(
            SYSTEM_SPEC,
            BASE_VCO,
            -110.0,
            -125.0,
            iterations=20,
        )
        self.assertLess(boundary["required_boundary"], -116.0)
        self.assertGreater(boundary["required_boundary"], -117.0)
        self.assertAlmostEqual(boundary["bracket_width"], 15.0 / (2.0 ** 20), places=7)

    def test_low_noise_candidate_passes_context_validation(self) -> None:
        candidate = build_vco_instance(
            BASE_VCO, {"pn_1mhz_dbc_hz": -122.0}
        )
        evaluation = evaluate_system(SYSTEM_SPEC, candidate, keep_raw=False)
        self.assertTrue(evaluation["passed"])
        requirement = VCORequirement(
            phase_noise_1mhz_max_dbc_hz=-117.858121,
            power_max_w=8.0e-3,
            margin_db=1.5,
        )
        from v1.pipeline import validate_vco_spec

        block = validate_vco_spec(
            SYSTEM_SPEC, requirement, candidate, evaluation["context"]
        )
        self.assertTrue(block["passed"])

    def test_contract_refinement_reduces_holdout_error(self) -> None:
        observations = characterize_vco(
            BASE_VCO,
            [0.1, 0.3, 0.5, 0.7, 0.9, 1.1],
            [25.0],
            [1.0e6],
        )
        validation = build_contract_evidence(BASE_VCO, observations)["validation"]
        self.assertGreater(validation["v0_mae_db"], 1.0)
        self.assertLess(validation["v1_mae_db"], 1.0e-12)

    def test_full_runner_completes_the_outer_loop(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = run(CASE_PATH, Path(directory) / "run")
            self.assertFalse(result["initial_passed"])
            self.assertEqual(result["selected_candidate"], "candidate_low_noise")
            self.assertTrue(result["final_passed"])
            output = Path(result["output_dir"])
            for name in (
                "required_vco_spec_boundary.json",
                "recommended_vco_spec.json",
                "block_feasibility.json",
                "final_system_evaluation.json",
                "trajectory.jsonl",
                "summary.md",
            ):
                self.assertTrue((output / name).exists(), name)

    def test_additive_schema_envelope_is_valid_and_deterministic(self) -> None:
        payload = SYSTEM_SPEC.to_dict()
        validate_system_spec_payload(payload)
        first = make_envelope("system_spec", "case:system", payload, run_id="case")
        second = make_envelope("system_spec", "case:system", payload, run_id="case")
        validate_envelope(first)
        self.assertEqual(first, second)

    def test_spec_vector_reuses_existing_systemtb(self) -> None:
        from v1.pipeline import abstract_pn_evaluation

        vector = SpecVector(
            values={"phase_noise_1mhz_max_dbc_hz": -120.0},
            source="test",
        )
        generic = evaluate_spec_vector(SYSTEM_SPEC, BASE_VCO, vector)
        legacy = abstract_pn_evaluation(SYSTEM_SPEC, BASE_VCO, -120.0)
        self.assertEqual(
            generic["system_evaluation"]["metrics"],
            legacy["system_evaluation"]["metrics"],
        )
        self.assertEqual(
            generic["system_evaluation"]["passed"],
            legacy["system_evaluation"]["passed"],
        )

    def test_graph_compiler_records_validated_influence_edges(self) -> None:
        observations = characterize_vco(BASE_VCO, [0.1, 0.5, 0.9], [25.0], [1.0e6])
        evidence = build_contract_evidence(BASE_VCO, observations)
        sensitivity = run_sensitivity_suite(
            SYSTEM_SPEC,
            BASE_VCO,
            {"pn_1mhz_dbc_hz": [-120.0, -118.0, -116.0, -114.0, -112.0]},
        )
        graph = build_v1_graph_artifact(
            contract=evidence["contract_v1"],
            sensitivity=sensitivity,
            system_spec=SYSTEM_SPEC.to_dict(),
            run_id="test",
        )
        edge_types = {edge["type"] for edge in graph["edges"]}
        self.assertIn("noise_transfer", edge_types)
        self.assertIn("sensitivity_evidence", edge_types)
        self.assertIn("contract_dependency", edge_types)

    def test_agent_actions_are_constrained(self) -> None:
        validate_agent_action(
            {
                "action": "add_dependency",
                "target": "VCO.phase_noise",
                "evidence_ids": ["sweep_001"],
            }
        )
        with self.assertRaises(ValueError):
            validate_agent_action(
                {
                    "action": "tighten_spec",
                    "target": "SystemSpec.integrated_jitter",
                    "evidence_ids": ["eval_001"],
                    "modify_system_spec": True,
                }
            )


if __name__ == "__main__":
    unittest.main()
