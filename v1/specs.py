"""Small, dependency-free data contracts for the V1 SystemSpec-to-VCO demo.

The V1 runner intentionally uses plain dataclasses and JSON rather than a large
schema framework.  These objects are the seam that can later be replaced by
versioned YAML/JSON schemas without changing the simulator or evaluator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional
import json


def _as_float(value: Any) -> float:
    return float(value)


def _normalize_candidate_overrides(values: Mapping[str, Any]) -> Dict[str, Any]:
    aliases = {"pn_1mhz_dbc_hz": "pn_anchor_1mhz_dbc_hz"}
    normalized: Dict[str, Any] = {}
    for name, value in values.items():
        canonical = aliases.get(str(name), str(name))
        if canonical in normalized and normalized[canonical] != value:
            raise ValueError(f"conflicting candidate override aliases for {canonical}")
        normalized[canonical] = value
    return normalized


@dataclass(frozen=True)
class SystemSpec:
    """Immutable system-level requirements used by the evaluator."""

    f_ref_hz: float
    divider_n: int
    target_frequency_hz: float
    output_frequency_tolerance_hz: float
    integrated_jitter_max_s: float
    lock_time_max_s: float
    power_max_w: Optional[float]
    vdd_v: float
    temperature_points_c: List[float]
    vctrl_initial_v: float
    vctrl_min_v: float
    vctrl_max_v: float
    jitter_f_low_hz: float
    jitter_f_high_hz: float
    jitter_points: int

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SystemSpec":
        pll = data.get("pll", {})
        limits = data.get("limits", {})
        context = data.get("operating_context", {})
        jitter = data.get("jitter", {})
        target = data.get("target_frequency_hz")
        if target is None:
            target = float(pll["f_ref_hz"]) * int(pll["divider_n"])
        temperatures = context.get("temperature_points_c")
        if temperatures is None:
            temperatures = [context.get("temperature_c", pll.get("temperature_c", 25.0))]
        return cls(
            f_ref_hz=_as_float(pll["f_ref_hz"]),
            divider_n=int(pll["divider_n"]),
            target_frequency_hz=_as_float(target),
            output_frequency_tolerance_hz=_as_float(
                limits["output_frequency_tolerance_hz"]
            ),
            integrated_jitter_max_s=_as_float(limits["integrated_jitter_max_s"]),
            lock_time_max_s=_as_float(limits["lock_time_max_s"]),
            power_max_w=(
                None
                if limits.get("power_max_w") is None
                else _as_float(limits["power_max_w"])
            ),
            vdd_v=_as_float(context.get("vdd_v", pll.get("vdd_v", 1.8))),
            temperature_points_c=[_as_float(item) for item in temperatures],
            vctrl_initial_v=_as_float(
                context.get("vctrl_initial_v", pll.get("vctrl_initial_v", 0.30))
            ),
            vctrl_min_v=_as_float(
                context.get("vctrl_min_v", pll.get("vctrl_min_v", 0.10))
            ),
            vctrl_max_v=_as_float(
                context.get("vctrl_max_v", pll.get("vctrl_max_v", 1.10))
            ),
            jitter_f_low_hz=_as_float(jitter.get("f_low_hz", 10.0)),
            jitter_f_high_hz=_as_float(jitter.get("f_high_hz", 20.0e6)),
            jitter_points=int(jitter.get("points", 240)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pll": {"f_ref_hz": self.f_ref_hz, "divider_n": self.divider_n},
            "target_frequency_hz": self.target_frequency_hz,
            "limits": {
                "output_frequency_tolerance_hz": self.output_frequency_tolerance_hz,
                "integrated_jitter_max_s": self.integrated_jitter_max_s,
                "lock_time_max_s": self.lock_time_max_s,
                "power_max_w": self.power_max_w,
            },
            "operating_context": {
                "vdd_v": self.vdd_v,
                "temperature_points_c": self.temperature_points_c,
                "vctrl_initial_v": self.vctrl_initial_v,
                "vctrl_min_v": self.vctrl_min_v,
                "vctrl_max_v": self.vctrl_max_v,
            },
            "jitter": {
                "f_low_hz": self.jitter_f_low_hz,
                "f_high_hz": self.jitter_f_high_hz,
                "points": self.jitter_points,
            },
        }


@dataclass(frozen=True)
class VCORequirement:
    """Requirements allocated to a VCO, separate from its realized behavior."""

    phase_noise_1mhz_max_dbc_hz: float
    tuning_range_min_hz: Optional[float] = None
    kvco_min_hz_per_v: Optional[float] = None
    kvco_max_hz_per_v: Optional[float] = None
    power_max_w: Optional[float] = None
    margin_db: float = 0.0

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "VCORequirement":
        return cls(
            phase_noise_1mhz_max_dbc_hz=_as_float(
                data["phase_noise_1mhz_max_dbc_hz"]
            ),
            tuning_range_min_hz=(
                None
                if data.get("tuning_range_min_hz") is None
                else _as_float(data["tuning_range_min_hz"])
            ),
            kvco_min_hz_per_v=(
                None
                if data.get("kvco_min_hz_per_v") is None
                else _as_float(data["kvco_min_hz_per_v"])
            ),
            kvco_max_hz_per_v=(
                None
                if data.get("kvco_max_hz_per_v") is None
                else _as_float(data["kvco_max_hz_per_v"])
            ),
            power_max_w=(
                None
                if data.get("power_max_w") is None
                else _as_float(data["power_max_w"])
            ),
            margin_db=_as_float(data.get("margin_db", 0.0)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase_noise_1mhz_max_dbc_hz": self.phase_noise_1mhz_max_dbc_hz,
            "tuning_range_min_hz": self.tuning_range_min_hz,
            "kvco_min_hz_per_v": self.kvco_min_hz_per_v,
            "kvco_max_hz_per_v": self.kvco_max_hz_per_v,
            "power_max_w": self.power_max_w,
            "margin_db": self.margin_db,
        }


@dataclass(frozen=True)
class CandidateDefinition:
    """A synthetic candidate source used for independent validation."""

    candidate_id: str
    overrides: Dict[str, Any] = field(default_factory=dict)
    engineering_cost: float = 0.0
    description: str = ""

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CandidateDefinition":
        return cls(
            candidate_id=str(data["candidate_id"]),
            overrides=_normalize_candidate_overrides(data.get("overrides", {})),
            engineering_cost=_as_float(data.get("engineering_cost", 0.0)),
            description=str(data.get("description", "")),
        )


def load_case(path: str | Path) -> Dict[str, Any]:
    """Load a deterministic JSON case file."""

    case_path = Path(path)
    with case_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("case file must contain a JSON object")
    return data
