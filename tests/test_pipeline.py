"""End-to-end pipeline + CLI tests using mock adapters & fixtures."""
from __future__ import annotations
import json
import os

from insta_pipeline.adapters.mocks import InMemoryRepository, FakeScraper
from insta_pipeline.application.pipeline_use_case import (
    PipelineConfig, run_pipeline,
)
from insta_pipeline.domain.services.exclusions import build_rules
from insta_pipeline.main import main as cli_main
from insta_pipeline.tests.fixtures import (
    SAMPLE_INPUT_CSV, SAMPLE_PROFILE_HTML, make_raw,
)


def test_sample_html_fixture_has_expected_signals():
    assert "jane_doe" in SAMPLE_PROFILE_HTML
    assert "Followers" in SAMPLE_PROFILE_HTML
    assert "Austin" in SAMPLE_PROFILE_HTML


def test_sample_csv_fixture_parses(tmp_path):
    p = tmp_path / "input.csv"
    p.write_text(SAMPLE_INPUT_CSV, encoding="utf-8")
    lines = p.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0] == "url"
    assert any("jane_doe" in l for l in lines)


def test_fake_scraper_returns_canned_data():
    raw = make_raw(username="alice")
    s = FakeScraper({"https://x/alice": raw})
    out = s.scrape_many(["https://x/alice", "https://x/missing"])
    assert len(out) == 1
    assert out[0].user_info["data"]["user"]["username"] == "alice"


def test_pipeline_with_in_memory_repo_and_exclusions(tmp_path):
    repo = InMemoryRepository({
        "jane_doe": make_raw(username="jane_doe"),
        "free_giveaway": make_raw(username="free_giveaway", bio="join now"),
        "tiny_acct": make_raw(username="tiny_acct", followers=50),
    })
    cfg = PipelineConfig(
        output_dir=str(tmp_path),
        analyzed_path=str(tmp_path / "analyzed.json"),
        csv_path=str(tmp_path / "out.csv"),
        json_path=str(tmp_path / "out.json"),
        ssa_path=None,
        rules=build_rules(min_followers=1000, use_defaults=True),
        repository=repo,
    )
    res = run_pipeline(cfg)

    assert res.analyzed_ok == 1, "only jane_doe should survive exclusions"
    assert res.analyzed_failed == 2
    assert res.csv_rows == 1
    assert res.json_rows == 1

    data = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert data[0]["username"] == "jane_doe"


def test_pipeline_writes_empty_envelope_on_no_targets(tmp_path):
    repo = InMemoryRepository({})
    cfg = PipelineConfig(
        output_dir=str(tmp_path),
        analyzed_path=str(tmp_path / "analyzed.json"),
        csv_path=None, json_path=None, ssa_path=None, repository=repo,
    )
    res = run_pipeline(cfg)
    assert res.analyzed_ok == 0
    body = json.loads((tmp_path / "analyzed.json").read_text())
    assert body["total_creators_analyzed"] == 0


def test_cli_run_command_no_scrape(tmp_path, monkeypatch):
    """`run` without --scrape should analyze + export, no Selenium required."""
    out_dir = tmp_path / "output"
    creator_dir = out_dir / "jane_doe"
    creator_dir.mkdir(parents=True)
    raw = make_raw(username="jane_doe")
    (creator_dir / "userInfo.json").write_text(json.dumps(raw.user_info))
    (creator_dir / "postInfo.json").write_text(json.dumps(raw.post_info))

    rc = cli_main([
        "run",
        "--output-dir", str(out_dir),
        "--analyzed", str(tmp_path / "analyzed.json"),
        "--csv", str(tmp_path / "report.csv"),
        "--json", str(tmp_path / "report.json"),
        "--ssa", "/nonexistent/ssa.txt",
        "--workers", "1",
    ])
    assert rc == 0
    assert os.path.exists(tmp_path / "report.csv")
    rows = json.loads((tmp_path / "report.json").read_text())
    assert rows and rows[0]["username"] == "jane_doe"
