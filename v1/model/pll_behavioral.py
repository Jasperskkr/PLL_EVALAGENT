"""Minimal behavioral Integer-N CPPLL model for the V1 feasibility prototype.

The model is phase-domain / reference-cycle sampled. It is intended for fast
system-level exploration, not transistor-level signoff. The VCO object is a
realized behavioral instance (an oracle in the V1 synthetic experiment), while
a separate contract predictor can be layered on top later.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class VCOParams:
    """Parameters for a nonlinear VCO behavioral instance."""

    f0_hz: float = 4.45e9
    v0_v: float = 0.50
    k1_hz_per_v: float = 1.60e9
    k2_hz_per_v2: float = 0.70e9
    tempco_hz_per_c: float = 0.15e6
    nominal_temperature_c: float = 25.0
    vctrl_min_v: float = 0.10
    vctrl_max_v: float = 1.10
    nominal_power_w: float = 5.0e-3
    power_vctrl_coeff: float = 0.12
    pn_1mhz_dbc_hz: float = -116.0
    pn_vctrl_coeff_db_per_v: float = 8.0
    pn_temp_coeff_db_per_c: float = 0.018
    pn_power_coeff_db_per_decade: float = -3.0

    def frequency_hz(self, vctrl_v: float, temperature_c: float) -> float:
        """Nonlinear tuning curve f(Vctrl, temperature)."""
        x = vctrl_v - self.v0_v
        return (
            self.f0_hz
            + self.k1_hz_per_v * x
            + self.k2_hz_per_v2 * x * x
            + self.tempco_hz_per_c * (temperature_c - self.nominal_temperature_c)
        )

    def kvco_hz_per_v(self, vctrl_v: float) -> float:
        """Local derivative of the nonlinear tuning curve."""
        return self.k1_hz_per_v + 2.0 * self.k2_hz_per_v2 * (vctrl_v - self.v0_v)

    def power_w(self, vctrl_v: float, temperature_c: float) -> float:
        """Simple positive power model for the behavioral instance."""
        normalized_v = (vctrl_v - self.vctrl_min_v) / (
            self.vctrl_max_v - self.vctrl_min_v
        )
        temp_factor = 1.0 + 0.001 * (temperature_c - self.nominal_temperature_c)
        return max(
            0.1e-3,
            self.nominal_power_w
            * (1.0 + self.power_vctrl_coeff * normalized_v)
            * temp_factor,
        )

    def phase_noise_dbc_hz(
        self,
        offset_hz: float,
        vctrl_v: float,
        temperature_c: float,
        power_w: Optional[float] = None,
    ) -> float:
        """Synthetic SSB phase-noise curve.

        The explicit Vctrl term intentionally makes a constant PN contract
        insufficient for the Contract-vs-Oracle refinement experiment.
        """
        if offset_hz <= 0.0:
            raise ValueError("offset_hz must be positive")
        if power_w is None:
            power_w = self.power_w(vctrl_v, temperature_c)

        if offset_hz < 1.0e6:
            slope_term = 30.0 * math.log10(1.0e6 / offset_hz)
        else:
            slope_term = -20.0 * math.log10(offset_hz / 1.0e6)

        power_ratio = max(power_w / self.nominal_power_w, 1.0e-6)
        return (
            self.pn_1mhz_dbc_hz
            + self.pn_vctrl_coeff_db_per_v * (vctrl_v - self.v0_v)
            + self.pn_temp_coeff_db_per_c * (temperature_c - self.nominal_temperature_c)
            + self.pn_power_coeff_db_per_decade * math.log10(power_ratio)
            + slope_term
        )


@dataclass(frozen=True)
class CPPLLParams:
    """Reference-cycle sampled averaged CPPLL parameters.

    kp and ki are normalized effective proportional/integral gains. The CP
    current and passive filter values are retained as physical metadata and
    can later be used to derive gains from a loop-filter model.
    """

    f_ref_hz: float = 50.0e6
    divider_n: int = 100
    vdd_v: float = 1.8
    temperature_c: float = 25.0
    vctrl_initial_v: float = 0.30
    vctrl_min_v: float = 0.10
    vctrl_max_v: float = 1.10
    cp_current_a: float = 100.0e-6
    loop_filter_r_ohm: float = 2.0e3
    loop_filter_c_f: float = 20.0e-9
    kp: float = 0.05
    ki: float = 2.0e-4
    max_cycles: int = 5000
    lock_relative_frequency_tolerance: float = 1.0e-5
    lock_consecutive_cycles: int = 100
    jitter_f_low_hz: float = 10.0
    jitter_f_high_hz: float = 20.0e6
    jitter_points: int = 240
    loop_bandwidth_hz: Optional[float] = None


def _clip(value: float, lower: float, upper: float) -> float:
    return min(max(value, lower), upper)


def _logspace(start: float, stop: float, points: int) -> Iterable[float]:
    if points < 2:
        raise ValueError("points must be >= 2")
    start_log = math.log10(start)
    step = (math.log10(stop) - start_log) / (points - 1)
    return (10.0 ** (start_log + i * step) for i in range(points))


def estimate_loop_bandwidth_hz(
    pll: CPPLLParams, vco: VCOParams, vctrl_v: float
) -> float:
    """Return an effective bandwidth for the phase-noise approximation."""
    if pll.loop_bandwidth_hz is not None:
        return max(1.0, pll.loop_bandwidth_hz)

    # A bounded effective bandwidth inferred from normalized PI gains. This is
    # intentionally a behavioral parameterization rather than a transistor-
    # accurate CP/loop-filter derivation.
    gain_term = pll.kp + math.sqrt(max(pll.ki, 0.0))
    kvco_term = max(vco.kvco_hz_per_v(vctrl_v) / 1.0e9, 0.05)
    estimated = pll.f_ref_hz * gain_term * math.sqrt(kvco_term)
    return _clip(estimated, 1.0e3, 0.20 * pll.f_ref_hz)


def integrated_vco_jitter_s(
    vco: VCOParams,
    pll: CPPLLParams,
    vctrl_v: float,
    output_frequency_hz: float,
) -> float:
    """Integrate the VCO phase-noise contribution through a high-pass loop.

    This is a compact phase-domain approximation. It is deterministic and
    suitable for comparing candidates, but it is not a replacement for PSS /
    PNOISE.
    """
    bandwidth_hz = estimate_loop_bandwidth_hz(pll, vco, vctrl_v)
    offsets = list(
        _logspace(pll.jitter_f_low_hz, pll.jitter_f_high_hz, pll.jitter_points)
    )
    integral = 0.0
    previous_offset: Optional[float] = None
    previous_density: Optional[float] = None

    for offset in offsets:
        pn_dbc_hz = vco.phase_noise_dbc_hz(
            offset, vctrl_v, pll.temperature_c, vco.power_w(vctrl_v, pll.temperature_c)
        )
        # VCO noise is high-pass shaped by the locked loop.
        transfer_sq = (offset * offset) / (offset * offset + bandwidth_hz * bandwidth_hz)
        phase_density = 2.0 * (10.0 ** (pn_dbc_hz / 10.0)) * transfer_sq

        if previous_offset is not None and previous_density is not None:
            integral += 0.5 * (phase_density + previous_density) * (
                offset - previous_offset
            )
        previous_offset = offset
        previous_density = phase_density

    return math.sqrt(max(integral, 0.0)) / (2.0 * math.pi * output_frequency_hz)


def simulate_cppll(
    pll: CPPLLParams = CPPLLParams(), vco: VCOParams = VCOParams()
) -> Dict[str, Any]:
    """Simulate an averaged Integer-N CPPLL at reference-clock updates.

    The loop uses normalized frequency error as the averaged PFD/CP error
    signal and an effective PI loop-filter update. No RF waveform is sampled.
    """
    if pll.divider_n <= 0:
        raise ValueError("divider_n must be positive")
    if pll.f_ref_hz <= 0.0:
        raise ValueError("f_ref_hz must be positive")

    target_frequency_hz = pll.f_ref_hz * pll.divider_n
    vctrl = _clip(
        pll.vctrl_initial_v,
        max(pll.vctrl_min_v, vco.vctrl_min_v),
        min(pll.vctrl_max_v, vco.vctrl_max_v),
    )
    integrator = 0.0
    phase_reference_cycles = 0.0
    phase_divided_cycles = 0.0
    lock_run = 0
    lock_cycle: Optional[int] = None

    history: List[Dict[str, float]] = []
    for cycle in range(pll.max_cycles):
        output_frequency_hz = vco.frequency_hz(vctrl, pll.temperature_c)
        divided_frequency_hz = output_frequency_hz / pll.divider_n
        relative_frequency_error = (
            target_frequency_hz - output_frequency_hz
        ) / target_frequency_hz

        phase_reference_cycles += 1.0
        phase_divided_cycles += divided_frequency_hz / pll.f_ref_hz
        phase_error_cycles = phase_reference_cycles - phase_divided_cycles
        wrapped_phase_error_cycles = ((phase_error_cycles + 0.5) % 1.0) - 0.5

        # Averaged PFD/CP command. kp/ki are normalized effective loop-filter
        # gains, while cp_current and R/C remain available as physical metadata.
        integrator += relative_frequency_error
        vctrl += pll.kp * relative_frequency_error + pll.ki * integrator
        vctrl = _clip(
            vctrl,
            max(pll.vctrl_min_v, vco.vctrl_min_v),
            min(pll.vctrl_max_v, vco.vctrl_max_v),
        )

        if abs(relative_frequency_error) <= pll.lock_relative_frequency_tolerance:
            lock_run += 1
            if (
                lock_run >= pll.lock_consecutive_cycles
                and lock_cycle is None
            ):
                lock_cycle = cycle - pll.lock_consecutive_cycles + 1
        else:
            lock_run = 0

        history.append(
            {
                "cycle": float(cycle),
                "time_s": float((cycle + 1) / pll.f_ref_hz),
                "vctrl_v": vctrl,
                "fosc_hz": output_frequency_hz,
                "fdiv_hz": divided_frequency_hz,
                "relative_frequency_error": relative_frequency_error,
                "phase_error_cycles": wrapped_phase_error_cycles,
            }
        )

    tail_length = min(
        100,
        len(history),
    )
    tail = history[-tail_length:]
    final_vctrl_v = tail[-1]["vctrl_v"]
    final_output_frequency_hz = sum(item["fosc_hz"] for item in tail) / tail_length
    final_relative_error = (
        target_frequency_hz - final_output_frequency_hz
    ) / target_frequency_hz
    final_power_w = vco.power_w(final_vctrl_v, pll.temperature_c)
    integrated_jitter = integrated_vco_jitter_s(
        vco, pll, final_vctrl_v, final_output_frequency_hz
    )

    vctrl_values = [item["vctrl_v"] for item in history]
    fosc_values = [item["fosc_hz"] for item in history]
    metrics: Dict[str, Optional[float]] = {
        "output_frequency_hz": final_output_frequency_hz,
        "integrated_jitter_s": integrated_jitter,
        "lock_time_s": (
            None
            if lock_cycle is None
            else float((lock_cycle + pll.lock_consecutive_cycles) / pll.f_ref_hz)
        ),
        "power_w": final_power_w,
        "phase_noise_100khz_dbc_hz": vco.phase_noise_dbc_hz(
            100.0e3, final_vctrl_v, pll.temperature_c, final_power_w
        ),
        "phase_noise_1mhz_dbc_hz": vco.phase_noise_dbc_hz(
            1.0e6, final_vctrl_v, pll.temperature_c, final_power_w
        ),
        "phase_noise_10mhz_dbc_hz": vco.phase_noise_dbc_hz(
            10.0e6, final_vctrl_v, pll.temperature_c, final_power_w
        ),
        "kvco_hz_per_v": vco.kvco_hz_per_v(final_vctrl_v),
        "loop_bandwidth_hz": estimate_loop_bandwidth_hz(
            pll, vco, final_vctrl_v
        ),
        "final_relative_frequency_error": final_relative_error,
        "final_vctrl_v": final_vctrl_v,
    }

    context = {
        "vctrl_min_v": min(vctrl_values),
        "vctrl_max_v": max(vctrl_values),
        "fosc_min_hz": min(fosc_values),
        "fosc_max_hz": max(fosc_values),
        "temperature_c": pll.temperature_c,
        "vdd_v": pll.vdd_v,
        "divider_n": pll.divider_n,
        "f_ref_hz": pll.f_ref_hz,
    }

    return {
        "model": "averaged_integer_n_cppll_v1",
        "mode": "reference_cycle_phase_domain",
        "target_frequency_hz": target_frequency_hz,
        "metrics": metrics,
        "context": context,
        "locked": lock_cycle is not None,
        "lock_cycle": lock_cycle,
        "simulation_cycles": len(history),
        "parameters": {
            "pll": asdict(pll),
            "vco": asdict(vco),
        },
        "history": history,
    }


def write_result(result: Dict[str, Any], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


if __name__ == "__main__":
    result = simulate_cppll()
    print(json.dumps({k: result[k] for k in ("model", "metrics", "context", "locked")}, indent=2))
