"""Execute several deterministic one-dimensional SystemSpec-to-VCO mappings.

This is an additive experiment harness.  It reuses the canonical Python
SystemTB and VCO BlockTB; the existing ``run_v1_prove.py`` PN baseline remains
unchanged.  Each mapping records sensitivity, a declared local fail/pass
bracket, boundary history, BlockTB validation, candidate realization and an
independent SystemTB replay.  A relation is reported as *rejected* when the
declared bracket is not valid or when the target is not locally monotonic.
"""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

from v1.model.pll_behavioral import VCOParams
from v1.pipeline import (
    abstract_vco_parameter_evaluation,
    build_vco_instance,
    characterize_vco,
    evaluate_system,
    run_parameter_sweep,
    search_required_scalar_boundary,
    measure_vco_behavior,
    validate_vco_spec,
    validate_vco_scalar_requirement,
    write_csv,
    write_json,
)
from v1.specs import SystemSpec, VCORequirement, load_case


ROOT = Path(__file__).resolve().parent
DEFAULT_CASE = ROOT / "v1" / "cases" / "vco_mapping_01.json"
DEFAULT_OUTPUT = ROOT / "results" / "v1_scalar_mapping_suite"


def _single_target_spec(
    case: Mapping[str, Any],
    target: str,
    overrides: Mapping[str, Any] | None = None,
) -> SystemSpec:
    """Make all non-target constraints comfortably non-binding.

    This does not alter the physical model.  It isolates one SystemSpec
    relation so the proof can answer whether a scalar VCO knob is identifiable
    for that metric instead of mixing unrelated failures into the boundary.
    """

    payload = deepcopy(dict(case["system_spec"]))
    limits = payload.setdefault("limits", {})
    limits["integrated_jitter_max_s"] = 1.0e-9 if target != "integrated_jitter" else limits["integrated_jitter_max_s"]
    limits["lock_time_max_s"] = 1.0e-3 if target != "lock_time" else limits["lock_time_max_s"]
    limits["power_max_w"] = 1.0 if target != "power" else limits.get("power_max_w", 8.0e-3)
    if target == "frequency":
        # Keep the benchmark output target but make lock/jitter/power loose.
        limits["output_frequency_tolerance_hz"] = limits.get("output_frequency_tolerance_hz", 1.0e5)
    for section, values in (overrides or {}).items():
        if isinstance(values, Mapping):
            payload.setdefault(section, {}).update(values)
        else:
            payload[section] = values
    return SystemSpec.from_dict(payload)


def _mapping_definitions() -> Sequence[Mapping[str, Any]]:
    return (
        {
            "mapping_id": "jitter_to_pn",
            "target": "integrated_jitter",
            "parameter": "pn_anchor_1mhz_dbc_hz",
            "relation": "max",
            "failing_bound": -114.0,
            "passing_bound": -120.0,
            "sweep": [-120.0, -118.0, -116.0, -114.0],
            "requirement_margin": 1.5,
            "candidate_values": [-116.0, -118.0, -120.0, -122.0],
            "system_spec_overrides": {},
            "global_probe": [-125.0, -122.0, -120.0, -118.0, -116.0, -114.0, -110.0],
        },
        {
            "mapping_id": "lock_time_to_kvco",
            "target": "lock_time",
            "parameter": "k1_hz_per_v",
            "relation": "min",
            "failing_bound": 0.60e9,
            "passing_bound": 0.70e9,
            "sweep": [0.55e9, 0.60e9, 0.62e9, 0.64e9, 0.66e9, 0.70e9],
            "requirement_margin": 0.0,
            "candidate_values": [0.62e9, 0.64e9, 0.66e9, 0.70e9],
            "system_spec_overrides": {"limits": {"lock_time_max_s": 3.4e-5}},
            "global_probe": [0.55e9, 0.60e9, 0.62e9, 0.64e9, 0.70e9, 0.90e9, 1.05e9, 1.10e9, 1.40e9, 1.60e9],
        },
        {
            "mapping_id": "power_to_nominal_power",
            "target": "power",
            "parameter": "nominal_power_w",
            "relation": "max",
            "failing_bound": 0.0055,
            "passing_bound": 0.0045,
            "sweep": [0.0035, 0.0040, 0.0045, 0.0050, 0.0055],
            "requirement_margin": 0.0,
            "candidate_values": [0.0050, 0.0048, 0.0047, 0.0045],
            "system_spec_overrides": {"limits": {"power_max_w": 5.2e-3}},
            "global_probe": [0.0035, 0.0040, 0.0045, 0.0050, 0.0055, 0.0060, 0.0070],
        },
        {
            "mapping_id": "frequency_to_f0",
            "target": "frequency",
            "parameter": "f0_hz",
            "relation": "min",
            "failing_bound": 4.60e9,
            "passing_bound": 4.65e9,
            "sweep": [4.60e9, 4.61e9, 4.62e9, 4.63e9, 4.65e9, 4.70e9],
            "requirement_margin": 0.0,
            "candidate_values": [4.60e9, 4.61e9, 4.62e9, 4.65e9],
            "system_spec_overrides": {
                "pll": {"divider_n": 116},
                "target_frequency_hz": 5.8e9,
            },
            "global_probe": [3.5e9, 3.8e9, 4.0e9, 4.60e9, 4.65e9, 4.80e9, 5.40e9, 5.60e9, 6.0e9, 6.5e9, 7.0e9],
        },
    )


