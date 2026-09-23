"""Promote the provisional V1.5 PN--Kvco rule to a formal 2-D BlockSpec.

The canonical nine conditional PN rows remain the source of the mapping.  A
formal measured-behavior contract is built only after the continuity and
boundary-adjacent holdouts have passed:

    kvco_lower <= measured kvco_max <= kvco_upper
    measured worst PN <= piecewise PN_spec(measured kvco_max)

Kvco engineering margin is explicit and deterministic: one canonical k1 grid
step (50 MHz/V) is removed from each end of the measured 1.49--1.89 GHz/V
domain, producing a required 1.54--1.84 GHz/V interior window.  This is an
engineering allocation rule for this frozen synthetic context, not a PVT or
transistor-level signoff claim.
"""

from __future__ import annotations

import argparse
import csv
import json
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

from v1.allocation.design_space import DesignPointDefinition, DesignSpaceDefinition
from v1.allocation.multidim_evaluator import evaluate_design_point
from v1.api.verification import VerificationRequest
from v1.backends.synthetic import SyntheticVCOConstraintBackend
from v1.model.pll_behavioral import VCOParams
from v1.pipeline import build_vco_instance
from v1.specs import SystemSpec, load_case
from v1.verification.service import verify_block_assignment

from run_v1_5_joint_contract import _interpolate, _known_contract_rows


ROOT = Path(__file__).resolve().parent
DEFAULT_CASE = ROOT / "v1" / "cases" / "vco_multidim_01.json"
DEFAULT_SOURCE = ROOT / "results" / "v1_5_kvco_mapping_v1_5"
DEFAULT_HOLDOUT = ROOT / "results" / "v1_5_joint_boundary_validation_v1_5"
DEFAULT_OUTPUT = ROOT / "results" / "v1_5_formal_joint_blockspec_v1_5"


def _digest(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False)
    return sha256(payload.encode("utf-8")).hexdigest()


def _write_json(value: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True),
                    encoding="utf-8")


def _formal_constraints(
    *,
    pn_limit: float,
    kvco_lower: float,
    kvco_upper: float,
    power_limit: float,
) -> list[Dict[str, Any]]:
    # These are measured behavior constraints.  The PN relation is resolved
    # separately for each candidate from its measured kvco_max value.
    return [
        {
            "constraint_id": "target_frequency_covered",
            "kind": "coverage",
            "measured_metrics": ["frequency_min_hz", "frequency_max_hz"],
            "target_ref": "system_spec.target_frequency_hz",
            "tolerance_ref": "system_spec.limits.output_frequency_tolerance_hz",
        },
        {
            "constraint_id": "positive_kvco",
            "kind": "lower_bound",
            "measured_metric": "kvco_min_hz_per_v",
            "operator": ">",
            "limit": 0.0,
        },
        {
            "constraint_id": "kvco_max_lower_window",
            "kind": "lower_bound",
            "measured_metric": "kvco_max_hz_per_v",
            "operator": ">=",
            "limit": kvco_lower,
        },
        {
            "constraint_id": "kvco_max_upper_window",
            "kind": "upper_bound",
            "measured_metric": "kvco_max_hz_per_v",
            "operator": "<=",
            "limit": kvco_upper,
        },
        {
            "constraint_id": "phase_noise_1mhz",
            "kind": "upper_bound",
            "measured_metric": "worst_phase_noise_1mhz_dbc_hz",
            "operator": "<=",
            "limit": pn_limit,
        },
        {
            "constraint_id": "worst_power",
            "kind": "upper_bound",
            "measured_metric": "worst_power_w",
            "operator": "<=",
            "limit": power_limit,
        },
        {
            "constraint_id": "finite_behavior_vector",
            "kind": "validity",
            "required": True,
        },
    ]


