"""Deterministic feedback rules promoted from the V2 experiment; tools compute parameters.

Rules are hypotheses about this supported ideal PLL, not dynamic theorems.
The controller owns native measurement verdicts and all execution budgets.
"""
from pathlib import Path
import json

from .physics_tool_policy import SCHEMA_VERSION, DeterministicToolPolicy


RULES = {
    "capture_fail": "VCO_TUNING_EXPLORATION / LOW_VOLTAGE; target upper-quarter BW if BW was not failing",
    "bw_fail": "Target midpoint scaled by measured M1/M2 BW ratio; clip to [0.1,0.9] target fraction; local hypothesis only",
    "unknown": "REVERIFY only if actual supported measurement is UNKNOWN or execution unresolved",
    "finish": "STOP after actual feedback construction has a formal M1 feasible best; outer controller owns M2 selection and verdict",
    "seed_count": 1,
}


class DeterministicFeedbackPolicy(DeterministicToolPolicy):
    def decide(self, state, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=False)
        feedback = state["external_feedback"]["observations"][0]
        measured = feedback["measurements"]
        for name, value in (("actual_feedback.json", feedback), ("predeclared_rules.json", RULES)):
            (directory / name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        common = {"schema_version": SCHEMA_VERSION, "state_sha256": state["state_sha256"],
                  "evidence_ids": [feedback["evidence_id"]]}
        failed = set(measured["failed_constraints"])
        if not failed and (measured["supported_metrics_status"] == "UNKNOWN" or measured["execution_status"] != "COMPLETED"):
            return common | {"action": "REVERIFY", "reason": "Actual supported M2 measurement is unresolved; one unchanged-protocol retry may resolve numerical uncertainty."}
        if state["history"]:
            best = state["best_known"]
            if best and best["m1_feasibility"] == "FEASIBLE":
                return common | {"action": "STOP", "stop_basis": "SPEC_SATISFIED", "evidence_ids": [feedback["evidence_id"], best["evidence_id"]],
                                 "reason": "Formal M1 feasible point is available after feedback construction. Outer controller independently audits a distinct candidate and owns native M2 verdict."}
            return super().decide(state, directory)
        specs = {s["metric"]: s for s in state["problem"]["specs"]}
        bw_spec = specs["BW_Hz"]
        fraction = 0.75 if "lock_time_s" in failed else 0.5
        deviation = measured["m1_m2_deviation"]["BW_Hz"]
        if "BW_Hz" in failed and deviation["M2_measurement"] and deviation["M1_prediction"]:
            lo, hi = bw_spec["min"], bw_spec["max"]
            target = ((lo + hi) / 2) * deviation["M1_prediction"] / deviation["M2_measurement"]
            fraction = min(0.9, max(0.1, (target - lo) / (hi - lo)))
        capture = "lock_time_s" in failed
        reason = ("Measured failures=" + ",".join(sorted(failed)) + "; "
                  "use native BW offset as a local target correction; explore a lower tuning voltage for conditional capture. "
                  "M1 cannot certify capture; all new parameters require tools and native reverification.")
        return common | {"action": "BUILD_PHYSICS_REGION", "reason": reason,
            "request": {"schema_version": "pll-physics-region-request-1.0", "request_id": "DET_FEEDBACK:"+str(state["round"]),
                "problem_sha256": state["problem"]["problem_sha256"], "model_fingerprint": state["model"]["model_sha256"],
                "strategy": "VCO_TUNING_EXPLORATION" if capture else "BW_TARGETED_INVERSE",
                "target_bw_fraction": [fraction, fraction],
                "physics_focus": ["LOOP_GAIN", "GAIN_SPLIT", "TUNING"] if capture else ["LOOP_GAIN", "LF_SHAPE"],
                "tuning_preference": "LOW_VOLTAGE" if capture else "INTERIOR", "seed_count": 1,
                "region_width_policy": "BALANCED", "budget": {"construction_attempts": state["budget"]["max_build_attempts"], "m1_calls": 1},
                "evidence_ids": [feedback["evidence_id"]]}}
