"""Run the deterministic V1 SystemSpec-to-VCO-Spec proof and allocation demo.

The runner has no random state and no LLM dependency.  It deliberately keeps
the existing PLL model as the canonical simulator, then records every input,
sweep, boundary-search decision, BlockTB result, and final re-evaluation under
one output directory.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping
import json

from v1.model.pll_behavioral import VCOParams
from v1.contract import build_contract_evidence
from v1.agent_actions import ALLOWED_ACTIONS
from v1.allocation.design_vector import DesignVector
from v1.allocation.service import allocate_system_spec
from v1.api.allocation import SpecAllocationRequest
from v1.graph.compiler import build_v1_graph_artifact, build_v1_graph_v2_artifact
from v1.graph.audit import audit_allocation_graph, build_agent_goal_context
from v1.graph.queries import all_plane_views, factor_view
from v1.model.instances import build_vco_instance
from v1.evaluation.vco import characterize_vco
from v1.evaluation.system import evaluate_system, strip_raw_results
from v1.evaluation.sensitivity import run_sensitivity_suite
from v1.io import write_csv, write_json
from v1.schema.envelopes import make_envelope
from v1.schema.block_schema import build_vco_block_meta_v1, validate_block_meta
from v1.schema.validators import validate_envelope, validate_system_spec_payload
from v1.specs import CandidateDefinition, SystemSpec, VCORequirement, load_case
from v1.api.verification import VerificationRequest
from v1.verification.service import verify_block_assignment


DEFAULT_CASE = Path(__file__).parent / "v1" / "cases" / "vco_mapping_01.json"


def _candidate_map(case: Mapping[str, Any]) -> Dict[str, CandidateDefinition]:
    candidates = {
        item.candidate_id: item
        for item in (
            CandidateDefinition.from_dict(raw)
            for raw in case.get("candidates", [])
        )
    }
    if not candidates:
        candidates["base"] = CandidateDefinition(candidate_id="base")
    return candidates


def _baseline_context_contract(system_spec: SystemSpec, initial_context: Mapping[str, Any], guard_v: float) -> Dict[str, Any]:
    """Freeze a conservative VCO test envelope before evaluating candidates."""
    if guard_v < 0:
        raise ValueError("context guard must be nonnegative")
    return {
        "vctrl_min_v": max(system_spec.vctrl_min_v, float(initial_context["vctrl_min_v"]) - guard_v),
        "vctrl_max_v": min(system_spec.vctrl_max_v, float(initial_context["vctrl_max_v"]) + guard_v),
        "temperature_points_c": list(system_spec.temperature_points_c),
        "vdd_v": system_spec.vdd_v,
        "context_id": "VCOBlockContext.v1",
        "source": "initial_SystemTB_plus_declared_guard; frozen_before_candidate_validation",
        "guard_v": guard_v,
    }


def _validated_domain_from_context(context: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "vctrl_v": [float(context["vctrl_min_v"]), float(context["vctrl_max_v"])],
        "temperature_c": [float(value) for value in context["temperature_points_c"]],
        "vdd_v": [float(context["vdd_v"])],
        "validation_source": str(context.get("context_id", "VCOBlockContext.v1")),
    }


def _write_jsonl(events: Iterable[Mapping[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def _write_optional_plots(output_dir: Path, characterization: List[Mapping[str, Any]], sensitivity: Mapping[str, Any]) -> Dict[str, Any]:
    """Create compact scientific plots when matplotlib is available."""

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency
        return {"available": False, "reason": str(exc)}

    plots_dir = output_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    generated: List[str] = []

    # VCO tuning curve and phase noise at 1 MHz.
    nominal = [row for row in characterization if row["temperature_c"] == 25.0 and row["offset_hz"] == 1.0e6]
    if nominal:
        x = [float(row["vctrl_v"]) for row in nominal]
        f = [float(row["fosc_hz"]) / 1e9 for row in nominal]
        pn = [float(row["phase_noise_dbc_hz"]) for row in nominal]
        fig, ax = plt.subplots(figsize=(6.0, 4.0))
        ax.plot(x, f, marker="o", label="fosc")
        ax.set_xlabel("Vctrl (V)")
        ax.set_ylabel("fosc (GHz)")
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        path = plots_dir / "vco_tuning_curve.png"
        fig.savefig(path, dpi=140)
        plt.close(fig)
        generated.append(str(path.name))

        fig, ax = plt.subplots(figsize=(6.0, 4.0))
        ax.plot(x, pn, marker="o", color="tab:red", label="PN@1MHz")
        ax.set_xlabel("Vctrl (V)")
        ax.set_ylabel("Phase noise (dBc/Hz)")
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        path = plots_dir / "phase_noise_vs_vctrl.png"
        fig.savefig(path, dpi=140)
        plt.close(fig)
        generated.append(str(path.name))

    for parameter, title, xscale, yscale, filename in (
        ("pn_anchor_1mhz_dbc_hz", "Integrated jitter vs PN anchor", 1.0, 1e15, "jitter_vs_pn.png"),
        ("k1_hz_per_v", "Lock time vs K1", 1e-9, 1e6, "lock_time_vs_k1.png"),
    ):
        sweep = sensitivity.get("sweeps", {}).get(parameter)
        if not sweep:
            continue
        rows = sweep["rows"]
        x = [float(row["value"]) * xscale for row in rows]
        if parameter == "pn_anchor_1mhz_dbc_hz":
            y = [float(row["integrated_jitter_s"]) * yscale for row in rows]
            ylabel = "Integrated jitter (fs)"
        else:
            y = [None if row["lock_time_s"] is None else float(row["lock_time_s"]) * yscale for row in rows]
            ylabel = "Lock time (us)"
        fig, ax = plt.subplots(figsize=(6.0, 4.0))
        ax.plot(x, y, marker="o")
        ax.set_title(title)
        ax.set_xlabel(parameter)
        ax.set_ylabel(ylabel)
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        path = plots_dir / filename
        fig.savefig(path, dpi=140)
        plt.close(fig)
        generated.append(str(path.name))
    return {"available": True, "files": generated}


def _metric_line(evaluation: Mapping[str, Any]) -> str:
    metrics = evaluation["metrics"]
    lock = metrics["lock_time_s"]
    lock_text = "N/A" if lock is None else f"{float(lock) * 1e6:.3f} us"
    return (
        f"frequency={float(metrics['output_frequency_hz']) / 1e9:.9f} GHz, "
        f"jitter={float(metrics['integrated_jitter_s']) * 1e15:.3f} fs, "
        f"lock_time={lock_text}, power={float(metrics['power_w']) * 1e3:.3f} mW"
    )


def _write_summary(
    path: Path,
    case_id: str,
    initial_eval: Mapping[str, Any],
    required_boundary: Mapping[str, Any],
    recommended: VCORequirement,
    candidate_results: List[Mapping[str, Any]],
    final_eval: Mapping[str, Any] | None,
    plots: Mapping[str, Any],
    contract_validation: Mapping[str, Any],
    simulation_count: int,
) -> None:
    selected = next((item for item in candidate_results if item.get("selected")), None)
    lines = [
        f"# V1.0 SystemSpec-to-VCO-Spec proof: `{case_id}`",
        "",
        "## Deterministic status",
        "",
        f"- Initial system PASS: `{initial_eval['passed']}`",
        f"- PN anchor boundary: `{required_boundary['search_knob_boundary']:.6f} dBc/Hz`",
        f"- Worst measured PN at boundary: `{required_boundary['block_metric_at_boundary']:.6f} dBc/Hz`",
        f"- Recommended phase-noise requirement: `{recommended.phase_noise_1mhz_max_dbc_hz:.6f} dBc/Hz`",
        f"- Selected candidate: `{selected['candidate_id'] if selected else 'none'}`",
        f"- Final system PASS: `{final_eval['passed'] if final_eval else False}`",
        f"- Deterministic simulator calls: `{simulation_count}`",
        f"- Contract holdout MAE: v0=`{contract_validation['v0_mae_db']:.6f} dB`, v1=`{contract_validation['v1_mae_db']:.6f} dB`",
        "",
        "## Before / after",
        "",
        f"- Before: {_metric_line(initial_eval)}",
    ]
    if final_eval:
        lines.append(f"- After:  {_metric_line(final_eval)}")
    lines.extend(
        [
            "",
            "## Candidate validation",
            "",
            "| Candidate | BlockTB | SystemTB | Cost |",
            "|---|---:|---:|---:|",
        ]
    )
    for item in candidate_results:
        lines.append(
            f"| {item['candidate_id']} | {item['block_tb']['passed']} | "
            f"{item['system_evaluation']['passed']} | {item['engineering_cost']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## Evidence interpretation",
            "",
            "- The initial candidate is intentionally evaluated against an immutable SystemSpec.",
            "- Sensitivity is generated by deterministic parameter sweeps; it is not guessed by an agent.",
            "- The search boundary is obtained by a bracketed bisection on the PN anchor knob.",
            "- The VCO requirement is derived from measured worst PN under the frozen VCOBlockContext.",
            "- BlockTB uses the same frozen VCOBlockContext for every candidate.",
            "- Final PASS is accepted only when both BlockTB and validation-mode SystemTB pass.",
            "",
            f"Plots: `{plots}`",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(case_path: str | Path, output_dir: str | Path) -> Dict[str, Any]:
    case = load_case(case_path)
    case_id = str(case.get("case_id", Path(case_path).stem))
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    system_spec = SystemSpec.from_dict(case["system_spec"])
    validate_system_spec_payload(system_spec.to_dict())
    run_id = f"{case_id}:deterministic-v1"
    provenance = {
        "runner": "run_v1_prove.py",
        "backend": "python_behavioral",
        "model": "averaged_integer_n_cppll_v1",
        "fidelity": "synthetic_behavioral",
    }
    write_json(
        {
            "run_id": run_id,
            "schema_version": "1.1",
            "provenance": provenance,
            "deterministic": True,
            "random_seed": None,
        },
        output_path / "provenance.json",
    )
    base_vco = build_vco_instance(VCOParams(), case.get("base_vco", {}))
    candidates = _candidate_map(case)
    initial_candidate_id = str(case.get("initial_candidate_id", next(iter(candidates))))
    if initial_candidate_id not in candidates:
        raise ValueError(f"unknown initial candidate: {initial_candidate_id}")
    initial_candidate = candidates[initial_candidate_id]
    initial_vco = build_vco_instance(base_vco, initial_candidate)
    initial_requirement = VCORequirement.from_dict(case["initial_vco_requirement"])

    events: List[Dict[str, Any]] = []
    events.append({"step": "load_case", "case_id": case_id, "system_spec": system_spec.to_dict()})
    events.append(
        {
            "step": "initial_requirement",
            "candidate_id": initial_candidate_id,
            "requirement": initial_requirement.to_dict(),
        }
    )

    initial_eval = evaluate_system(system_spec, initial_vco, keep_raw=True)
    write_json(system_spec.to_dict(), output_path / "system_spec.json")
    canonical_system_spec = make_envelope(
        "system_spec",
        f"{run_id}:system_spec",
        system_spec.to_dict(),
        run_id=run_id,
        provenance=provenance,
    )
    validate_envelope(canonical_system_spec)
    write_json(canonical_system_spec, output_path / "canonical_system_spec.json")
    write_json(initial_requirement.to_dict(), output_path / "initial_vco_spec.json")
    write_json(strip_raw_results(initial_eval), output_path / "initial_system_evaluation.json")
    write_json(
        make_envelope(
            "system_evaluation",
            f"{run_id}:initial-system-evaluation",
            strip_raw_results(initial_eval),
            run_id=run_id,
            provenance=provenance,
        ),
        output_path / "canonical_initial_system_evaluation.json",
    )
    write_json(initial_eval.get("raw_results", []), output_path / "initial_system_raw.json")
    context_contract = _baseline_context_contract(
        system_spec,
        initial_eval["context"],
        float(case.get("allocation", {}).get("context_guard_v", 0.01)),
    )
    write_json(context_contract, output_path / "vco_environment_contract.json")
    events.append(
        {
            "step": "initial_system_evaluation",
            "passed": initial_eval["passed"],
            "metrics": initial_eval["metrics"],
            "residuals": initial_eval["residuals"],
            "context": initial_eval["context"],
        }
    )

    prove_cfg = case.get("prove", {})
    characterization = characterize_vco(
        initial_vco,
        prove_cfg.get("vctrl_points_v", [0.1, 0.3, 0.5, 0.7, 0.9, 1.1]),
        prove_cfg.get("temperature_points_c", system_spec.temperature_points_c),
        prove_cfg.get("offset_points_hz", [1.0e6]),
    )
    write_csv(characterization, output_path / "vco_characterization.csv")
    contract_evidence = build_contract_evidence(initial_vco, characterization)
    write_json(contract_evidence["contract_v0"], output_path / "contract_v0.json")
    write_json(contract_evidence["contract_v1"], output_path / "refined_vco_contract.json")
    write_json(contract_evidence["validation"], output_path / "contract_validation.json")
    block_meta = build_vco_block_meta_v1(
        contract_evidence["contract_v1"],
        validated_domain=_validated_domain_from_context(context_contract),
    )
    validate_block_meta(block_meta)
    write_json(block_meta, output_path / "vco_block_meta_v1.json")
    events.append(
        {
            "step": "contract_validation",
            "v0_mae_db": contract_evidence["validation"]["v0_mae_db"],
            "v1_mae_db": contract_evidence["validation"]["v1_mae_db"],
            "refinement_action": contract_evidence["validation"]["diagnosis"]["refinement_action"],
        }
    )
    events.append(
        {
            "step": "vco_characterization",
            "observation_count": len(characterization),
            "source": "realized synthetic candidate",
        }
    )

    sensitivity = run_sensitivity_suite(
        system_spec,
        initial_vco,
        prove_cfg.get("sweeps", {}),
    )
    write_json(sensitivity, output_path / "sensitivity.json")
    for parameter, sweep in sensitivity["sweeps"].items():
        write_csv(sweep["rows"], output_path / f"sensitivity_{parameter}.csv")
    events.append(
        {
            "step": "sensitivity",
            "method": sensitivity["method"],
            "parameters": sorted(sensitivity["sweeps"]),
        }
    )

    graph_artifact = build_v1_graph_artifact(
        contract=contract_evidence["contract_v1"],
        sensitivity=sensitivity,
        system_spec=system_spec.to_dict(),
        run_id=run_id,
    )
    write_json(graph_artifact, output_path / "vco_pll_graph.json")

    initial_vector = DesignVector(
        values=dict(initial_candidate.overrides),
        source=f"case.candidate.{initial_candidate_id}",
    )
    write_json(initial_vector.to_dict(), output_path / "initial_vco_design_vector.json")

    allocation_cfg = case.get("allocation", {})
    allocation_report = allocate_system_spec(
        SpecAllocationRequest(
            system_spec=system_spec,
            base_instance=base_vco,
            operating_context=context_contract,
            allocation_problem={
                **allocation_cfg,
                "initial_block_spec": initial_requirement.to_dict(),
            },
            block_id="VCO",
            request_id=f"{run_id}:forward-allocation",
        )
    )
    if not allocation_report["allocated"]:
        raise ValueError(f"SystemSpec allocation failed: {allocation_report}")
    boundary = dict(allocation_report["evidence"]["boundary"])
    required_requirement = VCORequirement.from_dict(
        allocation_report["allocated_block_spec"]
    )
    recommended_requirement = VCORequirement.from_dict(
        allocation_report["recommended_block_spec"]
    )
    write_json(allocation_report, output_path / "spec_allocation_report.json")
    write_json(boundary, output_path / "required_vco_spec_boundary.json")
    write_json(required_requirement.to_dict(), output_path / "required_vco_spec.json")
    write_json(recommended_requirement.to_dict(), output_path / "recommended_vco_spec.json")
    write_json(
        {
            "object_type": "requirement_evaluation",
            "status": "not_applicable",
            "reason": (
                "phase_noise_1mhz_max_dbc_hz is a measured BlockRequirement; "
                "it is not compiled into pn_anchor_1mhz_dbc_hz for SystemTB"
            ),
            "target_system_metric": boundary["target_system_metric"],
            "search_knob": boundary["search_knob"],
            "search_knob_boundary": boundary["search_knob_boundary"],
            "allocated_block_metric": "worst_phase_noise_1mhz_dbc_hz",
            "block_metric_at_boundary": boundary["block_metric_at_boundary"],
        },
        output_path / "recommended_requirement_evaluation.json",
    )
    write_json(
        {
            "schema_version": "1.0",
            "allowed_actions": sorted(ALLOWED_ACTIONS),
            "execution_policy": {
                "system_spec_mutable": False,
                "agent_can_declare_pass": False,
                "sensitivity_source": "deterministic_sweep",
            },
        },
        output_path / "agent_action_policy.json",
    )
    events.append(
        {
            "step": "system_to_block_allocation",
            "direction": "SystemSpec -> BlockSpec",
            "allocation_status": allocation_report["status"],
            "search_knob": boundary["search_knob"],
            "search_knob_boundary": boundary["search_knob_boundary"],
            "nearest_failing_search_knob": boundary["nearest_failing_search_knob"],
            "target_system_metric": boundary["target_system_metric"],
            "block_metric_at_boundary": boundary["block_metric_at_boundary"],
        }
    )

    candidate_results: List[Dict[str, Any]] = []
    for candidate_id, definition in candidates.items():
        instance = build_vco_instance(base_vco, definition)
        verification = verify_block_assignment(
            VerificationRequest(
                system_spec=system_spec,
                block_spec=recommended_requirement,
                realized_instance=instance,
                operating_context=context_contract,
                block_id="VCO",
                request_id=f"{run_id}:candidate:{candidate_id}",
                keep_raw=True,
            )
        )
        block_tb = verification["block_tb"]
        candidate_eval = verification["system_tb"]
        coverage = verification["context_coverage"]
        candidate_result = {
            "candidate_id": candidate_id,
            "engineering_cost": definition.engineering_cost,
            "description": definition.description,
            "design_vector": dict(definition.overrides),
            "realized_parameters": asdict(instance),
            "block_tb": block_tb,
            "context_coverage": coverage,
            "system_evaluation": strip_raw_results(candidate_eval),
        }
        candidate_results.append(candidate_result)
        write_json(block_tb, output_path / f"block_tb_{candidate_id}.json")
        write_json(candidate_eval["raw_results"], output_path / f"system_raw_{candidate_id}.json")
        events.append(
            {
                "step": "candidate_validation",
                "candidate_id": candidate_id,
                "block_tb_passed": block_tb["passed"],
                "system_passed": candidate_eval["passed"],
                "context_covered": coverage["passed"],
            }
        )

    feasible = [
        item
        for item in candidate_results
        if item["block_tb"]["passed"] and item["system_evaluation"]["passed"] and item["context_coverage"]["passed"]
    ]
    selected = min(feasible, key=lambda item: item["engineering_cost"]) if feasible else None
    if selected is not None:
        selected["selected"] = True
        final_instance = build_vco_instance(base_vco, candidates[selected["candidate_id"]])
        final_verification = verify_block_assignment(
            VerificationRequest(
                system_spec=system_spec,
                block_spec=recommended_requirement,
                realized_instance=final_instance,
                operating_context=context_contract,
                block_id="VCO",
                request_id=f"{run_id}:final",
                keep_raw=False,
            )
        )
        final_eval = final_verification["system_tb"]
        final_coverage = final_verification["context_coverage"]
        if not final_verification["passed"]:
            raise ValueError("independent final SystemTB or context closure failed")
        write_json(final_coverage, output_path / "final_context_coverage.json")
        # The compact evaluation is already written in candidate_results; write
        # the canonical final file as a separate stable artifact.
        write_json(final_eval, output_path / "final_system_evaluation.json")
        write_json(asdict(final_instance), output_path / "realized_vco_instance.json")
    else:
        final_eval = None
        write_json({"passed": False, "reason": "no feasible candidate"}, output_path / "final_system_evaluation.json")
    write_json(candidate_results, output_path / "block_feasibility.json")
    # Graph v1 remains the compatibility artifact.  Graph v2 is a typed map
    # of semantic roles plus workflow artifacts for future Agent proposals.
    graph_v2_artifact = build_v1_graph_v2_artifact(
        contract=contract_evidence["contract_v1"],
        sensitivity=sensitivity,
        system_spec=system_spec.to_dict(),
        run_id=run_id,
        initial_evaluation=strip_raw_results(initial_eval),
        boundary=boundary,
        recommended_requirement=recommended_requirement.to_dict(),
        candidate_results=candidate_results,
        final_evaluation=final_eval,
        block_meta=block_meta,
        context_contract=context_contract,
        final_context_coverage=None if selected is None else final_coverage,
    )
    selected_result = next((item for item in candidate_results if item.get("selected")), None)
    graph_audit = audit_allocation_graph(
        graph_v2_artifact,
        expected={
            "selected_candidate": None if selected_result is None else selected_result["candidate_id"],
            "search_knob_boundary": boundary["search_knob_boundary"],
            "required_pn": required_requirement.phase_noise_1mhz_max_dbc_hz,
            "recommended_pn": recommended_requirement.phase_noise_1mhz_max_dbc_hz,
            "block_tb": {} if selected_result is None else selected_result["block_tb"],
            "candidate_system": {} if selected_result is None else selected_result["system_evaluation"],
            "final_system": {} if final_eval is None else final_eval,
            "final_context_coverage": {} if selected is None else final_coverage,
        },
    )
    if not graph_audit["passed"]:
        raise ValueError(f"Graph semantic audit failed: {graph_audit}")
    write_json(graph_v2_artifact, output_path / "vco_pll_graph_v2.json")
    write_json(graph_audit, output_path / "graph_audit.json")
    write_json(build_agent_goal_context(graph_v2_artifact), output_path / "agent_goal_context.json")
    # Plane views are deterministic read-only projections of the canonical
    # graph.  They give a future Agent the smallest authorized context while
    # preserving the full cross-plane trace in vco_pll_graph_v2.json.
    write_json(all_plane_views(graph_v2_artifact), output_path / "graph_plane_views.json")
    write_json(factor_view(graph_v2_artifact), output_path / "graph_factor_view.json")
    events.append(
        {
            "step": "final_selection",
            "selected_candidate": None if selected is None else selected["candidate_id"],
            "final_passed": False if final_eval is None else final_eval["passed"],
        }
    )

    report_cfg = case.get("report", {})
    plots = (
        _write_optional_plots(output_path, characterization, sensitivity)
        if report_cfg.get("generate_plots", False)
        else {"available": False, "reason": "disabled_unless_explicitly_enabled"}
    )
    simulation_count = len(system_spec.temperature_points_c) * (
        1
        + sum(len(values) for values in prove_cfg.get("sweeps", {}).values())
        + 2
        + int(allocation_cfg.get("iterations", 24))
        + len(candidates)
        + (1 if selected is not None else 0)
    )
    _write_summary(
        output_path / "summary.md",
        case_id,
        strip_raw_results(initial_eval),
        boundary,
        recommended_requirement,
        candidate_results,
        final_eval,
        plots,
        contract_evidence["validation"],
        simulation_count,
    )
    events.append(
        {
            "step": "report",
            "output_dir": str(output_path),
            "plots": plots,
            "simulator_calls": simulation_count,
        }
    )
    _write_jsonl(events, output_path / "trajectory.jsonl")
    return {
        "case_id": case_id,
        "output_dir": str(output_path),
        "initial_passed": initial_eval["passed"],
        "search_knob_boundary": boundary["search_knob_boundary"],
        "block_metric_at_boundary": boundary["block_metric_at_boundary"],
        "required_requirement": required_requirement.to_dict(),
        "recommended_requirement": recommended_requirement.to_dict(),
        "selected_candidate": None if selected is None else selected["candidate_id"],
        "final_passed": False if final_eval is None else final_eval["passed"],
        "simulator_calls": simulation_count,
        "contract_validation": contract_evidence["validation"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default=str(DEFAULT_CASE), help="JSON benchmark case")
    parser.add_argument(
        "--output-dir",
        default="results/v1_vco_mapping_01",
        help="directory for replayable artifacts",
    )
    args = parser.parse_args()
    result = run(args.case, args.output_dir)
    print("Case:", result["case_id"])
    print("Initial SystemTB PASS:", result["initial_passed"])
    print("PN anchor boundary (dBc/Hz):", f"{result['search_knob_boundary']:.6f}")
    print("Worst measured PN at boundary (dBc/Hz):", f"{result['block_metric_at_boundary']:.6f}")
    print("Selected candidate:", result["selected_candidate"] or "none")
    print("Final SystemTB PASS:", result["final_passed"])
    print("Deterministic simulator calls:", result["simulator_calls"])
    print(
        "Contract holdout MAE (dB):",
        f"v0={result['contract_validation']['v0_mae_db']:.6f},",
        f"v1={result['contract_validation']['v1_mae_db']:.6f}",
    )
    print("Artifacts:", Path(result["output_dir"]).resolve())


if __name__ == "__main__":
    main()