def _evaluate_formal_candidate(
    *,
    case: Mapping[str, Any],
    system_spec: SystemSpec,
    base_vco: VCOParams,
    design_space: DesignSpaceDefinition,
    rows: Sequence[Mapping[str, float]],
    kvco_lower: float,
    kvco_upper: float,
    candidate_id: str,
    candidate_class: str,
    k1_hz_per_v: float,
    pn_anchor_dbc_hz: float,
    power_limit: float,
) -> Dict[str, Any]:
    values = {
        "pn_anchor_1mhz_dbc_hz": float(pn_anchor_dbc_hz),
        "k1_hz_per_v": float(k1_hz_per_v),
    }
    point = DesignPointDefinition(
        point_id=design_space.point_id(values), ordinal=-1, values=values
    )
    evaluated = evaluate_design_point(case, system_spec, base_vco, point)
    behavior = evaluated["behavior_vector"]
    measured_kvco = float(behavior["kvco_max_hz_per_v"])
    measured_pn = float(behavior["worst_phase_noise_1mhz_dbc_hz"])
    pn_spec = _interpolate(rows, measured_kvco)
    window_pass = kvco_lower <= measured_kvco <= kvco_upper
    pn_pass = pn_spec is not None and measured_pn <= pn_spec
    contract_pass = window_pass and pn_pass
    constraints = _formal_constraints(
        pn_limit=float(pn_spec if pn_spec is not None else measured_pn - 1.0),
        kvco_lower=kvco_lower,
        kvco_upper=kvco_upper,
        power_limit=power_limit,
    )
    formal_spec = {"constraints": constraints, "margin_db": 1.5,
                   "contract_type": "formal_measured_pn_by_measured_kvco_max"}
    realized = VCOParams(**dict(evaluated["realized_instance"]["parameters"]))
    verification = verify_block_assignment(
        VerificationRequest(
            system_spec=system_spec,
            block_spec=formal_spec,
            realized_instance=realized,
            operating_context=dict(case["block_context"]),
            block_id="VCO",
            backend_id="synthetic_vco_v1_constraint_set",
            request_id=f"{case['case_id']}:formal-joint:{candidate_id}",
            keep_raw=False,
        ),
        backend=SyntheticVCOConstraintBackend(case),
    )
    replay_identical = (
        verification["system_tb"]["metrics"] == evaluated["system_tb"]["metrics"]
        and verification["system_tb"]["checks"] == evaluated["system_tb"]["checks"]
        and verification["system_tb"]["residuals"] == evaluated["system_tb"]["residuals"]
    )
    return {
        "candidate_id": candidate_id,
        "candidate_class": candidate_class,
        "design_vector": values,
        "point_id": evaluated["point_id"],
        "measured_behavior": dict(behavior),
        "system_metrics": dict(evaluated["system_tb"]["metrics"]),
        "system_checks": dict(evaluated["system_tb"]["checks"]),
        "formal_contract_prediction": {
            "kvco_window_hz_per_v": [kvco_lower, kvco_upper],
            "measured_kvco_max_hz_per_v": measured_kvco,
            "predicted_pn_spec_dbc_hz": pn_spec,
            "measured_pn_dbc_hz": measured_pn,
            "kvco_window_pass": window_pass,
            "pn_relation_pass": pn_pass,
            "formal_joint_blockspec_pass": contract_pass,
        },
        "verification": {
            "blocktb_passed": bool(verification["block_tb"]["passed"]),
            "systemtb_passed": bool(verification["system_tb"]["passed"]),
            "context_covered": bool(verification["context_coverage"]["passed"]),
            "same_instance_used": bool(verification["provenance"]["realized_instance_shared_by_block_and_system_tb"]),
            "systemtb_replay_identical": replay_identical,
            "blocktb_checks": dict(verification["block_tb"]["checks"]),
            "blocktb_residuals": dict(verification["block_tb"]["residuals"]),
        },
    }


