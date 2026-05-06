"""Input CSV validation with clear, actionable error messages.

Used by the `scrape` and `run --scrape` commands to fail fast (BEFORE we boot
Selenium / start analysis) when the input file is malformed.
"""
from __future__ import annotations
import csv
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

# An Instagram profile URL like https://www.instagram.com/<handle>/
_IG_URL_RE = re.compile(
    r"^https?://(www\.)?instagram\.com/[A-Za-z0-9_.]{1,30}/?(\?.*)?$",
    re.IGNORECASE,
)


class CsvValidationError(ValueError):
    """Raised when the input CSV cannot be safely consumed."""


@dataclass
class CsvValidationReport:
    path: str
    total_rows: int = 0
    valid_rows: int = 0
    errors: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def format(self) -> str:
        head = f"CSV: {self.path}  rows={self.total_rows}  valid={self.valid_rows}"
        if self.ok:
            return head + "  status=OK"
        return head + "  status=FAILED\n  - " + "\n  - ".join(self.errors)


def validate_input_csv(
    path: str,
    required_columns: Optional[List[str]] = None,
    url_column: str = "url",
) -> CsvValidationReport:
    """Validate the scrape input CSV.

    Required:
      * file exists and is non-empty
      * has a header row containing every column in ``required_columns``
        (defaults to ``[url_column]``)
      * every row has a non-empty value in ``url_column`` and that value is
        a syntactically valid Instagram profile URL
    """
    required_columns = required_columns or [url_column]
    report = CsvValidationReport(path=path)

    if not os.path.exists(path):
        report.errors.append(f"file not found: {path}")
        return report
    if os.path.getsize(path) == 0:
        report.errors.append("file is empty (0 bytes)")
        return report

    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            report.errors.append(
                "missing header row; expected columns: "
                + ", ".join(required_columns)
            )
            return report

        # Header validation
        headers_lower = {h.lower(): h for h in reader.fieldnames}
        for col in required_columns:
            if col.lower() not in headers_lower:
                report.errors.append(
                    f"required column '{col}' missing "
                    f"(found: {', '.join(reader.fieldnames)})"
                )
        if report.errors:
            return report

        url_key = headers_lower[url_column.lower()]
        seen = set()

        for i, row in enumerate(reader, start=2):  # row 1 = header
            report.total_rows += 1
            value = (row.get(url_key) or "").strip()
            if not value:
                report.errors.append(f"row {i}: empty value in '{url_column}'")
                continue
            if not _IG_URL_RE.match(value):
                report.errors.append(
                    f"row {i}: '{value}' is not a valid Instagram URL "
                    f"(expected https://www.instagram.com/<handle>/)"
                )
                continue
            if value.lower() in seen:
                report.errors.append(f"row {i}: duplicate url '{value}'")
                continue
            seen.add(value.lower())
            report.valid_rows += 1

    if report.total_rows == 0:
        report.errors.append("no data rows after header")
    return report


def validate_or_raise(path: str, **kw) -> CsvValidationReport:
    rep = validate_input_csv(path, **kw)
    if not rep.ok:
        raise CsvValidationError(rep.format())
    return rep
