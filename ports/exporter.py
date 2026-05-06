"""Port: exporter writes analyzed creators to a sink (CSV, DB, ...)."""
from __future__ import annotations
from typing import Protocol


class ExporterPort(Protocol):
    def export(self, analyzed_json_path: str, output_path: str) -> int:
        """Return number of rows exported."""
        ...