def _probe_offset(
    case: Mapping[str, Any], system_spec: SystemSpec, base_vco: VCOParams,
    design_space: DesignSpaceDefinition, k1: float, probe_anchor: float,
) -> tuple[float, float]:
    values = {"pn_anchor_1mhz_dbc_hz": probe_anchor, "k1_hz_per_v": k1}
    point = DesignPointDefinition(point_id=design_space.point_id(values), ordinal=-1, values=values)
    evaluated = evaluate_design_point(case, system_spec, base_vco, point)
    behavior = evaluated["behavior_vector"]
    return float(behavior["worst_phase_noise_1mhz_dbc_hz"]), float(behavior["kvco_max_hz_per_v"])


def run(
    case_path: str | Path = DEFAULT_CASE,
    source_dir: str | Path = DEFAULT_SOURCE,
    holdout_dir: str | Path = DEFAULT_HOLDOUT,
    output_dir: str | Path = DEFAULT_OUTPUT,
) -> Dict[str, Any]:
    case = load_case(case_path)
    source = Path(source_dir).resolve()
    holdout = Path(holdout_dir).resolve()
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    rows = _known_contract_rows(source)
    if len(rows) != 9:
        raise ValueError(f"expected nine canonical rows, got {len(rows)}")
    holdout_artifact = json.loads((holdout / "joint_boundary_validation.json").read_text(encoding="utf-8"))
    holdout_validation = holdout_artifact["validation"]
    required_holdout_checks = (
        holdout_validation["inside_joint_contract_all_pass"],
        holdout_validation["inside_blocktb_all_pass"],
        holdout_validation["inside_systemtb_all_pass"],
        holdout_validation["inside_false_positive_count"] == 0,
        holdout_validation["all_independent_systemtb_replays_identical"],
    )
    if not all(required_holdout_checks):
        raise ValueError("cannot promote joint contract: boundary holdout did not pass")

    system_spec = SystemSpec.from_dict(case["system_spec"])
    base_vco = build_vco_instance(VCOParams(), case.get("base_vco", {}))
    design_space = DesignSpaceDefinition.from_dict(case["design_space"])
    power_limit = float(case["system_spec"]["limits"]["power_max_w"])
    observed_lower = float(rows[0]["kvco_max_hz_per_v"])
    observed_upper = float(rows[-1]["kvco_max_hz_per_v"])
    # The design-space k1 step is 50 MHz/V and the measured kvco_max mapping
    # changes by exactly 50 MHz/V per canonical step in this frozen model.
    k1_step = float(case["design_space"]["axes"][1]["step"])
    kvco_margin = k1_step
    kvco_lower = observed_lower + kvco_margin
    kvco_upper = observed_upper - kvco_margin
    formal_rows = [row for row in rows if kvco_lower <= row["kvco_max_hz_per_v"] <= kvco_upper]
    if len(formal_rows) != 7:
        raise ValueError(f"expected seven interior relation rows, got {len(formal_rows)}")

    # Use unseen off-grid slices plus canonical interior endpoints.  A probe
    # determines the deterministic PN-anchor-to-measured-PN offset; candidates
    # are then placed 0.10 dB inside/outside the predicted formal relation.
    k1_inside = [700e6, 725e6, 775e6, 825e6, 875e6, 925e6, 975e6, 1_000e6]
    entries: list[Dict[str, Any]] = []
    probe_anchor = -121.0
    for index, k1 in enumerate(k1_inside):
        probe_pn, measured_kvco = _probe_offset(case, system_spec, base_vco, design_space, k1, probe_anchor)
        pn_spec = _interpolate(rows, measured_kvco)
        if pn_spec is None:
            raise ValueError(f"formal k1={k1} is outside PN relation support")
        target_anchor = pn_spec - (probe_pn - probe_anchor)
        inside = _evaluate_formal_candidate(
            case=case, system_spec=system_spec, base_vco=base_vco,
            design_space=design_space, rows=rows,
            kvco_lower=kvco_lower, kvco_upper=kvco_upper,
            candidate_id=f"formal_inside_{index:02d}",
            candidate_class="formal_contract_inside",
            k1_hz_per_v=k1, pn_anchor_dbc_hz=target_anchor - 0.10,
            power_limit=power_limit,
        )
        outside = _evaluate_formal_candidate(
            case=case, system_spec=system_spec, base_vco=base_vco,
            design_space=design_space, rows=rows,
            kvco_lower=kvco_lower, kvco_upper=kvco_upper,
            candidate_id=f"formal_outside_{index:02d}",
            candidate_class="formal_contract_pn_outside",
            k1_hz_per_v=k1, pn_anchor_dbc_hz=target_anchor + 0.10,
            power_limit=power_limit,
        )
        entries.extend([inside, outside])

    for candidate_id, candidate_class, k1, pn in [
        ("formal_kvco_below", "formal_contract_kvco_below", 675e6, -124.0),
        ("formal_kvco_above", "formal_contract_kvco_above", 1_025e6, -124.0),
    ]:
        entries.append(_evaluate_formal_candidate(
            case=case, system_spec=system_spec, base_vco=base_vco,
            design_space=design_space, rows=rows,
            kvco_lower=kvco_lower, kvco_upper=kvco_upper,
            candidate_id=candidate_id, candidate_class=candidate_class,
            k1_hz_per_v=k1, pn_anchor_dbc_hz=pn, power_limit=power_limit,
        ))

    inside = [e for e in entries if e["candidate_class"] == "formal_contract_inside"]
    pn_outside = [e for e in entries if e["candidate_class"] == "formal_contract_pn_outside"]
    kvco_outside = [e for e in entries if e["candidate_class"].startswith("formal_contract_kvco_")]
    validation = {
        "inside_count": len(inside),
        "inside_contract_all_pass": all(e["formal_contract_prediction"]["formal_joint_blockspec_pass"] for e in inside),
        "inside_blocktb_all_pass": all(e["verification"]["blocktb_passed"] for e in inside),
        "inside_systemtb_all_pass": all(e["verification"]["systemtb_passed"] for e in inside),
        "inside_false_positive_count": sum(
            e["formal_contract_prediction"]["formal_joint_blockspec_pass"] and not e["verification"]["systemtb_passed"] for e in inside
        ),
        "pn_outside_rejected_by_contract": all(not e["formal_contract_prediction"]["formal_joint_blockspec_pass"] for e in pn_outside),
        "pn_outside_rejected_by_blocktb": all(not e["verification"]["blocktb_passed"] for e in pn_outside),
        "kvco_outside_rejected_by_contract": all(not e["formal_contract_prediction"]["formal_joint_blockspec_pass"] for e in kvco_outside),
        "kvco_outside_rejected_by_blocktb": all(not e["verification"]["blocktb_passed"] for e in kvco_outside),
        "all_systemtb_replays_identical": all(e["verification"]["systemtb_replay_identical"] for e in entries),
    }
    checks = {
        "provisional_holdout_passed": all(required_holdout_checks),
        "kvco_margin_positive": kvco_margin > 0.0,
        "formal_window_is_strict_interior": observed_lower < kvco_lower < kvco_upper < observed_upper,
        "formal_relation_rows_cover_window": len(formal_rows) == 7,
        "inside_joint_contract_implies_blocktb": validation["inside_contract_all_pass"] and validation["inside_blocktb_all_pass"],
        "inside_joint_contract_implies_systemtb": validation["inside_contract_all_pass"] and validation["inside_systemtb_all_pass"],
        "no_inside_false_positive": validation["inside_false_positive_count"] == 0,
        "independent_replay_closed": validation["all_systemtb_replays_identical"],
    }
    if not all(checks.values()):
        raise ValueError(f"formal joint BlockSpec validation failed: {[k for k,v in checks.items() if not v]}")

    contract = {
        "schema_version": "v1.5-formal-2d-joint-blockspec-1.0",
        "status": "formal_2d_blockspec_allocated_and_validated",
        "case_id": str(case["case_id"]),
        "block_id": "VCO",
        "contract_type": "measured_pn_by_measured_kvco_max_joint",
        "independent_variables": ["pn_anchor_1mhz_dbc_hz", "k1_hz_per_v"],
        "measured_behavior_axis": "kvco_max_hz_per_v",
        "required_measured_kvco_window": {
            "metric": "kvco_max_hz_per_v",
            "operator": "inclusive_window",
            "lower_hz_per_v": kvco_lower,
            "upper_hz_per_v": kvco_upper,
            "lower_ghz_per_v": kvco_lower / 1e9,
            "upper_ghz_per_v": kvco_upper / 1e9,
            "observed_boundary_domain_hz_per_v": [observed_lower, observed_upper],
            "engineering_margin": {
                "type": "one_canonical_k1_step_each_side",
                "value_hz_per_v": kvco_margin,
                "source_axis": "k1_hz_per_v",
                "source_step_hz_per_v": k1_step,
                "data_derived": False,
                "policy_source": "explicit conservative allocation choice; magnitude uses the canonical grid step",
                "physical_uncertainty_calibrated": False,
                "policy": "shrink_each_end of measured feasible Kvco domain by one canonical grid increment",
            },
        },
        "pn_requirement": {
            "metric": "worst_phase_noise_1mhz_dbc_hz",
            "requirement_metric": "phase_noise_1mhz_max_dbc_hz",
            "operator": "<=",
            "form": "piecewise_linear_promoted_after_offgrid_and_boundary_holdout",
            "engineering_margin_db": 1.5,
            "source_rows": formal_rows,
            "support_rows": rows,
            "domain_hz_per_v": [kvco_lower, kvco_upper],
        },
        "joint_rule": {
            "operator": "AND",
            "conditions": [
                {
                    "metric": "kvco_max_hz_per_v",
                    "operator": ">=",
                    "limit": kvco_lower,
                },
                {
                    "metric": "kvco_max_hz_per_v",
                    "operator": "<=",
                    "limit": kvco_upper,
                },
                {
                    "metric": "worst_phase_noise_1mhz_dbc_hz",
                    "operator": "<=",
                    "limit_function": "piecewise_linear(pn_spec_by_kvco_max)",
                },
            ],
            "pn_spec_by_kvco_max": [
                {
                    "kvco_max_hz_per_v": float(row["kvco_max_hz_per_v"]),
                    "kvco_max_ghz_per_v": float(row["kvco_max_ghz_per_v"]),
                    "pn_spec_dbc_hz": float(row["pn_spec_dbc_hz"]),
                    "source_k1_hz_per_v": float(row["k1_hz_per_v"]),
                    "source_boundary_measured_pn_dbc_hz": float(
                        row["boundary_measured_pn_dbc_hz"]
                    ),
                    "pn_margin_db": 1.5,
                }
                for row in formal_rows
            ],
            "interpolation": {
                "method": "piecewise_linear",
                "domain_hz_per_v": [kvco_lower, kvco_upper],
                "promoted_after_holdout": True,
            },
        },
        "formal_block_spec": {
            "requirements": [
                "1.54 <= measured kvco_max_GHz_per_V <= 1.84",
                "measured worst PN <= PN_spec(measured kvco_max)",
                "target frequency coverage, positive kvco and power constraints pass",
            ],
            "margin_db": 1.5,
            "measurement_context_ref": "VCOBlockContext.v1_5",
            "context_frozen": True,
        },
        "allocation_provenance": {
            "v1_0_reference": "PN boundary -> frozen-context BlockTB -> 1.5 dB margin -> BlockSpec",
            "v1_5_extension": "measured Kvco window + PN_spec(measured Kvco) joint contract",
            "source_provisional_contract": str(source / "../v1_5_joint_contract_v1_5" / "provisional_joint_contract.json"),
            "source_holdout": str(holdout / "joint_boundary_validation.json"),
        },
        "validation": {"checks": checks, "candidate_validation": validation},
        "claim_boundary": (
            "Formal behavior-level 2-D sufficient-condition BlockSpec for the frozen "
            "synthetic VCO context. The contract is not claimed necessary, PVT-robust, "
            "or transistor-level signoff."
        ),
    }
    contract["contract_sha256"] = _digest(contract)
    _write_json(contract, output / "formal_2d_blockspec.json")
    _write_json({
        "schema_version": "v1.5-formal-2d-blockspec-candidate-validation-1.0",
        "status": "formal_2d_blockspec_candidate_validation_passed",
        "source_contract_sha256": contract["contract_sha256"],
        "entries": entries,
        "validation": validation,
    }, output / "formal_2d_blockspec_candidate_validation.json")
    with (output / "formal_2d_blockspec_candidate_validation.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = ["candidate_id", "candidate_class", "k1_ghz_per_v", "pn_anchor_1mhz_dbc_hz", "measured_kvco_max_ghz_per_v", "predicted_pn_spec_dbc_hz", "measured_pn_dbc_hz", "formal_joint_blockspec_pass", "blocktb_passed", "systemtb_passed", "systemtb_replay_identical"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in entries:
            pred, ver = item["formal_contract_prediction"], item["verification"]
            writer.writerow({
                "candidate_id": item["candidate_id"], "candidate_class": item["candidate_class"],
                "k1_ghz_per_v": item["design_vector"]["k1_hz_per_v"] / 1e9,
                "pn_anchor_1mhz_dbc_hz": item["design_vector"]["pn_anchor_1mhz_dbc_hz"],
                "measured_kvco_max_ghz_per_v": pred["measured_kvco_max_hz_per_v"] / 1e9,
                "predicted_pn_spec_dbc_hz": pred["predicted_pn_spec_dbc_hz"],
                "measured_pn_dbc_hz": pred["measured_pn_dbc_hz"],
                "formal_joint_blockspec_pass": pred["formal_joint_blockspec_pass"],
                "blocktb_passed": ver["blocktb_passed"], "systemtb_passed": ver["systemtb_passed"],
                "systemtb_replay_identical": ver["systemtb_replay_identical"],
            })
    report = [
        "# V1.5 formal 2-D PN–Kvco BlockSpec",
        "",
        "The provisional relation is promoted after the off-grid boundary holdout passed.",
        "",
        f"- Formal measured Kvco window: `{kvco_lower/1e9:.3f}`–`{kvco_upper/1e9:.3f} GHz/V`",
        f"- Kvco engineering margin: `{kvco_margin/1e6:.1f} MHz/V` per side",
        "- Kvco margin is a chosen grid-based guard band, not an inferred physical uncertainty bound.",
        "- PN engineering margin: `1.5 dB`",
        f"- PN relation rows inside formal window: `{len(formal_rows)}`",
        f"- Inside candidates: `{validation['inside_count']}`; BlockTB all PASS: `{validation['inside_blocktb_all_pass']}`; SystemTB all PASS: `{validation['inside_systemtb_all_pass']}`",
        f"- Inside false positives: `{validation['inside_false_positive_count']}`",
        f"- PN-outside candidates rejected by BlockTB: `{validation['pn_outside_rejected_by_blocktb']}`",
        f"- Kvco-outside candidates rejected by BlockTB: `{validation['kvco_outside_rejected_by_blocktb']}`",
        f"- Independent replay identical: `{validation['all_systemtb_replays_identical']}`",
        "",
        "This is a formal behavior-level sufficient-condition BlockSpec in the frozen synthetic context. Necessity, PVT robustness and transistor-level signoff remain outside the claim.",
    ]
    (output / "formal_2d_blockspec_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return contract


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default=str(DEFAULT_CASE))
    parser.add_argument("--source-dir", default=str(DEFAULT_SOURCE))
    parser.add_argument("--holdout-dir", default=str(DEFAULT_HOLDOUT))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    result = run(args.case, args.source_dir, args.holdout_dir, args.output_dir)
    print("Status:", result["status"])
    print("Formal Kvco window (GHz/V):", result["required_measured_kvco_window"]["lower_ghz_per_v"], "to", result["required_measured_kvco_window"]["upper_ghz_per_v"])
    print("Contract SHA-256:", result["contract_sha256"])
    print("Artifacts:", Path(args.output_dir).resolve())


if __name__ == "__main__":
    main()
