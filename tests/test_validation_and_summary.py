"""Tests for CSV input validation and summary report generation."""
from __future__ import annotations
import json
import os

import pytest

from insta_pipeline.adapters.mocks import InMemoryRepository
from insta_pipeline.application.csv_validation import (
    validate_input_csv, validate_or_raise, CsvValidationError,
)
from insta_pipeline.application.pipeline_use_case import (
    PipelineConfig, run_pipeline,
)
from insta_pipeline.application.summary_report import SummaryStats
from insta_pipeline.domain.services.exclusions import build_rules
from insta_pipeline.tests.fixtures import make_raw, SAMPLE_INPUT_CSV


# ---------- CSV validation -------------------------------------------------

def test_csv_validation_ok(tmp_path):
    p = tmp_path / "input.csv"
    p.write_text(SAMPLE_INPUT_CSV, encoding="utf-8")
    rep = validate_input_csv(str(p))
    assert rep.ok, rep.format()
    assert rep.valid_rows == 3


def test_csv_validation_missing_file():
    rep = validate_input_csv("/tmp/does_not_exist_xyz.csv")
    assert not rep.ok
    assert "file not found" in rep.format()


def test_csv_validation_missing_header(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("not_a_url\nfoo\n", encoding="utf-8")
    rep = validate_input_csv(str(p))
    assert not rep.ok
    assert "required column 'url' missing" in rep.format()


def test_csv_validation_bad_url_and_empty(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("url,note\n,first\nhttps://twitter.com/foo,bad\n", encoding="utf-8")
    rep = validate_input_csv(str(p))
    assert not rep.ok
    txt = rep.format()
    assert "empty value" in txt
    assert "not a valid Instagram URL" in txt


def test_csv_validation_duplicates(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text(
        "url\nhttps://www.instagram.com/jane_doe/\nhttps://www.instagram.com/jane_doe/\n",
        encoding="utf-8",
    )
    rep = validate_input_csv(str(p))
    assert not rep.ok
    assert "duplicate url" in rep.format()


def test_validate_or_raise_raises(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("url\n", encoding="utf-8")  # header only
    with pytest.raises(CsvValidationError):
        validate_or_raise(str(p))


# ---------- Summary report -------------------------------------------------

def test_pipeline_writes_summary_with_reasons_and_locations(tmp_path):
    repo = InMemoryRepository({
        "jane_doe":      make_raw(username="jane_doe"),
        "free_giveaway": make_raw(username="free_giveaway"),
        "tiny_acct":     make_raw(username="tiny_acct", followers=10),
    })
    cfg = PipelineConfig(
        output_dir=str(tmp_path),
        analyzed_path=str(tmp_path / "analyzed.json"),
        csv_path=str(tmp_path / "out.csv"),
        json_path=str(tmp_path / "out.json"),
        ssa_path=None,
        rules=build_rules(min_followers=1000, use_defaults=True),
        repository=repo,
        parallel=False,
    )
    res = run_pipeline(cfg)

    assert res.analyzed_ok == 1
    assert res.analyzed_failed == 2

    # summary files exist next to outputs
    txt_path = res.summary_paths["text"]
    js_path = res.summary_paths["json"]
    assert os.path.exists(txt_path)
    assert os.path.exists(js_path)

    body = json.loads(open(js_path, encoding="utf-8").read())
    assert body["analyzed_ok"] == 1
    assert body["analyzed_failed"] == 2
    # both junk accounts have rule-based filter reasons
    reasons = body["filter_reasons"]
    assert sum(reasons.values()) == 2
    assert ("username_matched_substring" in reasons
            or "below_min_followers" in reasons)
    # exclusion config snapshot is recorded
    assert body["exclusions_applied"]["min_followers"] == 1000


# ---------- Sequential vs parallel toggle ----------------------------------

def test_sequential_flag_runs_in_process(tmp_path):
    """parallel=False must work even without a real on-disk repo path."""
    repo = InMemoryRepository({"jane_doe": make_raw(username="jane_doe")})
    cfg = PipelineConfig(
        output_dir=str(tmp_path),
        analyzed_path=str(tmp_path / "analyzed.json"),
        csv_path=None, json_path=None, ssa_path=None,
        repository=repo, parallel=False,
    )
    res = run_pipeline(cfg)
    assert res.analyzed_ok == 1


def test_summary_stats_format_text_includes_sections():
    s = SummaryStats(
        analyzed_ok=2, analyzed_failed=1,
        top_cities=[("Austin", 2)], top_countries=[("USA", 2)],
        exclusions_applied={"min_followers": 1000},
    )
    text = s.format_text()
    assert "Analyzed OK:     2" in text
    assert "Top cities:" in text
    assert "Austin: 2" in text
    assert "min_followers: 1000" in text
