"""Qualify a measured Kvco axis for the V1.5 joint-contract extension.

The script consumes frozen V1.5 boundary and off-grid artifacts.  It does not
change the canonical nine-entry PN BlockSpec map.  It compares three possible
second-axis representations:

* SystemTB operating-point Kvco (the value used by the loop model);
* BlockTB Kvco minimum over the frozen Vctrl context;
* BlockTB Kvco maximum over the frozen Vctrl context.

The output is evidence for choosing a future contract axis, not a joint
BlockSpec allocation or transistor-level signoff.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

from v1.io import (
    evidence_digest,
    file_sha256,
    read_json,
    write_csv,
    write_evidence_json,
)

ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE = ROOT / "results" / "v1_5_continuity_v1_5"
DEFAULT_OUTPUT = ROOT / "results" / "v1_5_kvco_mapping_v1_5"


def _monotonic(values: Sequence[float], direction: str) -> bool:
    pairs = zip(values, values[1:])
    if direction == "increasing":
        return all(right >= left for left, right in pairs)
    if direction == "decreasing":
        return all(right <= left for left, right in pairs)
    raise ValueError(direction)


def _range(values: Sequence[float]) -> Dict[str, float]:
    return {"min": min(values), "max": max(values), "span": max(values) - min(values)}


def _linear_fit(x: Sequence[float], y: Sequence[float]) -> Dict[str, float]:
    if len(x) < 2:
        raise ValueError("linear fit requires at least two points")
    x_mean = sum(x) / len(x)
    y_mean = sum(y) / len(y)
    denom = sum((item - x_mean) ** 2 for item in x)
    slope = sum((a - x_mean) * (b - y_mean) for a, b in zip(x, y)) / denom
    intercept = y_mean - slope * x_mean
    residuals = [b - (intercept + slope * a) for a, b in zip(x, y)]
    ss_res = sum(value * value for value in residuals)
    ss_tot = sum((value - y_mean) ** 2 for value in y)
    return {
        "slope": slope,
        "intercept": intercept,
        "r2": 1.0 if ss_tot == 0.0 else 1.0 - ss_res / ss_tot,
        "max_abs_residual": max(abs(value) for value in residuals),
        "mae_residual": sum(abs(value) for value in residuals) / len(residuals),
    }


def _boundary_rows(source: Path) -> list[Dict[str, Any]]:
    frozen = read_json(source / "frozen_conditional_contracts.json")
    snapshot = frozen["snapshot"]["boundary_block_contract"]
    rows: list[Dict[str, Any]] = []
    for entry in snapshot["entries"]:
        condition = entry["condition"]
        behavior = entry["measured_block_behavior"]
        system = entry["system_boundary_confirmation"]
        rows.append(
            {
                "source": "mapped_boundary",
                "k1_hz_per_v": float(condition["value"]),
                "k1_ghz_per_v": float(condition["value"]) / 1.0e9,
                "pn_anchor_boundary_dbc_hz": float(
                    entry["source_system_boundary"]["passing_value"]
                ),
                "boundary_measured_pn_dbc_hz": float(
                    behavior["worst_phase_noise_1mhz_dbc_hz"]
                ),
                "pn_spec_dbc_hz": float(
                    behavior["worst_phase_noise_1mhz_dbc_hz"]
                )
                - 1.5,
                "kvco_operating_hz_per_v": float(
                    system["metrics"]["kvco_hz_per_v"]
                ),
                "kvco_min_hz_per_v": float(behavior["kvco_min_hz_per_v"]),
                "kvco_max_hz_per_v": float(behavior["kvco_max_hz_per_v"]),
                "lock_time_s": float(system["metrics"]["lock_time_s"]),
                "loop_bandwidth_hz": float(system["metrics"]["loop_bandwidth_hz"]),
                "system_boundary_passed": bool(system["passed"]),
                "block_tb_passed": bool(entry["block_tb"]["passed"]),
                "context_covered": bool(
                    entry["independent_replay_validation"]["context_covered"]
                ),
            }
        )
    offgrid = read_json(source / "offgrid_boundary_allocations.json")
    for item in offgrid["entries"]:
        detail = item["detail"]
        behavior = detail["boundary_replay"]["behavior_vector"]
        system = detail["boundary_replay"]["system_metrics"]
        rows.append(
            {
                "source": "off_grid_boundary",
                "k1_hz_per_v": float(item["k1_hz_per_v"]),
                "k1_ghz_per_v": float(item["k1_ghz_per_v"]),
                "pn_anchor_boundary_dbc_hz": float(
                    detail["actual_allocation"]["boundary_pn_anchor_dbc_hz"]
                ),
                "boundary_measured_pn_dbc_hz": float(
                    detail["actual_allocation"][
                        "boundary_measured_worst_pn_dbc_hz"
                    ]
                ),
                "pn_spec_dbc_hz": float(
                    detail["actual_allocation"]["allocated_pn_spec_dbc_hz"]
                ),
                "kvco_operating_hz_per_v": float(system["kvco_hz_per_v"]),
                "kvco_min_hz_per_v": float(behavior["kvco_min_hz_per_v"]),
                "kvco_max_hz_per_v": float(behavior["kvco_max_hz_per_v"]),
                "lock_time_s": float(system["lock_time_s"]),
                "loop_bandwidth_hz": float(system["loop_bandwidth_hz"]),
                "system_boundary_passed": bool(
                    detail["boundary_replay"]["system_tb_passed"]
                ),
                "block_tb_passed": bool(
                    detail["boundary_replay"]["direct_required_pn_blocktb_passed"]
                ),
                "context_covered": bool(detail["boundary_replay"]["context_covered"]),
            }
        )
    return sorted(rows, key=lambda row: (row["k1_hz_per_v"], row["source"]))


def _axis_analysis(rows: Sequence[Mapping[str, Any]], name: str) -> Dict[str, Any]:
    x = [float(row["k1_ghz_per_v"]) for row in rows]
    y = [float(row[name]) / 1.0e9 for row in rows]
    pn = [float(row["pn_spec_dbc_hz"]) for row in rows]
    fit = _linear_fit(y, pn)
    return {
        "axis": name,
        "unit": "GHz/V",
        "value_range": _range(y),
        "k1_monotonic_increasing": _monotonic(y, "increasing"),
        "unique_value_count": len(set(y)),
        "point_count": len(y),
        "pn_spec_linear_fit": fit,
        "boundary_systemtb_all_pass": all(row["system_boundary_passed"] for row in rows),
        "boundary_blocktb_all_pass": all(row["block_tb_passed"] for row in rows),
        "context_all_covered": all(row["context_covered"] for row in rows),
    }


def run(source_dir: str | Path = DEFAULT_SOURCE, output_dir: str | Path = DEFAULT_OUTPUT) -> Dict[str, Any]:
    source = Path(source_dir).resolve()
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    continuity_summary = read_json(source / "continuity_validation_summary.json")
    rows = _boundary_rows(source)
    if len(rows) != 17:
        raise ValueError(f"expected 17 mapped/off-grid boundary rows, got {len(rows)}")

    axis_names = (
        "kvco_operating_hz_per_v",
        "kvco_min_hz_per_v",
        "kvco_max_hz_per_v",
    )
    analyses = {name: _axis_analysis(rows, name) for name in axis_names}
    # A block contract must be based on a BlockTB-measured quantity.  The
    # operating-point value is retained as system evidence, but min/max are the
    # currently available frozen-context BlockTB quantities.
    selected_axis = "kvco_max_hz_per_v"
    decision = {
        "status": "axis_qualified_for_joint_contract_design_pending_margin",
        "selected_primary_block_axis": selected_axis,
        "selected_primary_block_axis_unit": "Hz/V",
        "selected_axis_semantics": (
            "maximum measured Kvco over the frozen VCOBlockContext"
        ),
        "supporting_system_axis": "kvco_operating_hz_per_v",
        "supporting_axis_semantics": (
            "SystemTB operating-point Kvco used by the loop model; retained as "
            "coupling evidence, not yet as an independent BlockSpec metric"
        ),
        "selection_reason": [
            "kvco_max is directly present in the frozen-context BlockTB behavior vector",
            "kvco_max is strictly increasing over all 17 boundary and off-grid rows",
            "the same axis is defined for both mapped and off-grid boundary measurements",
            "using a worst-context maximum preserves the V1.0 measured-behavior contract pattern",
        ],
        "not_selected_reasons": {
            "kvco_operating_hz_per_v": (
                "strong system coupling evidence, but currently a SystemTB operating-point metric"
            ),
            "kvco_min_hz_per_v": (
                "valid auxiliary coverage metric, but its minimum is less directly tied to the observed lock boundary"
            ),
        },
        "checks": {
            "selected_axis_monotonic": analyses[selected_axis]["k1_monotonic_increasing"],
            "selected_axis_unique_on_all_rows": analyses[selected_axis]["unique_value_count"] == len(rows),
            "selected_axis_all_boundary_systemtb_pass": analyses[selected_axis]["boundary_systemtb_all_pass"],
            "selected_axis_all_boundary_blocktb_pass": analyses[selected_axis]["boundary_blocktb_all_pass"],
            "selected_axis_all_context_covered": analyses[selected_axis]["context_all_covered"],
            "all_three_axes_monotonic": all(
                analyses[name]["k1_monotonic_increasing"] for name in axis_names
            ),
        },
        "qualification_scope": (
            "17 deterministic boundary observations in one frozen synthetic behavioral context; "
            "no Kvco engineering margin, joint allocation, PVT coverage, or transistor-level signoff"
        ),
    }
    rows_json = {
        "schema_version": "v1.5-measured-kvco-mapping-1.0",
        "status": "measured_behavior_axis_qualification",
        "source": {
            "frozen_contracts": "frozen_conditional_contracts.json",
            "offgrid_boundaries": "offgrid_boundary_allocations.json",
            "frozen_contracts_file_sha256": file_sha256(
                source / "frozen_conditional_contracts.json"
            ),
            "offgrid_boundaries_file_sha256": file_sha256(
                source / "offgrid_boundary_allocations.json"
            ),
            "continuity_summary_sha256": continuity_summary["summary_sha256"],
        },
        "row_count": len(rows),
        "rows": rows,
        "axis_analysis": analyses,
        "claim_boundary": (
            "This artifact qualifies a candidate measured Kvco axis for a future "
            "joint PN-Kvco contract. It does not allocate a Kvco requirement."
        ),
    }
    rows_json["mapping_sha256"] = evidence_digest(rows_json)
    write_evidence_json(rows_json, output / "measured_kvco_mapping.json")
    write_csv(rows, output / "measured_kvco_mapping.csv")
    decision["source_mapping_sha256"] = rows_json["mapping_sha256"]
    decision["decision_sha256"] = evidence_digest(decision)
    write_evidence_json(decision, output / "joint_contract_axis_decision.json")

    optional_plot_artifact = "k1_to_measured_kvco.png"
    try:
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), constrained_layout=True)
        x = [row["k1_ghz_per_v"] for row in rows]
        axes[0].plot(x, [row["kvco_operating_hz_per_v"] / 1e9 for row in rows], "o-", label="SystemTB operating Kvco")
        axes[0].plot(x, [row["kvco_min_hz_per_v"] / 1e9 for row in rows], "s--", label="BlockTB Kvco min")
        axes[0].plot(x, [row["kvco_max_hz_per_v"] / 1e9 for row in rows], "^--", label="BlockTB Kvco max")
        axes[0].set_xlabel("k1 (GHz/V)")
        axes[0].set_ylabel("Kvco (GHz/V)")
        axes[0].set_title("k1 to measured Kvco")
        axes[0].grid(True, alpha=0.3)
        axes[0].legend(fontsize=8)
        axes[1].plot([row["kvco_max_hz_per_v"] / 1e9 for row in rows], [row["pn_spec_dbc_hz"] for row in rows], "o")
        axes[1].set_xlabel("BlockTB Kvco max (GHz/V)")
        axes[1].set_ylabel("PN_spec (dBc/Hz)")
        axes[1].set_title("Candidate joint-contract projection")
        axes[1].grid(True, alpha=0.3)
        fig.savefig(output / optional_plot_artifact, dpi=160)
        plt.close(fig)
    except Exception:
        pass

    report = {
        "schema_version": "v1.5-measured-kvco-report-1.0",
        "status": "measured_kvco_axis_qualified_pending_joint_allocation",
        "mapping_sha256": rows_json["mapping_sha256"],
        "decision_sha256": decision["decision_sha256"],
        "row_count": len(rows),
        "selected_axis": selected_axis,
        "selected_axis_range_ghz_per_v": analyses[selected_axis]["value_range"],
        "selected_axis_fit": analyses[selected_axis]["pn_spec_linear_fit"],
        "all_three_axes_monotonic": decision["checks"]["all_three_axes_monotonic"],
        "joint_contract_allocation_started": False,
        "optional_plot_artifact": optional_plot_artifact,
        "plot_is_excluded_from_scientific_evidence": True,
        "next_step": (
            "define and validate a Kvco window/margin policy, then generate joint "
            "PN-Kvco candidate contracts and replay boundary-adjacent candidates"
        ),
    }
    report["report_sha256"] = evidence_digest(report)
    write_evidence_json(report, output / "measured_kvco_report.json")
    (output / "measured_kvco_report.md").write_text(
        "\n".join(
            [
                "# V1.5 measured Kvco axis qualification",
                "",
                f"- Boundary and off-grid rows: `{len(rows)}`",
                f"- Selected BlockTB axis: `{selected_axis}`",
                f"- Selected axis range: `{analyses[selected_axis]['value_range']['min']:.6f}` to `{analyses[selected_axis]['value_range']['max']:.6f} GHz/V`",
                f"- Selected axis monotonic with k1: `{analyses[selected_axis]['k1_monotonic_increasing']}`",
                f"- PN_spec fit R² against selected axis: `{analyses[selected_axis]['pn_spec_linear_fit']['r2']:.12f}`",
                f"- PN_spec fit maximum residual: `{analyses[selected_axis]['pn_spec_linear_fit']['max_abs_residual']:.9f} dB`",
                "- Kvco margin policy: `pending`",
                "- Joint PN–Kvco allocation: `not started`",
                "",
                "The selected axis is the BlockTB measured maximum Kvco over the frozen context. The SystemTB operating-point Kvco remains supporting coupling evidence.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", default=str(DEFAULT_SOURCE))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    result = run(args.source_dir, args.output_dir)
    print("Rows:", result["row_count"])
    print("Selected axis:", result["selected_axis"])
    print("Selected axis monotonic:", result["all_three_axes_monotonic"])
    print("Joint allocation started:", result["joint_contract_allocation_started"])
    print("Artifacts:", Path(args.output_dir).resolve())


if __name__ == "__main__":
    main()
