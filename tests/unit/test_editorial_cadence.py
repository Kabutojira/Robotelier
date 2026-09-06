from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from robotelier.cadence import activate, slot_for_date, status
from robotelier.config import load_settings
from robotelier.editorial import calculate_priority, propose, ranked_snapshot, review, select
from robotelier.storage import ConflictError
from robotelier.utils import ContractError, stable_id


def scores(value: int, **modifiers: int) -> dict[str, object]:
    result: dict[str, object] = {}
    for name in (
        "relevance",
        "novelty",
        "significance",
        "timeliness",
        "evidence_readiness",
        "explanatory_value",
    ):
        result[name] = value
        result[f"{name}_rationale"] = f"Fixture rationale for {name}."
    result.update(modifiers)
    return result


def idea_request(
    claim_revision_id: str,
    *,
    key: str,
    duration: int = 700,
    gaps: list[str] | None = None,
) -> dict[str, object]:
    return {
        "originating_operation_id": stable_id("operation", f"idea:{key}"),
        "body": {
            "working_title": f"Fixture idea {key}",
            "listener_question": f"What changed in {key}?",
            "angle": "An evidence-backed fixture angle.",
            "development_ids": [],
            "claim_revision_ids": [claim_revision_id],
            "origin_group_ids": [stable_id("origin", key)],
            "evidence_gaps": gaps or [],
            "outline": [{"section": "evidence", "claim_revision_ids": [claim_revision_id]}],
            "estimated_duration_seconds": duration,
            "novelty_comparison": "Not covered in earlier fixture episodes.",
            "scores": {},
            "reviewed_at": None,
            "revalidate_at": "2026-10-01T00:00:00Z",
        },
    }


def accept_review(repo: Path, idea_id: str, value: int) -> dict[str, object]:
    return review(
        repo,
        {
            "idea_id": idea_id,
            "originating_operation_id": stable_id("operation", f"review:{idea_id}"),
            "scores": scores(value),
            "gates": {
                "dense_enough": True,
                "non_redundant": True,
                "evidence_ready": True,
                "standalone": True,
            },
            "rationale": "Independent fixture review.",
            "reviewed_at": "2026-09-06T03:00:00Z",
        },
    )


def test_priority_formula_is_bounded_monotonic_and_requires_rationale(repo: Path) -> None:
    policy = load_settings(repo).ranking
    low = calculate_priority(scores(1), policy)
    high = calculate_priority(scores(5), policy)
    assert 0 <= low < high <= 100
    assert calculate_priority(scores(5, weekly_urgency=10), policy) == 100
    with pytest.raises(ContractError, match="rationale"):
        calculate_priority({**scores(3), "relevance_rationale": ""}, policy)
    with pytest.raises(ContractError, match="outside"):
        calculate_priority(scores(3, weekly_urgency=11), policy)


def test_lower_scoring_ready_idea_beats_blocked_high_score(repo: Path, evidence_chain: dict[str, object]) -> None:
    claim = evidence_chain["claim"]
    assert isinstance(claim, dict)
    blocked = propose(repo, idea_request(claim["revision_id"], key="blocked", gaps=["Need independent test"]))
    ready = propose(repo, idea_request(claim["revision_id"], key="ready"))
    accept_review(repo, blocked["id"], 5)
    accepted = accept_review(repo, ready["id"], 3)
    snapshot = ranked_snapshot(repo, reference_time="2026-09-06T04:00:00Z")
    assert snapshot["candidates"][0]["idea_revision_id"] == accepted["revision_id"]
    selected = select(repo, local_date="2026-09-06", reference_time="2026-09-06T04:00:00Z")
    assert selected["idea_id"] == ready["id"]


def test_selection_is_one_per_local_date(repo: Path, evidence_chain: dict[str, object]) -> None:
    claim = evidence_chain["claim"]
    assert isinstance(claim, dict)
    first = propose(repo, idea_request(claim["revision_id"], key="first"))
    accept_review(repo, first["id"], 4)
    initial = select(repo, local_date="2026-09-06", reference_time="2026-09-06T04:00:00Z")
    assert select(repo, local_date="2026-09-06", reference_time="2026-09-06T04:01:00Z") == initial
    second = propose(repo, idea_request(claim["revision_id"], key="second"))
    accept_review(repo, second["id"], 5)
    with pytest.raises(ConflictError, match="already owned"):
        select(repo, local_date="2026-09-06", reference_time="2026-09-06T04:02:00Z")


def test_europe_rome_slots_follow_dst_without_fixed_offset(repo: Path) -> None:
    winter = slot_for_date(repo, date(2026, 3, 28))
    summer = slot_for_date(repo, date(2026, 3, 30))
    autumn_summer = slot_for_date(repo, date(2026, 10, 24))
    autumn_winter = slot_for_date(repo, date(2026, 10, 26))
    assert winter["release_at"].endswith("05:00:00Z")
    assert summer["release_at"].endswith("04:00:00Z")
    assert autumn_summer["release_at"].endswith("04:00:00Z")
    assert autumn_winter["release_at"].endswith("05:00:00Z")


def test_activation_anchor_is_immutable_and_weekly_phases_are_local_calendar(repo: Path) -> None:
    activated = activate(repo, now=datetime(2026, 9, 1, 12, tzinfo=UTC))
    repeated = activate(repo, now=datetime(2026, 9, 5, 12, tzinfo=UTC))
    assert repeated == activated
    assert status(repo, now=datetime(2026, 9, 5, 12, tzinfo=UTC))["phase"] == "prepare_weekly_candidate"
    assert status(repo, now=datetime(2026, 9, 6, 12, tzinfo=UTC))["phase"] == "evidence_priority"
    assert status(repo, now=datetime(2026, 9, 7, 12, tzinfo=UTC))["phase"] == "outline_due"
    assert status(repo, now=datetime(2026, 9, 8, 12, tzinfo=UTC))["phase"] == "cadence_breach"


def test_listener_release_anchor_uses_acknowledged_audio_not_transcript(repo: Path) -> None:
    activate(repo, now=datetime(2026, 9, 1, 12, tzinfo=UTC))
    outbox = repo / "data/published/outbox/2026-09-04.json"
    outbox.parent.mkdir(parents=True, exist_ok=True)
    outbox.write_text(
        json.dumps(
            {
                "telegram_audio": {"state": "acknowledged", "acknowledged_at": "2026-09-04T04:00:00Z"},
                "transcript": {"state": "committed"},
            }
        )
    )
    current = status(repo, now=datetime(2026, 9, 8, 12, tzinfo=UTC))
    assert current["last_listener_release_date"] == "2026-09-04"
    assert current["days_since_anchor"] == 4
