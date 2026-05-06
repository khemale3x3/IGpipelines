"""Single-step pipeline: scrape (optional) -> analyze -> export CSV/JSON
+ a human-readable summary report next to the outputs.
"""
from __future__ import annotations
import json
import os
from dataclasses import dataclass, field
from typing import Iterable, Optional, Set

from .analyze_use_case import run_analyze
from .export_use_case import run_export
from .summary_report import (
    SummaryStats, compute_top_locations, rules_to_dict, write_summary,
)
from ..adapters.exporters.json_exporter import export_json
from ..domain.services.exclusions import ExclusionRules


@dataclass
class PipelineConfig:
    output_dir: str = "output"
    analyzed_path: str = "analyzed.json"
    csv_path: Optional[str] = "report.csv"
    json_path: Optional[str] = None
    ssa_path: Optional[str] = "unique_names_ssa.txt"
    only_usernames: Optional[Iterable[str]] = None
    exclude_usernames: Set[str] = field(default_factory=set)
    rules: Optional[ExclusionRules] = None
    max_workers: int = 2
    parallel: bool = True
    repository: object = None  # for tests / in-memory
    summary_basename: str = "summary"


@dataclass
class PipelineResult:
    analyzed_ok: int
    analyzed_failed: int
    csv_rows: int
    json_rows: int
    summary_paths: dict = field(default_factory=dict)


def _summary_dir(cfg: PipelineConfig) -> str:
    for p in (cfg.csv_path, cfg.json_path, cfg.analyzed_path):
        if p:
            return os.path.dirname(os.path.abspath(p)) or "."
    return "."


def run_pipeline(cfg: PipelineConfig) -> PipelineResult:
    ok, failed, reasons = run_analyze(
        base_dir=cfg.output_dir,
        output_path=cfg.analyzed_path,
        only_usernames=cfg.only_usernames,
        exclude_usernames=cfg.exclude_usernames,
        max_workers=cfg.max_workers,
        rules=cfg.rules,
        repository=cfg.repository,
        parallel=cfg.parallel,
    )

    csv_rows = 0
    if cfg.csv_path:
        csv_rows = run_export(
            cfg.analyzed_path, cfg.csv_path,
            ssa_path=cfg.ssa_path if cfg.ssa_path and os.path.exists(cfg.ssa_path) else None,
        )

    json_rows = 0
    if cfg.json_path:
        json_rows = export_json(cfg.analyzed_path, cfg.json_path)

    # Build summary report
    creators = []
    if os.path.exists(cfg.analyzed_path):
        try:
            with open(cfg.analyzed_path, "r", encoding="utf-8") as f:
                creators = json.load(f).get("creators", [])
        except Exception:
            creators = []
    cities, countries = compute_top_locations(creators)
    stats = SummaryStats(
        analyzed_ok=ok, analyzed_failed=failed,
        filter_reasons=reasons,
        top_cities=cities, top_countries=countries,
        exclusions_applied=rules_to_dict(cfg.rules),
    )
    paths = write_summary(stats, _summary_dir(cfg), base_name=cfg.summary_basename)

    return PipelineResult(ok, failed, csv_rows, json_rows, summary_paths=paths)
