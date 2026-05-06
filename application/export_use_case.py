"""Use-case: export an analyzed.json file to CSV."""
from __future__ import annotations
import os
from typing import Optional

from ..adapters.exporters.streaming_csv_exporter import StreamingCsvExporter
from ..adapters.name_providers.ssa_name_provider import (
    SSAFirstNameValidator, PassthroughFirstNameValidator,
)


def run_export(
    analyzed_json_path: str, output_csv_path: str,
    ssa_path: Optional[str] = "unique_names_ssa.txt",
) -> int:
    validator = (
        SSAFirstNameValidator(ssa_path) if ssa_path and os.path.exists(ssa_path)
        else PassthroughFirstNameValidator()
    )
    exporter = StreamingCsvExporter(name_validator=validator)
    return exporter.export(analyzed_json_path, output_csv_path)