def _target_passed(evaluation: Mapping[str, Any], target: str) -> bool:
    checks = {
        str(name): bool(passed)
        for context in evaluation.get("per_context", [])
        for name, passed in context.get("checks", {}).items()
    }
    if target == "lock_time":
        return checks.get("lock_time", False) and checks.get("locked", False)
    if target == "frequency":
        return checks.get("output_frequency", False)
    return checks.get(target, False)


def _target_summary(
    system_spec: SystemSpec,
    evaluation: Mapping[str, Any],
    target: str,
) -> Dict[str, Any]:
    metrics = evaluation["metrics"]
    residuals = evaluation["residuals"]
    if target == "integrated_jitter":
        return {
            "requirement": system_spec.integrated_jitter_max_s,
            "value": metrics["integrated_jitter_s"],
            "residual": residuals["integrated_jitter_residual_s_max"],
            "unit": "s",
        }
    if target == "lock_time":
        return {
            "requirement": system_spec.lock_time_max_s,
            "value": metrics["lock_time_s"],
            "residual": residuals["lock_time_residual_s_max"],
            "unit": "s",
        }
    if target == "power":
        return {
            "requirement": system_spec.power_max_w,
            "value": metrics["power_w"],
            "residual": residuals["power_residual_w_max"],
            "unit": "W",
        }
    return {
        "requirement": system_spec.target_frequency_hz,
        "tolerance": system_spec.output_frequency_tolerance_hz,
        "value": metrics["output_frequency_hz"],
        "residual": residuals["output_frequency_residual_hz_max"],
        "unit": "Hz",
    }


def _allocated_block_metric(parameter: str, relation: str) -> str:
    if parameter == "pn_anchor_1mhz_dbc_hz":
        return "worst_phase_noise_1mhz_dbc_hz"
    if parameter == "k1_hz_per_v":
        return "kvco_min_hz_per_v" if relation == "min" else "kvco_max_hz_per_v"
    if parameter == "nominal_power_w":
        return "power_min_w" if relation == "min" else "worst_power_w"
    if parameter == "f0_hz":
        return "frequency_max_hz" if relation == "min" else "frequency_min_hz"
    raise ValueError(f"no measured block metric mapping for {parameter}")


def _behavior_metric(parameter: str) -> str:
    if parameter == "pn_anchor_1mhz_dbc_hz":
        return "phase_noise_1mhz_dbc_hz"
    if parameter == "k1_hz_per_v":
        return "kvco_hz_per_v"
    if parameter == "nominal_power_w":
        return "power_w"
    if parameter == "f0_hz":
        return "frequency_hz"
    raise ValueError(f"no behavior metric mapping for {parameter}")


