from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from robotelier.discovery import register_candidate, scan_adapters
from robotelier.integrity import validate_integrity
from robotelier.models import load_records
from robotelier.sources import Candidate, FeedAdapter, MetadataAdapter
from robotelier.utils import ContractError, stable_id
from robotelier.x_research import normalize_x_response

NOW = datetime(2026, 9, 6, 2, 0, tzinfo=UTC)


class FailedAdapter:
    adapter_id = "failed-source"

    def scan(self, *, limit: int) -> list[Any]:
        del limit
        raise TimeoutError("fixture outage")


def candidate(**overrides: object) -> Candidate:
    values: dict[str, object] = {
        "external_id": "announcement-1",
        "url": "https://robotics.example/news/one",
        "title": "Robot update",
        "publisher": "Robotics Example",
        "author": None,
        "language": "de",
        "published_at": "2026-09-06T01:00:00Z",
        "event_at": "2024-03-01T00:00:00Z",
        "source_kind": "company_announcement",
        "origin_url": None,
        "media": [],
    }
    values.update(overrides)
    return Candidate.from_mapping("official-example", values)


def test_feed_adapter_parses_atom_without_retaining_payload() -> None:
    feed = """<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>42</id>
    <title>Neuigkeit</title><link href="https://example.com/post/42"/>
    <published>2026-09-05T10:00:00Z</published></entry></feed>"""
    result = FeedAdapter("official-feed", feed, publisher="Example Lab").scan(limit=2)
    assert result[0].external_id == "42"
    assert result[0].title == "Neuigkeit"
    assert result[0].url == "https://example.com/post/42"


def test_registration_preserves_old_event_date_and_foreign_metadata(repo: Path) -> None:
    result = register_candidate(
        repo,
        candidate(),
        operation_id=stable_id("operation", "discovery"),
        classification="ingest",
        now=NOW,
    )
    source = next(row for row in load_records(repo, "source") if row["id"] == result["source_id"])
    observation = next(
        row for row in load_records(repo, "source_revision") if row["revision_id"] == result["source_revision_id"]
    )
    assert source["language"] == "de"
    assert source["original_title"] == "Robot update"
    assert observation["event_at"] == "2024-03-01T00:00:00Z"
    assert observation["retrieved_at"] == "2026-09-06T02:00:00Z"
    assert observation["content_hash"] is None
    assert observation["hash_scope"] == "none"


def test_media_metadata_is_registered_immediately_and_signed_url_is_omitted(repo: Path) -> None:
    item = candidate(
        media=[
            {
                "media_type": "video",
                "platform": "example",
                "external_media_id": "vid-42",
                "page_url": "https://robotics.example/news/one",
                "direct_asset_url": "https://cdn.example/video.mp4?X-Amz-Signature=secret",
                "rights_status": "unknown",
            }
        ]
    )
    result = register_candidate(
        repo,
        item,
        operation_id=stable_id("operation", "media-discovery"),
        now=NOW,
    )
    assert len(result["media_ids"]) == 1
    media = next(row for row in load_records(repo, "media") if row["id"] == result["media_ids"][0])
    assert media["direct_asset_url"] is None
    assert media["direct_url_status"] == "omitted_signed"
    assert media["source_revision_ids"] == [result["source_revision_id"]]
    assert not validate_integrity(repo)


def test_adapter_failure_is_durable_while_sibling_success_persists(repo: Path) -> None:
    good = MetadataAdapter(
        "good-source",
        [
            {
                "external_id": "good-1",
                "url": "https://example.com/good/1",
                "title": "Good result",
                "publisher": "Example",
                "language": "en",
            }
        ],
    )
    result = scan_adapters(
        repo,
        [FailedAdapter(), good],
        operation_id=stable_id("operation", "mixed-discovery"),
        now=NOW,
    )
    assert [row["status"] for row in result["coverage"]] == ["failed", "succeeded"]
    assert result["registered"]
    failed = json.loads((repo / "data/cursors/failed-source.json").read_text())
    succeeded = json.loads((repo / "data/cursors/good-source.json").read_text())
    assert failed["last_successful_checkpoint"] is None
    assert failed["retry_history"][-1]["reason"] == "TimeoutError"
    assert succeeded["last_successful_checkpoint"] == "2026-09-06T02:00:00Z"


def test_repeated_transport_identity_is_idempotent(repo: Path) -> None:
    operation = stable_id("operation", "repeat")
    first = register_candidate(repo, candidate(), operation_id=operation, now=NOW)
    second = register_candidate(repo, candidate(), operation_id=operation, now=NOW)
    assert first["source_id"] == second["source_id"]
    assert len(load_records(repo, "source")) == 1
    assert len(load_records(repo, "source_revision")) == 1


@pytest.mark.parametrize("degraded", [False, None, True])
def test_uncited_x_answer_is_always_unsourced(degraded: bool | None) -> None:
    result = normalize_x_response(
        {
            "credential_source": "openai-codex",
            "success": True,
            "degraded": degraded,
            "tool_available": True,
            "answer": "Plausible but uncited prose",
            "citations": [],
        },
        query="robotics",
    )
    assert result["status"] == "x_search_unsourced"
    assert result["posts"] == []
    assert result["answer_retained"] is False


def test_x_evidence_requires_openai_codex_and_matching_originating_post() -> None:
    raw = {
        "credential_source": "openai-codex",
        "success": True,
        "degraded": False,
        "tool_available": True,
        "citations": [
            {
                "url": "https://x.com/OfficialBot/status/1234567890",
                "post_id": "1234567890",
                "account": "@OfficialBot",
                "published_at": "2026-09-06T01:02:03Z",
            }
        ],
    }
    result = normalize_x_response(raw, query="from:OfficialBot", account_filter="OfficialBot")
    assert result["status"] == "evidence_available"
    assert result["posts"][0]["url"] == "https://x.com/OfficialBot/status/1234567890"
    with pytest.raises(ContractError, match="openai-codex"):
        normalize_x_response({**raw, "credential_source": "api-key"}, query="robotics")


def test_x_invalid_handle_date_profile_url_and_signed_media_are_not_invented() -> None:
    result = normalize_x_response(
        {
            "credential_source": "openai-codex",
            "tool_available": True,
            "answer": "lead",
            "citations": [
                {"url": "https://x.com/only-a-profile"},
                {"url": "https://x.com/a/status/1", "published_at": "not-a-date"},
                {
                    "url": "https://x.com/b/status/2",
                    "published_at": "2026-09-06T01:00:00Z",
                    "media": [{"direct_asset_url": "https://cdn.example/a.mp4?sig=secret"}],
                },
            ],
        },
        query="robotics",
    )
    assert "citation_not_status_url" in result["invalid_citations"]
    assert "published_at_invalid" in result["invalid_citations"]
    assert result["posts"][0]["media"][0]["direct_asset_url"] is None
    assert result["posts"][0]["media"][0]["direct_url_status"] == "omitted_signed"
