"""JSON exporter — writes the analyzed list as a flat JSON array."""
from __future__ import annotations
import json
from decimal import Decimal
from typing import Any

try:
    import ijson  # type: ignore
except Exception:  # pragma: no cover
    ijson = None


def _coerce(o: Any) -> Any:
    if isinstance(o, Decimal):
        return float(o)
    raise TypeError(f"not serializable: {type(o).__name__}")


def export_json(analyzed_json_path: str, output_json_path: str) -> int:
    """Read analyzed.json and write a compact JSON array of creator dicts.

    Streams via ijson when available, falls back to a full json.load otherwise.
    """
    rows = []
    if ijson is not None:
        with open(analyzed_json_path, "rb") as f:
            for obj in ijson.items(f, "creators.item"):
                rows.append(obj)
    else:
        with open(analyzed_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        rows = data.get("creators", []) if isinstance(data, dict) else list(data)

    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2, default=_coerce)
    return len(rows)
