from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from robotelier.knowledge import build_wiki, render_page
from robotelier.provenance import register_revision
from robotelier.utils import stable_id

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    root.mkdir()
    for name in ("AGENTS.md", "PLAN.md", "config.ini"):
        shutil.copy2(PROJECT_ROOT / name, root / name)
    shutil.copytree(PROJECT_ROOT / "schemas", root / "schemas")
    shutil.copytree(PROJECT_ROOT / "skills", root / "skills")
    shutil.copytree(PROJECT_ROOT / "data", root / "data")
    for generated in (
        root / "data" / "published" / "reference-index.json",
        root / "data" / "wiki" / "_meta" / "catalog.json",
    ):
        generated.unlink(missing_ok=True)
    return root


@pytest.fixture
def evidence_chain(repo: Path) -> dict[str, Any]:
    operation_id = stable_id("operation", "fixture-research")
    entity_id = stable_id("entity_robot_version", "fixturebot:v2")
    entity = register_revision(
        repo,
        {
            "record_type": "entity",
            "id": entity_id,
            "originating_operation_id": operation_id,
            "created_at": "2026-09-01T10:00:00Z",
            "body": {
                "entity_type": "robot_version",
                "display_name": "FixtureBot 2",
                "aliases": [{"name": "FixtureBot v2", "language": "en"}],
                "canonical_urls": ["https://example.com/robots/fixturebot-2"],
                "external_ids": {"maker": "fixturebot-2"},
                "parent_ids": [],
                "lifecycle": "demonstrated_system",
                "planned_availability": None,
                "actual_availability": None,
                "review_at": "2026-12-01T00:00:00Z",
                "wiki_path": f"data/wiki/robots/{entity_id}.md",
            },
        },
    )
    source_id = stable_id("source", "fixture-maker-announcement")
    source = register_revision(
        repo,
        {
            "record_type": "source",
            "id": source_id,
            "originating_operation_id": operation_id,
            "created_at": "2026-09-01T10:01:00Z",
            "body": {
                "canonical_url": "https://example.com/news/fixturebot-test",
                "discovered_url": "https://example.com/news/fixturebot-test",
                "publisher": "Fixture Robotics",
                "author": None,
                "original_title": "FixtureBot completes a supervised bin-picking trial",
                "language": "en",
                "platform": "official_site",
                "stable_external_id": "announcement-42",
                "source_kind": "company_announcement",
                "origin_group_id": stable_id("origin", "fixture-announcement-42"),
                "original_source_url": None,
            },
        },
    )
    observation_id = stable_id("source_revision", "fixture-observation")
    observation = register_revision(
        repo,
        {
            "record_type": "source_revision",
            "id": observation_id,
            "originating_operation_id": operation_id,
            "created_at": "2026-09-01T10:02:00Z",
            "body": {
                "source_id": source_id,
                "published_at": "2026-09-01T09:00:00Z",
                "event_at": "2026-08-29T00:00:00Z",
                "modified_at": None,
                "retrieved_at": "2026-09-01T10:02:00Z",
                "date_precision": "second",
                "access_status": "inspected",
                "retrieval_method": "fixture_text",
                "effective_url": "https://example.com/news/fixturebot-test",
                "content_hash": "1" * 64,
                "hash_scope": "extracted_text",
                "retained_excerpt": None,
                "english_summary": "The maker reports a supervised ten-trial bin-picking test.",
                "observation_id": observation_id,
            },
        },
    )
    evidence_id = stable_id("evidence", "fixture-paragraph-3")
    evidence = register_revision(
        repo,
        {
            "record_type": "evidence",
            "id": evidence_id,
            "originating_operation_id": operation_id,
            "created_at": "2026-09-01T10:03:00Z",
            "body": {
                "source_revision_id": observation["revision_id"],
                "locator": {"coordinate_system": "section_paragraph", "value": "Results, paragraph 3"},
                "support": "The maker reported nine successes in ten supervised attempts.",
                "support_kind": "paraphrase",
                "context": "The announcement does not establish fully autonomous operation.",
                "evidence_type": "maker_statement",
                "access_level": "inspected_text",
            },
        },
    )
    claim_id = stable_id("claim", "fixturebot-successes")
    claim = register_revision(
        repo,
        {
            "record_type": "claim",
            "id": claim_id,
            "originating_operation_id": operation_id,
            "created_at": "2026-09-01T10:04:00Z",
            "body": {
                "subject_id": entity_id,
                "predicate": "reported_successes",
                "value": 9,
                "units": "successful_attempts_of_10",
                "conditions": {
                    "task": "bin picking",
                    "environment": "maker test cell",
                    "autonomy": "unknown",
                    "human_assistance": "supervised",
                    "configuration": "FixtureBot 2",
                },
                "valid_at": "2026-08-29T00:00:00Z",
                "modality": "asserted",
                "epistemic_status": "maker_claim",
                "supporting_evidence_ids": [evidence["revision_id"]],
                "contradicting_evidence_ids": [],
                "confidence_rationale": "Direct maker statement; no independent test was inspected.",
                "origin_group_ids": [source["origin_group_id"]],
                "premise_claim_revision_ids": [],
                "review_at": "2026-10-01T00:00:00Z",
            },
        },
    )
    page_path = repo / "data" / "wiki" / "robots" / f"{entity_id}.md"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text(
        render_page(
            title="FixtureBot 2",
            page_type="robot",
            created_date="2026-09-01",
            entity_ids=[entity_id],
            claim_revision_ids=[claim["revision_id"]],
            evidence_revision_ids=[evidence["revision_id"]],
            body_sections=[
                {
                    "heading": "Reported test",
                    "claim_revision_ids": [claim["revision_id"]],
                    "text": (
                        "Fixture Robotics reported nine successes in ten supervised attempts "
                        "([source](https://example.com/news/fixturebot-test)). Autonomy was not established."
                    ),
                }
            ],
        ),
        encoding="utf-8",
    )
    build_wiki(repo)
    return {
        "operation_id": operation_id,
        "entity": entity,
        "source": source,
        "observation": observation,
        "evidence": evidence,
        "claim": claim,
        "wiki_path": page_path,
    }
