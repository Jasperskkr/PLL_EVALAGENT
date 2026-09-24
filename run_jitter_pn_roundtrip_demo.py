"""Modular reference flow: jitter -> VCO PN -> verified system jitter."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from v1.api.workflow import SpecClosureRequest
from v1.model.pll_behavioral import VCOParams
from v1.model.instances import build_vco_instance
from v1.io import write_json
from v1.specs import SystemSpec, load_case
from v1.workflow import (
    GraphEvidenceFinalizer,
    MinimumCostPassingSelector,
    StaticBlockDefinitionProvider,
    StaticCandidateProvider,
    WorkflowModules,
    run_spec_closure,
)
from v1.workflow.vco import (
    VCOAllocationModule,
    VCOAssignmentVerifier,
    VCOBaselineEvaluator,
    VCOCandidateRealizer,
    VCOContextBuilder,
)


ROOT = Path(__file__).resolve().parent
DEFAULT_CASE = ROOT / "v1" / "cases" / "jitter_pn_roundtrip_01.json"
DEFAULT_OUTPUT = ROOT / "results" / "jitter_pn_roundtrip_demo"


def build_request(case: dict[str, Any]) -> SpecClosureRequest:
    """Compile a JSON case into the block-agnostic workflow request."""

    return SpecClosureRequest(
        workflow_id=f"{case['case_id']}:spec-closure",
        system_spec=SystemSpec.from_dict(case["system_spec"]),
        base_instance=build_vco_instance(
            VCOParams(), case.get("base_instance", {})
        ),
        block_definition=dict(case["block_definition"]),
        allocation_problem=dict(case["allocation_problem"]),
        candidate_proposals=tuple(case["candidate_proposals"]),
        declared_operating_context=dict(
            case.get("declared_operating_context", {})
        ),
        policy=dict(case.get("workflow_policy", {})),
    )


def build_modules() -> WorkflowModules:
    """Bind the generic workflow to the current synthetic VCO adapters."""

    return WorkflowModules(
        block_definition_provider=StaticBlockDefinitionProvider(),
        baseline_evaluator=VCOBaselineEvaluator(),
        context_builder=VCOContextBuilder(),
        allocator=VCOAllocationModule(),
        candidate_provider=StaticCandidateProvider(),
        candidate_realizer=VCOCandidateRealizer(),
        verifier=VCOAssignmentVerifier(),
        selector=MinimumCostPassingSelector(),
        evidence_finalizer=GraphEvidenceFinalizer(),
    )


def run(
    case_path: str | Path = DEFAULT_CASE,
    output_dir: str | Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    case = load_case(case_path)
    report = run_spec_closure(build_request(case), build_modules())
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    write_json(report, output / "spec_closure_report.json")
    write_json(report["allocation"], output / "allocation_report.json")
    write_json(report["evidence"]["graph"], output / "workflow_graph_v2.json")
    write_json(report["evidence"]["audit"], output / "workflow_graph_audit.json")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default=str(DEFAULT_CASE))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    report = run(args.case, args.output_dir)
    selected_id = report["selection"]["selected_candidate_id"]
    selected = next(
        item
        for item in report["candidate_evaluations"]
        if item["candidate_id"] == selected_id
    )
    verification = selected["verification"]
    print(
        "Initial jitter (fs):",
        f"{report['baseline']['metrics']['integrated_jitter_s'] * 1e15:.3f}",
    )
    print("Forward allocation:", report["allocation"]["status"])
    print(
        "Required VCO PN (dBc/Hz):",
        f"{report['allocation']['allocated_block_spec']['phase_noise_1mhz_max_dbc_hz']:.6f}",
    )
    print(
        "Final jitter (fs):",
        f"{verification['system_tb']['metrics']['integrated_jitter_s'] * 1e15:.3f}",
    )
    print("Selected candidate:", selected_id)
    print("BlockTB PASS:", verification["block_tb"]["passed"])
    print("SystemTB PASS:", verification["system_tb"]["passed"])
    print("Graph audit PASS:", report["evidence"]["audit"]["passed"])
    print("Spec closure PASS:", report["passed"])
    print("Report:", (Path(args.output_dir) / "spec_closure_report.json").resolve())


if __name__ == "__main__":
    main()
