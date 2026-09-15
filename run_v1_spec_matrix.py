"""Run a deterministic SystemSpec-to-VCO-Spec allocation test matrix.

Positive cases execute the complete V1 runner.  Negative controls deliberately
violate a non-PN constraint and prove that the one-dimensional PN allocator
rejects the case instead of manufacturing a VCO PN requirement.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Mapping, MutableMapping, Sequence
import json

from run_v1_prove import run
from v1.model.pll_behavioral import VCOParams
from v1.pipeline import (
    abstract_pn_evaluation,
    build_vco_instance,
    search_required_pn_boundary,
    write_csv,
    write_json,
)
from v1.specs import SystemSpec, load_case


ROOT = Path(__file__).resolve().parent
DEFAULT_MATRIX = ROOT / "v1" / "cases" / "vco_mapping_matrix.json"
DEFAULT_OUTPUT = ROOT / "results" / "v1_spec_matrix"
REQUIRED_CASE_ARTIFACTS = (
    "system_spec.json",
    "initial_system_evaluation.json",
    "vco_characterization.csv",
    "sensitivity.json",
    "required_vco_spec_boundary.json",
    "recommended_vco_spec.json",
    "block_feasibility.json",
    "realized_vco_instance.json",
    "final_system_evaluation.json",
    "trajectory.jsonl",
    "summary.md",
    "vco_block_meta_v1.json",
    "vco_pll_graph_v2.json",
)


def _deep_merge(
    target: MutableMapping[str, Any], override: Mapping[str, Any]
) -> MutableMapping[str, Any]:
    """Recursively merge mappings; arrays and scalar values are replaced."""

    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(target.get(key), MutableMapping):
            _deep_merge(target[key], value)
        else:
            target[key] = deepcopy(value)
    return target


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_case(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _case_payload(
    base_case: Mapping[str, Any],
    matrix: Mapping[str, Any],
    entry: Mapping[str, Any],
) -> Dict[str, Any]:
    payload = deepcopy(dict(base_case))
    _deep_merge(payload, matrix.get("common_overrides", {}))
    _deep_merge(payload, entry.get("overrides", {}))
    payload["case_id"] = str(entry["case_id"])
    payload["description"] = str(entry.get("description", ""))
    payload["candidates"] = deepcopy(matrix["candidate_set"])
    payload["initial_candidate_id"] = "candidate_baseline"
    return payload


def _candidate_overrides(case: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    return {
        str(item["candidate_id"]): item.get("overrides", {})
        for item in case.get("candidates", [])
    }


def _false_checks(evaluation: Mapping[str, Any]) -> list[str]:
    failed = {
        str(name)
        for context in evaluation.get("per_context", [])
        for name, passed in context.get("checks", {}).items()
        if not passed
    }
    return sorted(failed)


def _fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return "PASS" if value else "FAIL"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _markdown_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    lines.extend("| " + " | ".join(str(value) for value in row) + " |" for row in rows)
    return lines


def _write_report(
    path: Path,
    forward_rows: Sequence[Mapping[str, Any]],
    boundary_rows: Sequence[Mapping[str, Any]],
    reverse_rows: Sequence[Mapping[str, Any]],
    rejected_rows: Sequence[Mapping[str, Any]],
    assertions: Mapping[str, bool],
) -> None:
    lines = [
        "# V1 SystemSpec-to-VCO-Spec test matrix",
        "",
        "本报告由 `python run_v1_spec_matrix.py` 确定性生成。正例运行完整 V1 pipeline；负例验证 PN 一维分配不会掩盖 lock-time/power 违例。",
        "",
        "## 表 0：12 步 pipeline 的测试证据",
        "",
    ]
    lines.extend(
        _markdown_table(
            ["步骤", "Pipeline 节点", "本次验证证据"],
            [
                ["1–3", "SystemSpec → SystemTB → residual", "system_spec.json + initial_system_evaluation.json + 表 1"],
                ["4–5", "characterization → sensitivity", "vco_characterization.csv + sensitivity.json"],
                ["6–7", "PN boundary → margin", "required_vco_spec_boundary.json + recommended_vco_spec.json + 表 2"],
                ["8–9", "candidate → BlockTB → SystemTB", "block_feasibility.json + 表 3"],
                ["10–11", "cost selection → final SystemTB", "realized_vco_instance.json + final_system_evaluation.json"],
                ["12", "trace/schema/graph", "trajectory.jsonl + BlockMeta + Graph v2 + artifact completeness assertion"],
            ],
        )
    )
    lines.extend([
        "",
        "## 表 1：SystemSpec → VCO Spec 正向分配",
        "",
    ])
    lines.extend(
        _markdown_table(
            ["Case", "Temp (C)", "Jitter limit (fs)", "Initial (fs)", "Residual (fs)", "Initial", "Required PN", "Recommended PN", "Abstract @rec (fs)", "Selected", "Final (fs)", "Final"],
            [
                [
                    row["case_id"],
                    row["temperature_points_c"],
                    _fmt(row["jitter_limit_fs"]),
                    _fmt(row["initial_jitter_fs"]),
                    _fmt(row["initial_jitter_residual_fs"]),
                    _fmt(row["initial_passed"]),
                    _fmt(row["required_pn_dbc_hz"], 6),
                    _fmt(row["recommended_pn_dbc_hz"], 6),
                    _fmt(row["recommended_abstract_jitter_fs"]),
                    row["selected_candidate"],
                    _fmt(row["final_jitter_fs"]),
                    _fmt(row["final_system_passed"]),
                ]
                for row in forward_rows
            ],
        )
    )
    lines.extend(["", "## 表 2：PN 边界双向验证", ""])
    lines.append("注：PN 数值越负代表要求越严。本表在求得边界两侧各取 0.05 dB，检查紧一侧 PASS、松一侧 FAIL。")
    lines.append("")
    lines.extend(
        _markdown_table(
            ["Case", "Required PN", "Tighter PN", "Tighter jitter", "Result", "Looser PN", "Looser jitter", "Result"],
            [
                [
                    row["case_id"],
                    _fmt(row["required_pn_dbc_hz"], 6),
                    _fmt(row["tighter_pn_dbc_hz"], 6),
                    _fmt(row["tighter_jitter_fs"]),
                    _fmt(row["tighter_passed"]),
                    _fmt(row["looser_pn_dbc_hz"], 6),
                    _fmt(row["looser_jitter_fs"]),
                    _fmt(row["looser_passed"]),
                ]
                for row in boundary_rows
            ],
        )
    )
    selected_rows = [row for row in reverse_rows if row["selected"]]
    lines.extend(["", "## 表 3：Allocated Spec → Candidate → BlockTB/SystemTB 反向验证", ""])
    lines.extend(
        _markdown_table(
            ["Case", "Candidate", "PN knob", "Worst PN in context", "BlockTB", "PLL jitter (fs)", "Lock (us)", "Frequency (GHz)", "Power (mW)", "SystemTB"],
            [
                [
                    row["case_id"],
                    row["candidate_id"],
                    _fmt(row["candidate_pn_knob_dbc_hz"]),
                    _fmt(row["worst_context_pn_dbc_hz"]),
                    _fmt(row["block_tb_passed"]),
                    _fmt(row["system_jitter_fs"]),
                    _fmt(row["system_lock_time_us"]),
                    _fmt(row["system_frequency_ghz"], 9),
                    _fmt(row["system_power_mw"]),
                    _fmt(row["system_tb_passed"]),
                ]
                for row in selected_rows
            ],
        )
    )
    lines.extend(["", "完整候选逐项结果见 `reverse_candidate_validation.csv`。", "", "## 表 4：一维 PN allocation 的正确拒绝案例", ""])
    lines.extend(
        _markdown_table(
            ["Case", "Jitter limit (fs)", "Lock limit (us)", "Power limit (mW)", "Tight PN trial", "Blocking checks", "Conclusion"],
            [
                [
                    row["case_id"],
                    _fmt(row["jitter_limit_fs"]),
                    _fmt(row["lock_limit_us"]),
                    _fmt(row["power_limit_mw"]),
                    _fmt(row["tight_trial_pn_dbc_hz"]),
                    ", ".join(row["blocking_checks"]),
                    "REJECTED as expected" if row["rejected_as_expected"] else "UNEXPECTED",
                ]
                for row in rejected_rows
            ],
        )
    )
    lines.extend(["", "## 自动断言", ""])
    lines.extend(
        f"- `{name}`: **{'PASS' if passed else 'FAIL'}**"
        for name, passed in assertions.items()
    )
    lines.extend(
        [
            "",
            "140 fs 和 100 fs case 的初始 SystemTB 虽然已 PASS，但 candidate 仍按“边界 + 1.5 dB 设计裕量”的 Block requirement 筛选；因此 100 fs case 会选择 low-noise candidate。",
            "",
            "## 结论",
            "",
            "在固定 PLL 架构、行为模型和其余约束可满足时，jitter SystemSpec 可以确定性映射为一维 VCO PN requirement；更严格的 jitter 会得到更严格（更负）的 PN。边界两侧的 PASS/FAIL 和候选回代结果共同构成正向求解与反向验证证据。若失败来自 lock time 或 power，PN-only allocator 会拒绝分配，说明必须进入 PN × Kvco 或多 Block allocation。",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_matrix(
    matrix_path: str | Path = DEFAULT_MATRIX,
    output_dir: str | Path = DEFAULT_OUTPUT,
) -> Dict[str, Any]:
    matrix_file = Path(matrix_path).resolve()
    matrix = load_case(matrix_file)
    base_case_path = matrix_file.parent / str(matrix["base_case"])
    base_case = load_case(base_case_path)
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    cases_dir = output / "cases"
    guard_db = float(matrix.get("boundary_guard_db", 0.05))

    forward_rows: list[Dict[str, Any]] = []
    boundary_rows: list[Dict[str, Any]] = []
    reverse_rows: list[Dict[str, Any]] = []
    rejected_rows: list[Dict[str, Any]] = []

    for entry in matrix["cases"]:
        case = _case_payload(base_case, matrix, entry)
        case_id = str(case["case_id"])
        case_dir = cases_dir / case_id
        case_file = case_dir / "case.json"
        _write_case(case_file, case)
        system_spec = SystemSpec.from_dict(case["system_spec"])
        base_vco = build_vco_instance(VCOParams(), case.get("base_vco", {}))
        allocation = case.get("allocation", {})
        loose = float(allocation.get("loose_bound_dbc_hz", -110.0))
        tight = float(allocation.get("tight_bound_dbc_hz", -125.0))
        iterations = int(allocation.get("iterations", 24))

        if not bool(entry["expected_allocatable"]):
            rejected = False
            error = ""
            try:
                search_required_pn_boundary(
                    system_spec, base_vco, loose, tight, iterations=iterations
                )
            except ValueError as exc:
                rejected = True
                error = str(exc)
            tight_evaluation = abstract_pn_evaluation(system_spec, base_vco, tight)[
                "system_evaluation"
            ]
            rejected_rows.append(
                {
                    "case_id": case_id,
                    "jitter_limit_fs": system_spec.integrated_jitter_max_s * 1e15,
                    "lock_limit_us": system_spec.lock_time_max_s * 1e6,
                    "power_limit_mw": None if system_spec.power_max_w is None else system_spec.power_max_w * 1e3,
                    "tight_trial_pn_dbc_hz": tight,
                    "tight_trial_jitter_fs": tight_evaluation["metrics"]["integrated_jitter_s"] * 1e15,
                    "blocking_checks": _false_checks(tight_evaluation),
                    "rejected_as_expected": rejected,
                    "allocator_error": error,
                }
            )
            continue

        result = run(case_file, case_dir)
        initial = _read_json(case_dir / "initial_system_evaluation.json")
        boundary = _read_json(case_dir / "required_vco_spec_boundary.json")
        recommended = _read_json(case_dir / "recommended_vco_spec.json")
        recommended_eval = _read_json(
            case_dir / "recommended_spec_vector_evaluation.json"
        )["system_evaluation"]
        candidates = _read_json(case_dir / "block_feasibility.json")
        final = _read_json(case_dir / "final_system_evaluation.json")
        missing_artifacts = [
            name for name in REQUIRED_CASE_ARTIFACTS if not (case_dir / name).is_file()
        ]
        required_pn = float(boundary["required_boundary"])
        tighter_pn = required_pn - guard_db
        looser_pn = required_pn + guard_db
        tighter_eval = abstract_pn_evaluation(system_spec, base_vco, tighter_pn)[
            "system_evaluation"
        ]
        looser_eval = abstract_pn_evaluation(system_spec, base_vco, looser_pn)[
            "system_evaluation"
        ]
        selected = next(item for item in candidates if item.get("selected"))

        forward_rows.append(
            {
                "case_id": case_id,
                "temperature_points_c": "/".join(
                    f"{value:g}" for value in system_spec.temperature_points_c
                ),
                "jitter_limit_fs": system_spec.integrated_jitter_max_s * 1e15,
                "lock_limit_us": system_spec.lock_time_max_s * 1e6,
                "power_limit_mw": None if system_spec.power_max_w is None else system_spec.power_max_w * 1e3,
                "initial_jitter_fs": initial["metrics"]["integrated_jitter_s"] * 1e15,
                "initial_jitter_residual_fs": initial["residuals"]["integrated_jitter_residual_s_max"] * 1e15,
                "initial_passed": bool(initial["passed"]),
                "required_pn_dbc_hz": required_pn,
                "recommended_pn_dbc_hz": float(recommended["phase_noise_1mhz_max_dbc_hz"]),
                "recommended_abstract_jitter_fs": recommended_eval["metrics"]["integrated_jitter_s"] * 1e15,
                "recommended_abstract_passed": bool(recommended_eval["passed"]),
                "selected_candidate": str(result["selected_candidate"]),
                "selected_block_tb_passed": bool(selected["block_tb"]["passed"]),
                "final_jitter_fs": final["metrics"]["integrated_jitter_s"] * 1e15,
                "final_lock_time_us": final["metrics"]["lock_time_s"] * 1e6,
                "final_frequency_ghz": final["metrics"]["output_frequency_hz"] / 1e9,
                "final_power_mw": final["metrics"]["power_w"] * 1e3,
                "final_system_passed": bool(final["passed"]),
                "evidence_artifacts_complete": not missing_artifacts,
                "missing_artifacts": missing_artifacts,
                "simulator_calls": int(result["simulator_calls"]),
            }
        )
        boundary_rows.append(
            {
                "case_id": case_id,
                "required_pn_dbc_hz": required_pn,
                "guard_db": guard_db,
                "tighter_pn_dbc_hz": tighter_pn,
                "tighter_jitter_fs": tighter_eval["metrics"]["integrated_jitter_s"] * 1e15,
                "tighter_passed": bool(tighter_eval["passed"]),
                "looser_pn_dbc_hz": looser_pn,
                "looser_jitter_fs": looser_eval["metrics"]["integrated_jitter_s"] * 1e15,
                "looser_passed": bool(looser_eval["passed"]),
            }
        )
        overrides_by_id = _candidate_overrides(case)
        for item in candidates:
            candidate_id = str(item["candidate_id"])
            overrides = overrides_by_id[candidate_id]
            system_eval = item["system_evaluation"]
            reverse_rows.append(
                {
                    "case_id": case_id,
                    "recommended_pn_dbc_hz": float(recommended["phase_noise_1mhz_max_dbc_hz"]),
                    "candidate_id": candidate_id,
                    "candidate_pn_knob_dbc_hz": float(overrides.get("pn_1mhz_dbc_hz", base_vco.pn_1mhz_dbc_hz)),
                    "candidate_k1_hz_per_v": float(overrides.get("k1_hz_per_v", base_vco.k1_hz_per_v)),
                    "worst_context_pn_dbc_hz": float(item["block_tb"]["worst_case"]["phase_noise_1mhz_dbc_hz"]),
                    "block_tb_passed": bool(item["block_tb"]["passed"]),
                    "system_jitter_fs": system_eval["metrics"]["integrated_jitter_s"] * 1e15,
                    "system_lock_time_us": system_eval["metrics"]["lock_time_s"] * 1e6,
                    "system_frequency_ghz": system_eval["metrics"]["output_frequency_hz"] / 1e9,
                    "system_power_mw": system_eval["metrics"]["power_w"] * 1e3,
                    "system_tb_passed": bool(system_eval["passed"]),
                    "selected": bool(item.get("selected")),
                }
            )

    nominal_jitter_rows = [
        row
        for row in forward_rows
        if row["temperature_points_c"] == "25"
    ]
    nominal_jitter_rows.sort(key=lambda item: item["jitter_limit_fs"], reverse=True)
    assertions = {
        "tighter_jitter_maps_to_tighter_pn": all(
            nominal_jitter_rows[index]["required_pn_dbc_hz"]
            > nominal_jitter_rows[index + 1]["required_pn_dbc_hz"]
            for index in range(len(nominal_jitter_rows) - 1)
        ),
        "boundary_tighter_side_passes": all(row["tighter_passed"] for row in boundary_rows),
        "boundary_looser_side_fails": all(not row["looser_passed"] for row in boundary_rows),
        "recommended_abstract_specs_pass": all(row["recommended_abstract_passed"] for row in forward_rows),
        "selected_candidates_pass_blocktb": all(row["selected_block_tb_passed"] for row in forward_rows),
        "selected_candidates_pass_systemtb": all(row["final_system_passed"] for row in forward_rows),
        "all_case_evidence_artifacts_exist": all(row["evidence_artifacts_complete"] for row in forward_rows),
        "non_pn_violations_are_rejected": all(row["rejected_as_expected"] for row in rejected_rows),
    }
    if not all(assertions.values()):
        failed = [name for name, passed in assertions.items() if not passed]
        raise AssertionError(f"spec matrix assertion(s) failed: {failed}")

    write_csv(forward_rows, output / "forward_allocation.csv")
    write_csv(boundary_rows, output / "boundary_reverse_check.csv")
    write_csv(reverse_rows, output / "reverse_candidate_validation.csv")
    write_csv(rejected_rows, output / "rejected_one_dimensional_cases.csv")
    summary = {
        "schema_version": "v1-spec-matrix-1.0",
        "matrix_id": matrix["matrix_id"],
        "deterministic": True,
        "base_case": str(matrix["base_case"]),
        "boundary_guard_db": guard_db,
        "forward_allocation": forward_rows,
        "boundary_reverse_checks": boundary_rows,
        "candidate_reverse_validation": reverse_rows,
        "rejected_one_dimensional_cases": rejected_rows,
        "assertions": assertions,
    }
    write_json(summary, output / "matrix_results.json")
    _write_report(
        output / "SPEC_MATRIX_REPORT.md",
        forward_rows,
        boundary_rows,
        reverse_rows,
        rejected_rows,
        assertions,
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", default=str(DEFAULT_MATRIX))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    result = run_matrix(args.matrix, args.output_dir)
    print("Matrix:", result["matrix_id"])
    print("Allocatable cases:", len(result["forward_allocation"]))
    print("Rejected one-dimensional cases:", len(result["rejected_one_dimensional_cases"]))
    for name, passed in result["assertions"].items():
        print(f"{name}: {'PASS' if passed else 'FAIL'}")
    print("Artifacts:", Path(args.output_dir).resolve())


if __name__ == "__main__":
    main()
