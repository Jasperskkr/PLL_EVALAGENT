from __future__ import annotations

import copy
import json
import unittest
from dataclasses import replace
from pathlib import Path
import tempfile

from v1.model.pll_behavioral import VCOParams
from v1.pipeline import (
    build_vco_instance,
    characterize_vco,
    evaluate_system,
    run_sensitivity_suite,
    search_required_pn_boundary,
    measure_vco_behavior,
)
from v1.contract import build_contract_evidence
from run_v1_prove import run
from run_v1_spec_matrix import run_matrix
from run_v1_mapping_suite import run_suite as run_mapping_suite
from v1.agent_actions import validate_agent_action
from v1.allocation.evaluator import evaluate_design_vector
from v1.allocation.design_vector import DesignVector
from v1.graph.compiler import build_v1_graph_artifact
from v1.graph.compiler import build_v1_graph_v2_artifact
from v1.graph.validators import validate_graph_v2_artifact
from v1.graph.model import EDGE_TYPES, NODE_TYPES
from v1.graph.planes import EDGE_PLANE_RULES
from v1.graph.audit import audit_allocation_graph, build_agent_goal_context
from v1.graph.proposals import validate_graph_proposal
from v1.graph.queries import (
    all_plane_views,
    evidence_neighborhood,
    plane_view,
    requirement_allocation_paths,
)
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
            {"pn_anchor_1mhz_dbc_hz": [-120.0, -118.0, -116.0, -114.0]},
        )["sweeps"]["pn_anchor_1mhz_dbc_hz"]["rows"]
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
        self.assertEqual(boundary["search_knob"], "pn_anchor_1mhz_dbc_hz")
        self.assertLess(boundary["search_knob_boundary"], -116.0)
        self.assertGreater(boundary["search_knob_boundary"], -117.0)
        self.assertAlmostEqual(boundary["bracket_width"], 15.0 / (2.0 ** 20), places=7)

    def test_low_noise_candidate_passes_context_validation(self) -> None:
        candidate = build_vco_instance(
            BASE_VCO, {"pn_anchor_1mhz_dbc_hz": -122.0}
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

    def test_design_vector_rejects_requirement_names(self) -> None:
        from v1.pipeline import abstract_pn_evaluation

        vector = DesignVector(
            values={"phase_noise_1mhz_max_dbc_hz": -120.0},
            source="test",
        )
        with self.assertRaises(ValueError):
            evaluate_design_vector(SYSTEM_SPEC, BASE_VCO, vector)

        vector = DesignVector(
            values={"pn_anchor_1mhz_dbc_hz": -120.0},
            source="test",
        )
        generic = evaluate_design_vector(SYSTEM_SPEC, BASE_VCO, vector)
        legacy = abstract_pn_evaluation(SYSTEM_SPEC, BASE_VCO, -120.0)
        self.assertEqual(generic["design_vector"]["object_type"], "vco_design_vector")
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
            {"pn_anchor_1mhz_dbc_hz": [-120.0, -118.0, -116.0, -114.0, -112.0]},
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
                "architecture",
                "behavior",
                "influence",
                "evidence",
            },
        )
        self.assertEqual(
            {port["name"] for port in block["architecture"]["ports"]},
            {"Vctrl", "oscillation_frequency"},
        )
        self.assertIn("metrics", block["behavior"])
        self.assertTrue(block["influence"])
        self.assertIn("measurement_contracts", block["evidence"])

    def test_graph_v2_has_allocation_and_validation_path(self) -> None:
        observations = characterize_vco(BASE_VCO, [0.1, 0.5, 0.9], [25.0], [1.0e6])
        contract = build_contract_evidence(BASE_VCO, observations)
        sensitivity = run_sensitivity_suite(
            SYSTEM_SPEC,
            BASE_VCO,
            {"pn_anchor_1mhz_dbc_hz": [-120.0, -118.0, -116.0]},
        )
        boundary = search_required_pn_boundary(
            SYSTEM_SPEC, BASE_VCO, -110.0, -125.0, iterations=4
        )
        context_contract = {
            "context_id": "VCOBlockContext.v1",
            "vctrl_min_v": 0.2,
            "vctrl_max_v": 0.8,
            "temperature_points_c": [25.0],
            "vdd_v": 1.8,
        }
        boundary_measurement = measure_vco_behavior(
            SYSTEM_SPEC,
            build_vco_instance(
                BASE_VCO,
                {boundary["search_knob"]: boundary["search_knob_boundary"]},
            ),
            context_contract,
        )
        boundary = {
            **boundary,
            "block_metric_at_boundary": boundary_measurement["worst_case"][
                "worst_phase_noise_1mhz_dbc_hz"
            ],
        }
        graph = build_v1_graph_v2_artifact(
            contract=contract["contract_v1"],
            sensitivity=sensitivity,
            system_spec=SYSTEM_SPEC.to_dict(),
            run_id="test-v2",
            initial_evaluation=evaluate_system(SYSTEM_SPEC, BASE_VCO, keep_raw=False),
            boundary=boundary,
            recommended_requirement={
                "phase_noise_1mhz_max_dbc_hz": boundary["block_metric_at_boundary"] - 1.5,
                "margin_db": 1.5,
            },
            candidate_results=[
                {
                    "candidate_id": "candidate_test",
                    "engineering_cost": 1.0,
                    "description": "test candidate",
                    "block_tb": {
                        "passed": False,
                        "context": {
                            "context_id": "VCOBlockContext.v1",
                            "vctrl_min_v": 0.2,
                            "vctrl_max_v": 0.8,
                            "temperature_points_c": [25.0],
                            "vdd_v": 1.8,
                        },
                        "measurement_method": "context_sweep_behavioral_vco",
                        "provenance": {"source": "test"},
                    },
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
                "source": "VCO.phase_noise_1mhz",
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

    def test_systemspec_to_pn_matrix_is_monotonic_and_reversible(self) -> None:
        boundaries = []
        for jitter_fs in (140.0, 100.0, 80.0, 60.0, 50.0):
            spec = replace(
                SYSTEM_SPEC, integrated_jitter_max_s=jitter_fs * 1.0e-15
            )
            boundary = search_required_pn_boundary(
                spec, BASE_VCO, -110.0, -130.0, iterations=18
            )["search_knob_boundary"]
            boundaries.append(boundary)
            tighter = evaluate_system(
                spec,
                build_vco_instance(BASE_VCO, {"pn_anchor_1mhz_dbc_hz": boundary - 0.05}),
                keep_raw=False,
            )
            looser = evaluate_system(
                spec,
                build_vco_instance(BASE_VCO, {"pn_anchor_1mhz_dbc_hz": boundary + 0.05}),
                keep_raw=False,
            )
            self.assertTrue(tighter["passed"])
            self.assertFalse(looser["passed"])
        self.assertTrue(
            all(
                boundaries[index] > boundaries[index + 1]
                for index in range(len(boundaries) - 1)
            )
        )

    def test_non_pn_failures_reject_one_dimensional_allocation(self) -> None:
        for spec in (
            replace(SYSTEM_SPEC, lock_time_max_s=30.0e-6),
            replace(SYSTEM_SPEC, power_max_w=5.0e-3),
        ):
            tight = evaluate_system(
                spec,
                build_vco_instance(BASE_VCO, {"pn_anchor_1mhz_dbc_hz": -130.0}),
                keep_raw=False,
            )
            self.assertFalse(tight["passed"])
            with self.assertRaisesRegex(ValueError, "PN-only allocation infeasible"):
                search_required_pn_boundary(
                    spec, BASE_VCO, -110.0, -130.0, iterations=8
                )

    def test_full_spec_matrix_report_is_reproducible(self) -> None:
        matrix_path = ROOT / "v1" / "cases" / "vco_mapping_matrix.json"
        with tempfile.TemporaryDirectory() as directory:
            result = run_matrix(matrix_path, Path(directory) / "matrix")
            self.assertEqual(len(result["forward_allocation"]), 6)
            self.assertEqual(len(result["rejected_one_dimensional_cases"]), 2)
            self.assertTrue(all(result["assertions"].values()))
            rejected = result["rejected_one_dimensional_cases"]
            self.assertTrue(all(row["graph_audit_passed"] for row in rejected))
            self.assertIn("VCO.k1_hz_per_v", rejected[0]["agent_candidate_variables"])
            self.assertIn("VCO.nominal_power_w", rejected[1]["agent_candidate_variables"])

    def test_json_schema_vocabulary_matches_runtime_vocabulary(self) -> None:
        schema = json.loads(
            (ROOT / "v1" / "graph" / "graph_schema_v2.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            set(schema["$defs"]["node"]["properties"]["type"]["enum"]),
            set(NODE_TYPES),
        )
        self.assertEqual(
            set(schema["$defs"]["edge"]["properties"]["type"]["enum"]),
            set(EDGE_TYPES),
        )

    def test_graph_semantic_closure_audit_and_agent_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = run(CASE_PATH, Path(directory) / "run")
            output = Path(result["output_dir"])
            graph = json.loads((output / "vco_pll_graph_v2.json").read_text(encoding="utf-8"))
            audit = json.loads((output / "graph_audit.json").read_text(encoding="utf-8"))
            self.assertTrue(audit["passed"])
            self.assertTrue(all(audit["checks"].values()))
            goal = json.loads((output / "agent_goal_context.json").read_text(encoding="utf-8"))
            self.assertIn("integrated_jitter", goal["failed_checks"])
            self.assertTrue(any(item["variable"] == "VCO.pn_anchor_1mhz" for item in goal["candidate_variables"]))
            broken = copy.deepcopy(graph)
            for edge in broken["edges"]:
                if edge["type"] == "evaluates" and edge["target"] == "BlockTB.candidate_low_noise":
                    edge["status"] = "validated"
                    edge["properties"]["passed"] = False
                    break
            with self.assertRaises(ValueError):
                validate_graph_v2_artifact(broken)

            block_results = json.loads((output / "block_feasibility.json").read_text(encoding="utf-8"))
            selected = next(item for item in block_results if item.get("selected"))
            expected = {
                "selected_candidate": selected["candidate_id"],
                "search_knob_boundary": json.loads((output / "required_vco_spec_boundary.json").read_text(encoding="utf-8"))["search_knob_boundary"],
                "required_pn": json.loads((output / "required_vco_spec.json").read_text(encoding="utf-8"))["phase_noise_1mhz_max_dbc_hz"],
                "recommended_pn": json.loads((output / "recommended_vco_spec.json").read_text(encoding="utf-8"))["phase_noise_1mhz_max_dbc_hz"],
                "block_tb": selected["block_tb"],
                "candidate_system": selected["system_evaluation"],
                "final_system": json.loads((output / "final_system_evaluation.json").read_text(encoding="utf-8")),
                "final_context_coverage": json.loads((output / "final_context_coverage.json").read_text(encoding="utf-8")),
            }

            def assert_audit_rejects(mutated: dict) -> None:
                self.assertFalse(audit_allocation_graph(mutated, expected=expected)["passed"])

            wrong_final_instance = copy.deepcopy(graph)
            final_edge = next(edge for edge in wrong_final_instance["edges"] if edge["target"] == "Evidence.SystemTB.final" and edge["type"] == "evaluates")
            final_edge["source"] = "Instance.candidate_baseline"
            assert_audit_rejects(wrong_final_instance)

            wrong_worst_case = copy.deepcopy(graph)
            block_node = next(node for node in wrong_worst_case["nodes"] if node["id"] == f"BlockTB.{selected['candidate_id']}")
            block_node["properties"]["worst_case"]["worst_phase_noise_1mhz_dbc_hz"] += 1.0
            assert_audit_rejects(wrong_worst_case)

            uncovered_context = copy.deepcopy(graph)
            cover_edge = next(edge for edge in uncovered_context["edges"] if edge["source"] == "Context.VCO.contract" and edge["target"] == "Context.SystemTB.final")
            cover_edge["properties"]["passed"] = False
            cover_edge["status"] = "rejected"
            assert_audit_rejects(uncovered_context)

            missing_evidence = copy.deepcopy(graph)
            missing_evidence["nodes"] = [node for node in missing_evidence["nodes"] if node["id"] != "Evidence.sensitivity"]
            assert_audit_rejects(missing_evidence)

            false_result_validated = copy.deepcopy(graph)
            failing_edge = next(edge for edge in false_result_validated["edges"] if edge["type"] == "evaluates" and edge.get("properties", {}).get("passed") is False)
            failing_edge["status"] = "validated"
            assert_audit_rejects(false_result_validated)

            failed_in_capability = copy.deepcopy(graph)
            failed_in_capability["edges"].append({
                "source": "Candidate.candidate_baseline",
                "target": "VCO.capability_region",
                "type": "candidate_of",
                "status": "validated",
                "properties": {"candidate_id": "candidate_baseline"},
            })
            assert_audit_rejects(failed_in_capability)

    def test_semantic_freeze_validator_rejects_named_violations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = run(CASE_PATH, Path(directory) / "run")
            graph = json.loads(
                (Path(result["output_dir"]) / "vco_pll_graph_v2.json").read_text(
                    encoding="utf-8"
                )
            )

        def assert_validator_rejects(mutated: dict, pattern: str | None = None) -> None:
            with self.assertRaisesRegex(ValueError, pattern or "."):
                validate_graph_v2_artifact(mutated)

        def node_metadata() -> dict:
            return {
                "plane": "schema",
                "authority": "schema_compiler",
                "scope": "global",
                "mutability": "immutable",
                "provenance": {"source": "test"},
            }

        def edge_metadata(edge_type: str) -> dict:
            plane = EDGE_PLANE_RULES.get(edge_type, "realization")
            return {
                "plane": plane,
                "authority": "deterministic_graph_compiler",
                "scope": "run_specific",
                "mutability": "append_only",
                "provenance": {"source": "test", "edge_type": edge_type},
                "status": "validated",
                "properties": {},
            }

        architecture_metric_port = copy.deepcopy(graph)
        architecture_metric_port["nodes"].append({
            "id": "VCO.power_port",
            "type": "port",
            "semantic_role": "architecture",
            "properties": {"direction": "out", "unit": "W", "signal_type": "power"},
            **node_metadata(),
        })
        assert_validator_rejects(architecture_metric_port, "behavior metric")

        duplicate_kvco = copy.deepcopy(graph)
        duplicate_kvco["nodes"].append({
            "id": "VCO.Kvco",
            "type": "port",
            "semantic_role": "architecture",
            "properties": {"direction": "out", "unit": "Hz/V"},
            **node_metadata(),
        })
        assert_validator_rejects(duplicate_kvco, "duplicate VCO Kvco")

        knob_as_behavior = copy.deepcopy(graph)
        next(node for node in knob_as_behavior["nodes"] if node["id"] == "VCO.pn_anchor_1mhz")["semantic_role"] = "behavior"
        assert_validator_rejects(knob_as_behavior, "internal model knob")

        non_influence_relation = copy.deepcopy(graph)
        edge = next(
            edge
            for edge in non_influence_relation["edges"]
            if edge["source"] == "VCO.phase_noise_1mhz"
            and edge["target"] == "PLL.integrated_jitter"
            and edge["type"] == "system_influence"
        )
        edge["type"] = "shortcut"
        edge["provenance"]["edge_type"] = "shortcut"
        assert_validator_rejects(non_influence_relation, "Behavior-to-SystemMetric")

        missing_measured_metric = copy.deepcopy(graph)
        next(node for node in missing_measured_metric["nodes"] if node["id"] == "VCORequirement.required")["properties"].pop("measured_metric")
        assert_validator_rejects(missing_measured_metric, "measured metric")

        knob_judges_requirement = copy.deepcopy(graph)
        knob_node = next(node["id"] for node in knob_judges_requirement["nodes"] if node["id"].startswith("Knob.") and "pn_anchor" in node["id"])
        bad_edge = {
            "source": knob_node,
            "target": "VCORequirement.recommended",
            "type": "constrains",
            **edge_metadata("constrains"),
        }
        knob_judges_requirement["edges"].append(bad_edge)
        assert_validator_rejects(knob_judges_requirement, "candidate/knob")

        anchor_as_requirement = copy.deepcopy(graph)
        req_props = next(node for node in anchor_as_requirement["nodes"] if node["id"] == "VCORequirement.required")["properties"]
        req_props["value"] = req_props["search_knob_boundary"]
        assert_validator_rejects(anchor_as_requirement, "anchor boundary")

        unfrozen_blocktb = copy.deepcopy(graph)
        selected_blocktb = next(node for node in unfrozen_blocktb["nodes"] if node["id"] == "BlockTB.candidate_low_noise")
        selected_blocktb["properties"]["context"]["context_id"] = "candidate_local_context"
        assert_validator_rejects(unfrozen_blocktb, "frozen VCOBlockContext")

        evidence_without_method = copy.deepcopy(graph)
        next(node for node in evidence_without_method["nodes"] if node["id"] == "Evidence.sensitivity")["properties"].pop("measurement_method")
        assert_validator_rejects(evidence_without_method, "measurement method")

        unverified_capability = copy.deepcopy(graph)
        unverified_capability["edges"].append({
            "source": "Candidate.candidate_baseline",
            "target": "VCO.capability_region",
            "type": "candidate_of",
            **edge_metadata("candidate_of"),
        })
        unverified_capability["edges"][-1]["properties"] = {"candidate_id": "candidate_baseline"}
        assert_validator_rejects(unverified_capability, "passing BlockTB")

    def test_typed_planes_are_present_and_views_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = run(CASE_PATH, Path(directory) / "run")
            output = Path(result["output_dir"])
            graph = json.loads((output / "vco_pll_graph_v2.json").read_text(encoding="utf-8"))
            self.assertEqual(
                set(graph["metadata"]["planes"]),
                {"schema", "contract", "realization", "evidence"},
            )
            self.assertTrue(
                all(
                    all(field in node for field in ("plane", "authority", "scope", "mutability", "provenance"))
                    for node in graph["nodes"]
                )
            )
            self.assertTrue(
                all(
                    all(field in edge for field in ("plane", "authority", "scope", "mutability", "provenance"))
                    for edge in graph["edges"]
                )
            )
            views = all_plane_views(graph)
            saved_views = json.loads((output / "graph_plane_views.json").read_text(encoding="utf-8"))
            self.assertEqual(views, saved_views)
            self.assertEqual(set(views), {"schema", "contract", "realization", "evidence"})
            self.assertIn("Contract.VCO.v1", {node["id"] for node in views["contract"]["nodes"]})
            self.assertIn("Candidate.candidate_low_noise", {node["id"] for node in views["realization"]["nodes"]})
            self.assertIn("Evidence.SystemTB.final", {node["id"] for node in views["evidence"]["nodes"]})
            self.assertEqual(
                views["realization"]["nodes"],
                sorted(views["realization"]["nodes"], key=lambda item: item["id"]),
            )
            with self.assertRaises(ValueError):
                plane_view(graph, "not_a_plane")

    def test_typed_plane_governance_rejects_forged_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = run(CASE_PATH, Path(directory) / "run")
            graph = json.loads(
                (Path(result["output_dir"]) / "vco_pll_graph_v2.json").read_text(encoding="utf-8")
            )
            forged = copy.deepcopy(graph)
            instance = next(node for node in forged["nodes"] if node["id"] == "Instance.candidate_low_noise")
            instance["authority"] = "agent_or_allocator"
            with self.assertRaisesRegex(ValueError, "realized instance"):
                validate_graph_v2_artifact(forged)

            forged_evidence = copy.deepcopy(graph)
            evidence = next(node for node in forged_evidence["nodes"] if node["id"] == "Evidence.SystemTB.final")
            evidence["mutability"] = "versioned"
            with self.assertRaisesRegex(ValueError, "evidence-plane node"):
                validate_graph_v2_artifact(forged_evidence)

    def test_typed_plane_edge_semantics_are_enforced(self) -> None:
        """Evidence/allocation relations cannot be relabeled as structure."""

        with tempfile.TemporaryDirectory() as directory:
            result = run(CASE_PATH, Path(directory) / "run")
            graph = json.loads(
                (Path(result["output_dir"]) / "vco_pll_graph_v2.json").read_text(
                    encoding="utf-8"
                )
            )
            for edge in graph["edges"]:
                expected = EDGE_PLANE_RULES.get(edge["type"])
                if expected is not None:
                    self.assertEqual(edge["plane"], expected, edge)
                self.assertEqual(edge["authority"], "deterministic_graph_compiler")
                self.assertEqual(edge["mutability"], "append_only")

            forged_plane = copy.deepcopy(graph)
            sensitivity_edge = next(
                edge
                for edge in forged_plane["edges"]
                if edge["type"] == "sensitivity_evidence"
            )
            sensitivity_edge["plane"] = "schema"
            with self.assertRaisesRegex(ValueError, "expected evidence"):
                validate_graph_v2_artifact(forged_plane)

            forged_authority = copy.deepcopy(graph)
            forged_authority["edges"][0]["authority"] = "agent_or_allocator"
            with self.assertRaisesRegex(ValueError, "compiler-owned"):
                validate_graph_v2_artifact(forged_authority)

    def test_multi_type_scalar_mapping_suite_closes_block_and_system_loops(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = run_mapping_suite(CASE_PATH, Path(directory) / "mappings")
            self.assertTrue(all(result["assertions"].values()))
            self.assertEqual(
                {item["mapping_id"] for item in result["mappings"]},
                {
                    "jitter_to_pn",
                    "lock_time_to_kvco",
                    "power_to_nominal_power",
                    "frequency_to_f0",
                },
            )
            for item in result["mappings"]:
                self.assertTrue(item["claims"]["initial_target_failed"])
                self.assertTrue(item["claims"]["candidate_block_tb_passed"])
                self.assertTrue(item["claims"]["candidate_system_tb_passed"])
                self.assertTrue(item["claims"]["replay_identical"])
            by_id = {item["mapping_id"]: item for item in result["mappings"]}
            self.assertFalse(
                by_id["lock_time_to_kvco"]["claims"][
                    "global_single_boundary_over_probed_range"
                ]
            )
            self.assertFalse(
                by_id["frequency_to_f0"]["claims"][
                    "global_single_boundary_over_probed_range"
                ]
            )


if __name__ == "__main__":
    unittest.main()
