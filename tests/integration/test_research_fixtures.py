from __future__ import annotations

import json
from pathlib import Path

from robotelier.discovery import scan_adapters
from robotelier.models import load_records
from robotelier.sources import FixtureAdapter
from robotelier.utils import stable_id

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_synthetic_discovery_fixture_preserves_origins_versions_dates_and_media(repo: Path) -> None:
    result = scan_adapters(
        repo,
        [FixtureAdapter("synthetic-global", FIXTURES / "discovery_cases.json")],
        operation_id=stable_id("operation", "synthetic-discovery"),
    )
    assert len(result["registered"]) == 5
    sources = load_records(repo, "source")
    reports = [row for row in sources if row["source_kind"] == "secondary_report"]
    announcement = next(row for row in sources if row["source_kind"] == "company_announcement")
    assert len(reports) == 2
    assert {row["origin_group_id"] for row in reports} == {announcement["origin_group_id"]}
    repost = next(row for row in sources if row["source_kind"] == "repost")
    assert repost["original_source_url"] == "https://fixture.example/demos/2024-unit"
    observations = load_records(repo, "source_revision")
    old = next(row for row in observations if row["source_id"] == repost["id"])
    assert old["event_at"] == "2024-03-01T00:00:00Z"
    media = load_records(repo, "media")[0]
    assert media["direct_asset_url"] is None
    assert media["original_creator"] is None
    assert media["context"]["source_time_ranges"][0]["coordinate_system"] == "source_media_time"
    independent = next(row for row in sources if row["source_kind"] == "independent_test")
    assert independent["language"] == "ja"


def test_semantic_fixture_expected_failures_are_explicit() -> None:
    cases = json.loads((FIXTURES / "semantic_cases.json").read_text())
    rejected = [case for case in cases if case["expected"] == "reject"]
    assert {case["reason_code"] for case in rejected} == {
        "unsupported_clause",
        "self_citation",
        "missing_conditions",
        "too_thin",
    }
    assert all(case.get("reason_code") for case in rejected)
