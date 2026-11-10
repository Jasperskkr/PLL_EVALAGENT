from __future__ import annotations

import math
from ..physics.cp import equilibrium_timing, signed_charge
from ..physics.lf import operators
from ..schemas import limits

MODEL_ID = "signed_charge_exact_ideal_rc_linear_vco_v1"


def measure_cycles(rows, request):
    """Full-window lock test, independent of the stricter static phase spec."""
    m = request["measurement"]
    n = round(m["duration_s"]*request["operating_context"]["fref_Hz"])
    if len(rows) != n or not all(math.isfinite(v) for r in rows for v in r.values()):
        return {"lock_status": "UNKNOWN", "reason": "INCOMPLETE_OR_NONFINITE_WINDOW"}
    inside = [abs(r["phase_deg"]) < m["lock_phase_deg"] and
              abs(r["frequency_error_ppm"]) < m["lock_frequency_ppm"] for r in rows]
    hold = m["lock_hold_cycles"]
    first = next((k for k in range(n-hold+1) if all(inside[k:k+hold])), None)
    tail = rows[-m["tail_cycles"]:]
    no_tail_slip = len({r["phase_wrap_index"] for r in tail}) == 1
    locked = first is not None and all(inside[-m["tail_cycles"]:]) and no_tail_slip
    return {"mean_phase_abs_deg": abs(sum(r["phase_deg"] for r in tail)/len(tail)),
            "signed_mean_phase_deg": sum(r["phase_deg"] for r in tail)/len(tail),
            "phase_absmax_deg": max(abs(r["phase_deg"]) for r in tail),
            "tail_max_abs_frequency_error_ppm": max(abs(r["frequency_error_ppm"]) for r in tail),
            "lock_status": "LOCKED" if locked else "NOT_LOCKED",
            "lock_time_s": rows[first]["time_s"] if first is not None else None,
            "tail_complete_cycles": len(tail), "tail_has_cycle_slip": not no_tail_slip,
            "vctrl_tail_ripple_V": max(r["vctrl_max_V"] for r in tail)-min(r["vctrl_min_V"] for r in tail)}


