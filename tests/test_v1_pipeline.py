from __future__ import annotations

import copy
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
from v1.graph.compiler import build_v1_graph_v2_artifact
from v1.graph.validators import validate_graph_v2_artifact
from v1.graph.proposals import validate_graph_proposal
from v1.graph.queries import evidence_neighborhood, requirement_allocation_paths
from v1.schema.envelopes import make_envelope
from v1.schema.block_schema import build_vco_block_meta_v1, validate_block_meta
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
                "vco_block_meta_v1.json",
                "vco_pll_graph_v2.json",
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

    def test_block_meta_schema_has_four_contracts(self) -> None:
        observations = characterize_vco(BASE_VCO, [0.1, 0.5, 0.9], [25.0], [1.0e6])
        contract = build_contract_evidence(BASE_VCO, observations)["contract_v1"]
        block = build_vco_block_meta_v1(contract)
        validate_block_meta(block)
        self.assertEqual(
            set(block),
            {
                "schema_version",
                "object_type",
                "block_id",
                "block_type",
                "provenance",
                "interface_contract",
                "behavior_contract",
                "capability_contract",
                "verification_contract",
            },
        )
        self.assertIn("capability_region", block["capability_contract"])
        self.assertIn("measurement_contracts", block["verification_contract"])

    def test_graph_v2_has_allocation_and_validation_path(self) -> None:
        observations = characterize_vco(BASE_VCO, [0.1, 0.5, 0.9], [25.0], [1.0e6])
        contract = build_contract_evidence(BASE_VCO, observations)
        sensitivity = run_sensitivity_suite(
            SYSTEM_SPEC,
            BASE_VCO,
            {"pn_1mhz_dbc_hz": [-120.0, -118.0, -116.0]},
        )
        boundary = search_required_pn_boundary(
            SYSTEM_SPEC, BASE_VCO, -110.0, -125.0, iterations=4
        )
        graph = build_v1_graph_v2_artifact(
            contract=contract["contract_v1"],
            sensitivity=sensitivity,
            system_spec=SYSTEM_SPEC.to_dict(),
            run_id="test-v2",
            initial_evaluation=evaluate_system(SYSTEM_SPEC, BASE_VCO, keep_raw=False),
            boundary=boundary,
            recommended_requirement={
                "phase_noise_1mhz_max_dbc_hz": boundary["required_boundary"] - 1.5,
                "margin_db": 1.5,
            },
            candidate_results=[
                {
                    "candidate_id": "candidate_test",
                    "engineering_cost": 1.0,
                    "description": "test candidate",
                    "block_tb": {"passed": False, "context": {}},
                    "system_evaluation": {"passed": False, "metrics": {}},
                }
            ],
        )
        validate_graph_v2_artifact(graph)
        self.assertEqual(graph["graph_version"], "2.0")
        self.assertIn("operator.Noise_Integration", {node["id"] for node in graph["nodes"]})
        self.assertIn("allocates", {edge["type"] for edge in graph["edges"]})
        self.assertIn("validated_by", {edge["type"] for edge in graph["edges"]})
        self.assertIn("Schema.BlockMeta.VCO", {node["id"] for node in graph["nodes"]})

        broken = dict(graph)
        broken["nodes"] = [node for node in graph["nodes"] if node["id"] != "operator.Noise_Integration"]
        with self.assertRaises(ValueError):
            validate_graph_v2_artifact(broken)

        paths = requirement_allocation_paths(graph, "SystemSpec.integrated_jitter")
        self.assertTrue(paths)
        self.assertEqual(paths[0]["nodes"][-1], "VCORequirement.required")
        evidence = evidence_neighborhood(graph, "VCORequirement.required")
        self.assertTrue(evidence["incoming"] or evidence["outgoing"])

        bad_units = copy.deepcopy(graph)
        for node in bad_units["nodes"]:
            if node["id"] == "VCO.vctrl":
                node["properties"]["unit"] = "A"
        with self.assertRaises(ValueError):
            validate_graph_v2_artifact(bad_units)

    def test_agent_graph_proposal_is_non_authoritative(self) -> None:
        proposal = {
            "proposal_id": "proposal:cp-noise-edge:001",
            "action": "add_edge",
            "subject": {
                "source": "VCO.phase_noise_profile",
                "target": "operator.VCO_Noise_TF",
                "type": "input_to",
                "properties": {"hypothesis": "phase-noise input to loop transfer"},
            },
            "rationale": "Connect an exported VCO noise profile to the known transfer operator.",
            "evidence_ids": ["contract:vco:v1"],
            "requested_verification": ["schema_validation", "unit_check", "system_tb"],
            "status": "proposed",
        }
        validate_graph_proposal(proposal)
        invalid = dict(proposal)
        invalid["status"] = "validated"
        with self.assertRaises(ValueError):
            validate_graph_proposal(invalid)

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
