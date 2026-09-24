"""Deterministic VCO characterization and measurement; no requirement judgment."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping

from ..model.pll_behavioral import VCOParams
from ..specs import SystemSpec


def characterize_vco(
    vco: VCOParams,
    vctrl_points_v: Iterable[float],
    temperature_points_c: Iterable[float],
    offset_points_hz: Iterable[float] = (1.0e6,),
) -> List[Dict[str, float]]:
    """Generate deterministic VCO observation data for the prove step."""

    rows: List[Dict[str, float]] = []
    for temperature_c in temperature_points_c:
        for vctrl_v in vctrl_points_v:
            power_w = vco.power_w(vctrl_v, temperature_c)
            for offset_hz in offset_points_hz:
                rows.append(
                    {
                        "temperature_c": float(temperature_c),
                        "vctrl_v": float(vctrl_v),
                        "offset_hz": float(offset_hz),
                        "fosc_hz": vco.frequency_hz(vctrl_v, temperature_c),
                        "kvco_hz_per_v": vco.kvco_hz_per_v(vctrl_v),
                        "power_w": power_w,
                        "phase_noise_dbc_hz": vco.phase_noise_dbc_hz(
                            offset_hz, vctrl_v, temperature_c, power_w
                        ),
                    }
                )
    return rows


def _sample_points(lower: float, upper: float, count: int) -> List[float]:
    if count < 2:
        return [lower]
    return [lower + (upper - lower) * index / (count - 1) for index in range(count)]


def measure_vco_behavior(
    system_spec: SystemSpec,
    vco: VCOParams,
    system_context: Mapping[str, Any],
    vctrl_points: int = 11,
) -> Dict[str, Any]:
    """Measure VCO behavior over the frozen VCOBlockContext."""

    context_vctrl_min = float(system_context["vctrl_min_v"])
    context_vctrl_max = float(system_context["vctrl_max_v"])
    if context_vctrl_min > context_vctrl_max:
        raise ValueError("invalid system Vctrl context")
    vctrl_values = _sample_points(context_vctrl_min, context_vctrl_max, vctrl_points)
    temperatures = [
        float(value)
        for value in system_context.get(
            "temperature_points_c", system_spec.temperature_points_c
        )
    ]
    observations: List[Dict[str, Any]] = []
    for temperature_c in temperatures:
        for vctrl_v in vctrl_values:
            power_w = vco.power_w(vctrl_v, temperature_c)
            observations.append(
                {
                    "temperature_c": temperature_c,
                    "vctrl_v": vctrl_v,
                    "fosc_hz": vco.frequency_hz(vctrl_v, temperature_c),
                    "kvco_hz_per_v": vco.kvco_hz_per_v(vctrl_v),
                    "phase_noise_1mhz_dbc_hz": vco.phase_noise_dbc_hz(
                        1.0e6, vctrl_v, temperature_c, power_w
                    ),
                    "power_w": power_w,
                }
            )

    worst_pn = max(item["phase_noise_1mhz_dbc_hz"] for item in observations)
    frequencies = [item["fosc_hz"] for item in observations]
    frequency_span = max(frequencies) - min(frequencies)
    characterization_window = {
        "vctrl_min_v": context_vctrl_min,
        "vctrl_max_v": context_vctrl_max,
        "temperature_points_c": temperatures,
        "vdd_v": float(system_context.get("vdd_v", system_spec.vdd_v)),
        "source": system_context.get("source", "frozen VCOBlockContext"),
        "context_id": system_context.get("context_id", "VCOBlockContext.v1"),
        "semantics": "declared_block_characterization_window",
    }
    result = {
        "measurement_method": "context_sweep_behavioral_vco",
        "provenance": {
            # Historical operation identifier: retained for artifact/digest compatibility.
            "source": "v1.pipeline.measure_vco_behavior",
            "model": "synthetic_behavioral_vco_v1",
        },
        "characterization_window": characterization_window,
        # Backward-compatible alias for existing V1 artifacts.
        "context": characterization_window,
        "worst_case": {
            "worst_phase_noise_1mhz_dbc_hz": worst_pn,
            "worst_frequency_hz": max(frequencies),
            "frequency_min_hz": min(frequencies),
            "frequency_max_hz": max(frequencies),
            "tuning_range_hz": frequency_span,
            "kvco_min_hz_per_v": min(item["kvco_hz_per_v"] for item in observations),
            "kvco_max_hz_per_v": max(item["kvco_hz_per_v"] for item in observations),
            "power_min_w": min(item["power_w"] for item in observations),
            "worst_power_w": max(item["power_w"] for item in observations),
        },
        "observations": observations,
    }
    result["measured"] = {
        "phase_noise_1mhz_dbc_hz": [
            float(item["phase_noise_1mhz_dbc_hz"]) for item in observations
        ],
        "frequency_hz": [float(item["fosc_hz"]) for item in observations],
        "kvco_hz_per_v": [float(item["kvco_hz_per_v"]) for item in observations],
        "power_w": [float(item["power_w"]) for item in observations],
    }
    return result
