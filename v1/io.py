"""Deterministic JSON/CSV serialization helpers used by runners."""

from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Sequence
import csv
import json
import math


def jsonable(value: Any) -> Any:
    """Convert dataclasses and non-finite values to strict JSON values."""

    if hasattr(value, "__dataclass_fields__"):
        return {key: jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def write_json(value: Any, path: str | Path) -> None:
    """Write application JSON, normalizing non-finite floats to ``null``."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(jsonable(value), indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def read_json(path: str | Path) -> Any:
    """Read one UTF-8 JSON document."""

    return json.loads(Path(path).read_text(encoding="utf-8"))


def canonical_evidence_json(value: Any) -> str:
    """Serialize evidence deterministically and reject non-finite values."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def evidence_digest(value: Any) -> str:
    """Return the canonical SHA-256 identity used by evidence artifacts."""

    return sha256(canonical_evidence_json(value).encode("utf-8")).hexdigest()


def file_sha256(path: str | Path) -> str:
    """Return the SHA-256 digest of the exact bytes stored at ``path``."""

    return sha256(Path(path).read_bytes()).hexdigest()


def write_evidence_json(value: Any, path: str | Path) -> None:
    """Write strict evidence JSON without silently coercing invalid numbers."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            value,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
        ),
        encoding="utf-8",
    )


def write_csv(rows: Sequence[Mapping[str, Any]], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        output_path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


__all__ = [
    "canonical_evidence_json",
    "evidence_digest",
    "file_sha256",
    "jsonable",
    "read_json",
    "write_csv",
    "write_evidence_json",
    "write_json",
]
