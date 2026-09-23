"""Deterministic design-space definitions for V1.5 allocation.

This module defines only the search domain and its enumeration order.  It does
not evaluate candidates or decide feasibility.  Keeping those responsibilities
separate makes the sampled point set reproducible before the multidimensional
evaluator is introduced.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from itertools import product
import json
from math import prod
from typing import Any, Dict, Iterator, Mapping, Sequence


DETERMINISTIC_GRID_METHOD = "deterministic_cartesian_grid"
DETERMINISTIC_TRAVERSAL = "first_axis_outer"
POINT_ID_SCHEME = "sha256_canonical_design_vector_v1"


def _decimal(value: Any, *, field_name: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be numeric")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric") from exc
    if not result.is_finite():
        raise ValueError(f"{field_name} must be finite")
    return result


def _canonical_decimal(value: float) -> str:
    normalized = Decimal(str(value)).normalize()
    text = format(normalized, "f")
    return "0" if text in {"-0", "-0.0"} else text


@dataclass(frozen=True)
class AxisDefinition:
    """One inclusive, uniformly spaced design-vector axis."""

    name: str
    unit: str
    start: float
    stop: float
    step: float

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AxisDefinition":
        name = str(data.get("name", "")).strip()
        unit = str(data.get("unit", "")).strip()
        if not name:
            raise ValueError("design-space axis must have a name")
        if not unit:
            raise ValueError(f"design-space axis {name} must have a unit")
        start = _decimal(data.get("start"), field_name=f"{name}.start")
        stop = _decimal(data.get("stop"), field_name=f"{name}.stop")
        step = _decimal(data.get("step"), field_name=f"{name}.step")
        if step <= 0:
            raise ValueError(f"design-space axis {name} step must be positive")
        if stop < start:
            raise ValueError(f"design-space axis {name} stop must be >= start")
        intervals = (stop - start) / step
        if intervals != intervals.to_integral_value():
            raise ValueError(
                f"design-space axis {name} range must be exactly divisible by step"
            )
        return cls(
            name=name,
            unit=unit,
            start=float(start),
            stop=float(stop),
            step=float(step),
        )

    def values(self) -> tuple[float, ...]:
        start = Decimal(str(self.start))
        stop = Decimal(str(self.stop))
        step = Decimal(str(self.step))
        interval_count = int((stop - start) / step)
        return tuple(float(start + step * index) for index in range(interval_count + 1))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "unit": self.unit,
            "start": self.start,
            "stop": self.stop,
            "step": self.step,
            "count": len(self.values()),
        }


@dataclass(frozen=True)
class DesignPointDefinition:
    """One deterministically enumerated point in a design space."""

    point_id: str
    ordinal: int
    values: Dict[str, float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "point_id": self.point_id,
            "ordinal": self.ordinal,
            "design_vector": dict(self.values),
        }


@dataclass(frozen=True)
class DesignSpaceDefinition:
    """Validated Cartesian-grid configuration with stable point identities."""

    axes: tuple[AxisDefinition, ...]
    axis_order: tuple[str, ...]
    expected_point_count: int
    method: str = DETERMINISTIC_GRID_METHOD
    traversal: str = DETERMINISTIC_TRAVERSAL
    point_id_scheme: str = POINT_ID_SCHEME
    random_seed: Any = None
    refinement: Any = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DesignSpaceDefinition":
        method = str(data.get("method", ""))
        traversal = str(data.get("traversal", ""))
        point_id_scheme = str(data.get("point_id_scheme", ""))
        if method != DETERMINISTIC_GRID_METHOD:
            raise ValueError(f"unsupported design-space method: {method}")
        if traversal != DETERMINISTIC_TRAVERSAL:
            raise ValueError(f"unsupported design-space traversal: {traversal}")
        if point_id_scheme != POINT_ID_SCHEME:
            raise ValueError(f"unsupported point-id scheme: {point_id_scheme}")
        if data.get("random_seed") is not None:
            raise ValueError("deterministic Cartesian grid must not use a random seed")
        if data.get("refinement") is not None:
            raise ValueError("V1.5 initial grid must not enable refinement")

        raw_axes = data.get("axes")
        if not isinstance(raw_axes, Sequence) or isinstance(raw_axes, (str, bytes)):
            raise ValueError("design-space axes must be an array")
        axes = tuple(AxisDefinition.from_dict(item) for item in raw_axes)
        if len(axes) < 2:
            raise ValueError("V1.5 design space requires at least two axes")
        axis_names = [axis.name for axis in axes]
        if len(set(axis_names)) != len(axis_names):
            raise ValueError("design-space axis names must be unique")

        raw_order = data.get("axis_order")
        if not isinstance(raw_order, Sequence) or isinstance(raw_order, (str, bytes)):
            raise ValueError("design-space axis_order must be an array")
        axis_order = tuple(str(name) for name in raw_order)
        if len(axis_order) != len(axes) or set(axis_order) != set(axis_names):
            raise ValueError("axis_order must list every design-space axis exactly once")

        expected = int(data.get("expected_point_count", 0))
        actual = prod(len(axis.values()) for axis in axes)
        if expected != actual:
            raise ValueError(
                f"expected_point_count is {expected}; axis product is {actual}"
            )
        return cls(
            axes=axes,
            axis_order=axis_order,
            expected_point_count=expected,
            method=method,
            traversal=traversal,
            point_id_scheme=point_id_scheme,
            random_seed=None,
            refinement=None,
        )

    def _axis_map(self) -> dict[str, AxisDefinition]:
        return {axis.name: axis for axis in self.axes}

    def point_id(self, values: Mapping[str, float]) -> str:
        if set(values) != set(self.axis_order):
            raise ValueError("point values must match the design-space axes")
        canonical = [
            [name, _canonical_decimal(float(values[name]))]
            for name in self.axis_order
        ]
        payload = json.dumps(canonical, ensure_ascii=True, separators=(",", ":"))
        return f"v15p-{sha256(payload.encode('utf-8')).hexdigest()[:16]}"

    def iter_points(self) -> Iterator[DesignPointDefinition]:
        axes = self._axis_map()
        ordered_values = [axes[name].values() for name in self.axis_order]
        for ordinal, coordinate in enumerate(product(*ordered_values)):
            values = {
                name: float(value)
                for name, value in zip(self.axis_order, coordinate)
            }
            yield DesignPointDefinition(
                point_id=self.point_id(values),
                ordinal=ordinal,
                values=values,
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "method": self.method,
            "axes": [axis.to_dict() for axis in self.axes],
            "axis_order": list(self.axis_order),
            "traversal": self.traversal,
            "point_id_scheme": self.point_id_scheme,
            "expected_point_count": self.expected_point_count,
            "random_seed": self.random_seed,
            "refinement": self.refinement,
        }


__all__ = [
    "AxisDefinition",
    "DesignPointDefinition",
    "DesignSpaceDefinition",
    "DETERMINISTIC_GRID_METHOD",
    "DETERMINISTIC_TRAVERSAL",
    "POINT_ID_SCHEME",
]