class PythonBehavioralEvaluator:
    def __init__(self, request, vco):
        self.request = request
        self.vco = vco

    def evaluate(self, joint_spec, context=None):
        try:
            return self._evaluate(joint_spec, context)
        except (OverflowError, ZeroDivisionError, ValueError) as error:
            return {"model_id": MODEL_ID, "behavioral_model_verdict": "UNKNOWN",
                    "model_domain_verdict": "UNKNOWN", "numeric_domain_status": "NUMERICAL_FAILURE",
                    "empirical_cp_trajectory_domain": "UNKNOWN", "constraint_margins": {},
                    "metrics": {"mean_phase_abs_deg": None, "signed_mean_phase_deg": None,
                                "tail_max_abs_frequency_error_ppm": None, "lock_status": "UNKNOWN"},
                    "units": {"mean_phase_abs_deg": "deg", "tail_max_abs_frequency_error_ppm": "ppm"},
                    "measurement_windows": self.request["measurement"],
                    "equilibrium_prediction": {"phase_deg": None, "vctrl_V": None},
                    "validity": {"reason": "NUMERICAL_FAILURE", "detail": str(error)},
                    "runtime_cost": {"behavioral_evaluations": 1, "external_simulator_calls": 0},
                    "independent_system_qualified_verdict": "UNKNOWN", "cycles": []}

    def _evaluate(self, joint_spec, context=None):
        target = joint_spec
        p, v = self.request, self.vco
        c = context or p["operating_context"]
        period = 1/c["fref_Hz"]
        veq = v["V0_V"]+(c["fout_target_Hz"]-v["f0_Hz"])/v["Kvco_Hz_per_V"]
        c1 = target["C1_F"]+target["Cload_F"]
        transition, integral = operators(target["Rz_Ohm"], c1, target["C2_F"], period)
        e = p["initialization"]["feedback_error_cycles"]
        x = p["initialization"]["Vctrl_V"]-veq
        y = p["initialization"]["Vc2_V"]-veq
        rows = []
        n = round(p["measurement"]["duration_s"]/period)
        for k in range(n):
            wrap_index = math.floor(e+.5)
            wrapped = e-wrap_index
            raw_timing = -wrapped*period
            timing = max(-period+c["pfd_reset_s"], min(period-c["pfd_reset_s"], raw_timing))
            q = signed_charge(target, timing)
            post = x+q/c1
            nx = transition[0][0]*post+transition[0][1]*y
            ny = transition[1][0]*post+transition[1][1]*y
            de = v["Kvco_Hz_per_V"]/c["N"]*(integral[0]*post+integral[1]*y)
            if not all(math.isfinite(value) for value in (x, y, e, post, nx, ny, de, q)):
                raise ValueError("nonfinite state transition")
            rows.append({"time_s": k*period, "phase_deg": 360*wrapped,
                         "unwrapped_error_cycles": e, "phase_wrap_index": wrap_index,
                         "frequency_cycle_Hz": c["fout_target_Hz"]+c["N"]*de/period,
                         "frequency_error_ppm": de*1e6,
                         "vctrl_pre_V": veq+x, "vctrl_post_V": veq+post,
                         "vctrl_min_V": veq+min(x, post, nx), "vctrl_max_V": veq+max(x, post, nx),
                         "timing_s": raw_timing, "charge_balance_C": q,
                         "pulse_clipped": int(raw_timing != timing)})
            x, y, e = nx, ny, e+de
        metrics = measure_cycles(rows, p)
        if "mean_phase_abs_deg" not in metrics:
            raise ValueError(metrics.get("reason", "invalid measured window"))
        spec = limits(p)
        margins = {"mean_phase_abs_deg": spec["mean_phase_abs_deg"]-metrics["mean_phase_abs_deg"],
                   "tail_max_abs_frequency_error_ppm": spec["tail_max_abs_frequency_error_ppm"]-metrics["tail_max_abs_frequency_error_ppm"]}
        ok = all(value >= 0 for value in margins.values()) and metrics["lock_status"] == "LOCKED"
        vlo, vhi = min(r["vctrl_min_V"] for r in rows), max(r["vctrl_max_V"] for r in rows)
        vrange = v["declared_voltage_range_V"]
        numeric_domain = vrange[0] <= vlo <= vhi <= vrange[1] and not any(r["pulse_clipped"] for r in rows)
        tmin, tmax = min(r["timing_s"] for r in rows), max(r["timing_s"] for r in rows)
        empirical = "NOT_ESTABLISHED_FOR_DECLARED_TARGET"
        if target.get("circuit_id"):
            empirical = "IN_LOCAL_TIMING_DOMAIN" if -1e-10 <= tmin <= tmax <= 1e-10 else "OUT_OF_LOCAL_TIMING_DOMAIN"
        return {"model_id": MODEL_ID, "metrics": metrics, "constraint_margins": margins,
                "units": {"mean_phase_abs_deg": "deg", "tail_max_abs_frequency_error_ppm": "ppm", "lock_status": "1"},
                "measurement_windows": p["measurement"],
                "behavioral_model_verdict": "PREDICTED_PASS" if ok else "PREDICTED_FAIL",
                "numeric_domain_status": "IN_DECLARED_NUMERIC_DOMAIN" if numeric_domain else "OUT_OF_DECLARED_NUMERIC_DOMAIN",
                "empirical_cp_trajectory_domain": empirical,
                "model_domain_verdict": "OUT_OF_DOMAIN" if not numeric_domain or empirical == "OUT_OF_LOCAL_TIMING_DOMAIN" else "CONDITIONAL",
                "validity": {"vctrl_range_V": [vlo, vhi], "timing_range_s": [tmin, tmax],
                             "vco_declared_range_V": vrange,
                             "target_cp_timing_domain_s": [-period+c["pfd_reset_s"], period-c["pfd_reset_s"]],
                             "empirical_loaded_cp_timing_domain_s": [-1e-10, 1e-10] if target.get("circuit_id") else None,
                             "assumptions": ["CP I and q0 are declared conditional targets, not observed implementation capabilities",
                                             "instantaneous charge impulse; passive ideal RC; fixed linear VCO",
                                             "q0 includes local proxy DC charge; incremental proxy conductance omitted",
                                             "sampling lock criterion is not a full transistor capture proof"]},
                "equilibrium_prediction": {"phase_deg": -360*c["fref_Hz"]*equilibrium_timing(target), "vctrl_V": veq},
                "runtime_cost": {"behavioral_evaluations": 1, "reference_cycles": n, "external_simulator_calls": 0},
                "independent_system_qualified_verdict": "UNKNOWN", "cycles": rows}