def _assert_local_monotonic(rows: Sequence[Mapping[str, Any]], target: str) -> Dict[str, Any]:
    """Report monotonicity of the target residual/pass result, not assumptions."""

    values = [float(row["value"]) for row in rows]
    metrics = []
    for row in rows:
        metrics.append(
            None
            if row.get("lock_time_s") is None
            else float(row["lock_time_s"])
            if target == "lock_time"
            else float(row["output_frequency_hz"])
            if target == "frequency"
            else float(row["power_w"])
            if target == "power"
            else float(row["integrated_jitter_s"])
        )
    finite = [item for item in metrics if item is not None]
    # A boundary proof only needs pass/fail ordering around the declared
    # bracket.  Record the sequence so a future search controller can reject a
    # non-monotonic relation instead of treating bisection as valid.
    passed = [_target_passed(row["evaluation"], target) for row in rows]
    transitions = sum(first != second for first, second in zip(passed, passed[1:]))
    return {
        "values": values,
        "target_metric_values": metrics,
        "target_pass_sequence": passed,
        "pass_fail_transitions": transitions,
        "single_transition": transitions <= 1,
        "finite_metric_values": len(finite) == len(metrics),
    }


def run_suite(case_path: str | Path = DEFAULT_CASE, output_dir: str | Path = DEFAULT_OUTPUT) -> Dict[str, Any]:
    case = load_case(case_path)
    base_vco = build_vco_instance(VCOParams(), case.get("base_vco", {}))
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    results: list[Dict[str, Any]] = []

    for definition in _mapping_definitions():
        mapping_id = str(definition["mapping_id"])
        target = str(definition["target"])
        spec = _single_target_spec(
            case,
            target,
            definition.get("system_spec_overrides", {}),
        )
        mapping_dir = output / mapping_id
        mapping_dir.mkdir(parents=True, exist_ok=True)
        write_json(spec.to_dict(), mapping_dir / "system_spec.json")

        characterization = characterize_vco(
            base_vco,
            [spec.vctrl_min_v, 0.5 * (spec.vctrl_min_v + spec.vctrl_max_v), spec.vctrl_max_v],
            spec.temperature_points_c,
            [1.0e6],
        )
        write_csv(characterization, mapping_dir / "vco_characterization.csv")

        sweep = run_parameter_sweep(spec, base_vco, str(definition["parameter"]), definition["sweep"])
        rows = []
        for raw_row in sweep["rows"]:
            evaluation = evaluate_system(
                spec,
                build_vco_instance(base_vco, {str(definition["parameter"]): raw_row["value"]}),
                keep_raw=False,
            )
            rows.append({**raw_row, "evaluation": evaluation})
        monotonicity = _assert_local_monotonic(rows, target)
        global_raw = run_parameter_sweep(
            spec,
            base_vco,
            str(definition["parameter"]),
            definition["global_probe"],
        )
        global_rows = []
        for raw_row in global_raw["rows"]:
            evaluation = evaluate_system(
                spec,
                build_vco_instance(
                    base_vco,
                    {str(definition["parameter"]): raw_row["value"]},
                ),
                keep_raw=False,
            )
            global_rows.append({**raw_row, "evaluation": evaluation})
        global_shape = _assert_local_monotonic(global_rows, target)
        global_shape["classification"] = (
            "single_boundary_over_probed_range"
            if global_shape["pass_fail_transitions"] <= 1
            else "feasible_window_or_non_monotonic_over_probed_range"
        )
        write_json(
            {
                "method": "deterministic_grid_sweep",
                "local_sweep": sweep,
                "local_monotonicity": monotonicity,
                "global_probe": global_raw,
                "global_shape": global_shape,
            },
            mapping_dir / "sensitivity.json",
        )

        boundary: Dict[str, Any] | None = None
        error: str | None = None
        try:
            boundary = search_required_scalar_boundary(
                spec,
                base_vco,
                parameter=str(definition["parameter"]),
                target_check="output_frequency" if target == "frequency" else target,
                failing_bound=float(definition["failing_bound"]),
                passing_bound=float(definition["passing_bound"]),
                iterations=20,
            )
        except ValueError as exc:
            error = str(exc)

        initial = evaluate_system(spec, base_vco, keep_raw=False)
        requirement_value = (
            float(definition["candidate_values"][-1])
            if boundary is None
            else float(boundary["search_knob_boundary"])
        )
        frozen_context = {
            "vctrl_min_v": spec.vctrl_min_v,
            "vctrl_max_v": spec.vctrl_max_v,
            "temperature_points_c": list(spec.temperature_points_c),
            "vdd_v": spec.vdd_v,
            "context_id": "VCOBlockContext.v1",
            "source": "declared SystemSpec operating envelope; frozen before candidate evaluation",
        }
        validity = {} if boundary is None else boundary["validity_domain"]
        allocated_block_metric = _allocated_block_metric(
            str(definition["parameter"]),
            str(definition["relation"]),
        )
        if boundary is not None:
            boundary_vco = build_vco_instance(
                base_vco,
                {str(definition["parameter"]): float(boundary["search_knob_boundary"])},
            )
            boundary_measurement = measure_vco_behavior(spec, boundary_vco, frozen_context)
            boundary = {
                **boundary,
                "allocated_block_metric": allocated_block_metric,
                "block_metric_at_boundary": boundary_measurement["worst_case"][allocated_block_metric],
                "boundary_block_measurement": {
                    "context": boundary_measurement["context"],
                    "worst_case": boundary_measurement["worst_case"],
                    "measurement_method": boundary_measurement["measurement_method"],
                    "provenance": boundary_measurement["provenance"],
                },
            }
            requirement_value = float(boundary["block_metric_at_boundary"])
        candidate_trials: list[Dict[str, Any]] = []
        base_parameter_value = float(getattr(base_vco, str(definition["parameter"])))
        for candidate_value in definition["candidate_values"]:
            candidate_vco = build_vco_instance(
                base_vco,
                {str(definition["parameter"]): float(candidate_value)},
            )
            if definition["parameter"] == "pn_anchor_1mhz_dbc_hz":
                block = validate_vco_spec(
                    spec,
                    VCORequirement(
                        phase_noise_1mhz_max_dbc_hz=requirement_value,
                    ),
                    candidate_vco,
                    frozen_context,
                )
            else:
                block = validate_vco_scalar_requirement(
                    spec,
                    parameter=str(definition["parameter"]),
                    relation=str(definition["relation"]),
                    required_value=requirement_value,
                    vco=candidate_vco,
                    system_context=frozen_context,
                    validity_min=validity.get("parameter_min"),
                    validity_max=validity.get("parameter_max"),
                )
            candidate_system = evaluate_system(spec, candidate_vco, keep_raw=False)
            coverage_checks = {
                "vctrl_min": float(candidate_system["context"]["vctrl_min_v"]) >= float(frozen_context["vctrl_min_v"]),
                "vctrl_max": float(candidate_system["context"]["vctrl_max_v"]) <= float(frozen_context["vctrl_max_v"]),
                "temperature": set(candidate_system["context"]["temperature_points_c"]).issubset(
                    set(frozen_context["temperature_points_c"])
                ),
                "vdd": float(candidate_system["context"]["vdd_v"]) == float(frozen_context["vdd_v"]),
            }
            context_coverage = {
                "passed": all(coverage_checks.values()),
                "checks": coverage_checks,
                "contract": frozen_context,
                "actual": candidate_system["context"],
            }
            candidate_trials.append(
                {
                    "candidate_id": f"{mapping_id}:{float(candidate_value):.9g}",
                    "parameter_value": float(candidate_value),
                    "engineering_cost": abs(float(candidate_value) - base_parameter_value)
                    / max(abs(base_parameter_value), 1.0e-30),
                    "block_tb": block,
                    "context_coverage": context_coverage,
                    "system_tb": candidate_system,
                    "feasible": bool(
                        block["passed"]
                        and context_coverage["passed"]
                        and candidate_system["passed"]
                    ),
                }
            )
        feasible = [item for item in candidate_trials if item["feasible"]]
        if not feasible:
            raise AssertionError(f"no feasible scalar candidate for {mapping_id}")
        selected = min(feasible, key=lambda item: (item["engineering_cost"], item["candidate_id"]))
        candidate_value = float(selected["parameter_value"])
        candidate_vco = build_vco_instance(
            base_vco,
            {str(definition["parameter"]): candidate_value},
        )
        block = selected["block_tb"]
        candidate_system = selected["system_tb"]
        context_coverage = selected["context_coverage"]
        final = evaluate_system(spec, candidate_vco, keep_raw=False)
        result = {
            "mapping_id": mapping_id,
            "target_system_metric": target,
            "allocated_vco_parameter": definition["parameter"],
            "candidate_id": selected["candidate_id"],
            "initial": initial,
            "initial_target": _target_summary(spec, initial, target),
            "sensitivity": monotonicity,
            "global_shape": global_shape,
            "boundary": boundary,
            "boundary_error": error,
            "candidate": {
                "allocated_requirement": {
                    "search_knob": definition["parameter"],
                    "relation": definition["relation"],
                    "required_value": requirement_value,
                    "behavior_metric": _behavior_metric(str(definition["parameter"])),
                    "measured_metric": allocated_block_metric,
                    "validity_domain": validity,
                },
                "parameter_value": candidate_value,
                "candidate_search": {
                    "method": "deterministic_one_dimensional_candidate_grid",
                    "objective": "minimum normalized distance from base parameter among feasible candidates",
                    "trials": candidate_trials,
                    "selected_candidate_id": selected["candidate_id"],
                },
                "block_tb": block,
                "context_coverage": context_coverage,
                "system_tb": candidate_system,
                "final_system_tb": final,
                "final_target": _target_summary(spec, final, target),
            },
            "claims": {
                "initial_target_failed": not _target_passed(initial, target),
                "boundary_found": boundary is not None,
                "candidate_block_tb_passed": bool(block["passed"]),
                "candidate_system_tb_passed": bool(final["passed"]),
                "candidate_context_covered": bool(context_coverage["passed"]),
                "replay_identical": candidate_system == final,
                "local_one_dimensional_proof": boundary is not None and monotonicity["single_transition"],
                "global_single_boundary_over_probed_range": global_shape["pass_fail_transitions"] <= 1,
            },
        }
        write_json(result, mapping_dir / "mapping_result.json")
        results.append(result)

    summary = {
        "schema_version": "v1-scalar-mapping-suite-1.0",
        "deterministic": True,
        "model": "averaged_integer_n_cppll_v1 + synthetic_behavioral_vco_v1",
        "random_seed": None,
        "mappings": results,
        "assertions": {
            "all_boundaries_found": all(item["claims"]["boundary_found"] for item in results),
            "all_initial_targets_failed": all(item["claims"]["initial_target_failed"] for item in results),
            "all_blocktb_pass": all(item["claims"]["candidate_block_tb_passed"] for item in results),
            "all_systemtb_pass": all(item["claims"]["candidate_system_tb_passed"] for item in results),
            "all_contexts_covered": all(item["claims"]["candidate_context_covered"] for item in results),
            "all_replays_identical": all(item["claims"]["replay_identical"] for item in results),
            "all_local_proofs": all(item["claims"]["local_one_dimensional_proof"] for item in results),
        },
    }
    write_json(summary, output / "mapping_suite_summary.json")
    table_rows = []
    candidate_rows = []
    for item in results:
        boundary = item["boundary"] or {}
        final_metrics = item["candidate"]["final_system_tb"]["metrics"]
        table_rows.append(
            {
                "mapping_id": item["mapping_id"],
                "system_metric": item["target_system_metric"],
                "vco_parameter": item["allocated_vco_parameter"],
                "search_knob_boundary": boundary.get("search_knob_boundary"),
                "block_metric_at_boundary": boundary.get("block_metric_at_boundary"),
                "allocated_block_metric": boundary.get("allocated_block_metric"),
                "nearest_failing_search_knob": boundary.get("nearest_failing_search_knob"),
                "candidate_value": item["candidate"]["parameter_value"],
                "system_requirement": item["initial_target"]["requirement"],
                "initial_target_value": item["initial_target"]["value"],
                "initial_target_residual": item["initial_target"]["residual"],
                "final_target_value": item["candidate"]["final_target"]["value"],
                "final_target_residual": item["candidate"]["final_target"]["residual"],
                "target_unit": item["initial_target"]["unit"],
                "global_shape": item["global_shape"]["classification"],
                "block_tb_passed": item["claims"]["candidate_block_tb_passed"],
                "system_tb_passed": item["claims"]["candidate_system_tb_passed"],
                "final_jitter_fs": final_metrics["integrated_jitter_s"] * 1e15,
                "final_lock_time_us": None if final_metrics["lock_time_s"] is None else final_metrics["lock_time_s"] * 1e6,
                "final_frequency_ghz": final_metrics["output_frequency_hz"] / 1e9,
                "final_power_mw": final_metrics["power_w"] * 1e3,
            }
        )
        for trial in item["candidate"]["candidate_search"]["trials"]:
            candidate_rows.append(
                {
                    "mapping_id": item["mapping_id"],
                    "candidate_id": trial["candidate_id"],
                    "parameter_value": trial["parameter_value"],
                    "engineering_cost": trial["engineering_cost"],
                    "block_tb_passed": trial["block_tb"]["passed"],
                    "context_covered": trial["context_coverage"]["passed"],
                    "system_tb_passed": trial["system_tb"]["passed"],
                    "feasible": trial["feasible"],
                    "selected": trial["candidate_id"] == item["candidate_id"],
                }
            )
    write_csv(table_rows, output / "mapping_summary.csv")
    write_csv(candidate_rows, output / "candidate_search.csv")
    report = [
        "# V1 多类型一维 SystemSpec-to-VCO-Spec 映射报告",
        "",
        "本报告由 `python run_v1_mapping_suite.py` 确定性生成；模型与指标均没有随机采样。",
        "",
        "| System metric | System limit/target | Initial | VCO search knob | Search boundary | Candidate | Final | Probed shape | BlockTB | SystemTB |",
        "|---|---:|---:|---|---:|---:|---:|---|---|---|",
    ]
    for row in table_rows:
        report.append(
            f"| {row['system_metric']} | {row['system_requirement']:.9g} {row['target_unit']} | "
            f"{row['initial_target_value']:.9g} | {row['vco_parameter']} | "
            f"{row['search_knob_boundary']:.9g} | {row['candidate_value']:.9g} | "
            f"{row['final_target_value']:.9g} | {row['global_shape']} | "
            f"{'PASS' if row['block_tb_passed'] else 'FAIL'} | "
            f"{'PASS' if row['system_tb_passed'] else 'FAIL'} |"
        )
    report.extend(
        [
            "",
            "## 解释",
            "",
            "- `single_boundary_over_probed_range`：在本次显式扫描范围内只有一个 PASS/FAIL 分界，可作为一维上下界。",
            "- `feasible_window_or_non_monotonic_over_probed_range`：宽范围内有多个分界，只能在记录的 validity bracket 内使用局部一维映射；不能宣称全局单调。",
            "- frequency→f0 的真正 Block 能力含义是目标频率是否落入 VCO tuning coverage；f0 是当前行为模型中的搜索参数。",
            "- 每条映射都执行一个显式的一维 candidate grid；按可行性和相对 base parameter 的最小改变量选择 candidate。完整结果见 `candidate_search.csv`。",
            "- 所有 candidate 都先通过冻结 context 下的 BlockTB，再用同一 realized instance 独立重跑 SystemTB。SystemTB PASS 但 BlockTB FAIL 的候选不会被选择。",
        ]
    )
    (output / "MAPPING_SUITE_REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    if not all(summary["assertions"].values()):
        failed = [name for name, passed in summary["assertions"].items() if not passed]
        raise AssertionError(f"mapping suite assertion(s) failed: {failed}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default=str(DEFAULT_CASE))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    result = run_suite(args.case, args.output_dir)
    print("Suite:", result["schema_version"])
    for item in result["mappings"]:
        claims = item["claims"]
        print(
            f"{item['mapping_id']}: boundary={'PASS' if claims['boundary_found'] else 'FAIL'} "
            f"BlockTB={'PASS' if claims['candidate_block_tb_passed'] else 'FAIL'} "
            f"SystemTB={'PASS' if claims['candidate_system_tb_passed'] else 'FAIL'}"
        )
    for name, passed in result["assertions"].items():
        print(f"{name}: {'PASS' if passed else 'FAIL'}")
    print("Artifacts:", Path(args.output_dir).resolve())


if __name__ == "__main__":
    main()
