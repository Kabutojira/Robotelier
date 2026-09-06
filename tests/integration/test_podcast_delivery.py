from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from robotelier.editorial import propose, review
from robotelier.operations import claim as claim_operation
from robotelier.operations import enqueue, finish
from robotelier.podcast import (
    PodcastError,
    freeze,
    pre_release_errors,
    render_temporary,
    save_script_draft,
    seal_script,
    validate_segments,
)
from robotelier.provenance import register_revision, trace
from robotelier.publication import commit_transcript, reserve
from robotelier.telegram import TelegramError, deliver_audio, deliver_text, reconcile
from robotelier.utils import content_hash, stable_id


def _scores() -> dict[str, object]:
    result: dict[str, object] = {}
    for name in (
        "relevance",
        "novelty",
        "significance",
        "timeliness",
        "evidence_readiness",
        "explanatory_value",
    ):
        result[name] = 4
        result[f"{name}_rationale"] = "Supported by the frozen fixture chain."
    return result


def reviewed_episode(repo: Path, evidence_chain: dict[str, Any]) -> dict[str, Any]:
    claim = evidence_chain["claim"]
    idea = propose(
        repo,
        {
            "originating_operation_id": stable_id("operation", "episode-idea"),
            "body": {
                "working_title": "What the FixtureBot test does and does not show",
                "listener_question": "What can a supervised bin-picking trial establish?",
                "angle": "Separate the maker's result from unsupported autonomy conclusions.",
                "development_ids": [],
                "claim_revision_ids": [claim["revision_id"]],
                "origin_group_ids": claim["origin_group_ids"],
                "evidence_gaps": [],
                "outline": [{"section": "reported result", "claim_revision_ids": [claim["revision_id"]]}],
                "estimated_duration_seconds": 700,
                "novelty_comparison": "No earlier fixture episode covers this result.",
                "scores": {},
                "reviewed_at": None,
                "revalidate_at": "2026-10-01T00:00:00Z",
            },
        },
    )
    ready = review(
        repo,
        {
            "idea_id": idea["id"],
            "originating_operation_id": stable_id("operation", "episode-idea-review"),
            "scores": _scores(),
            "gates": {
                "dense_enough": True,
                "non_redundant": True,
                "evidence_ready": True,
                "standalone": True,
            },
            "rationale": "Fixture independent editorial review.",
            "reviewed_at": "2026-09-06T03:00:00Z",
        },
    )
    package = freeze(
        repo,
        {
            "idea_revision_id": ready["revision_id"],
            "intended_local_date": "2026-09-06",
            "source_commit": "a" * 40,
            "originating_operation_id": stable_id("operation", "freeze"),
            "research_cutoff": "2026-09-06T03:30:00Z",
        },
    )
    writer = enqueue(
        repo,
        {
            "operation_type": "podcast_write",
            "dedupe_key": "fixture-podcast-writer",
            "prompt": "Write from frozen evidence.",
            "priority": 100,
        },
    )
    writer_lease = claim_operation(repo, run_id="writer-run", cycle_id="episode-cycle", profile="editorial")
    assert writer_lease and writer_lease["operation_id"] == writer["operation_id"]
    segments = [
        {
            "segment_id": "opening",
            "role": "greeting",
            "spoken_text": "Today, we are separating a reported robotics result from a broader conclusion.",
            "claim_revision_ids": [],
            "media_candidates": [],
        },
        {
            "segment_id": "reported-test",
            "role": "factual",
            "spoken_text": (
                "Fixture Robotics reported nine successes in ten supervised bin-picking attempts. "
                "Its announcement did not establish fully autonomous operation."
            ),
            "claim_revision_ids": [claim["revision_id"]],
            "media_candidates": [],
        },
        {
            "segment_id": "close",
            "role": "conclusion",
            "spoken_text": "That distinction is the useful result: evidence first, interpretation second.",
            "claim_revision_ids": [],
            "media_candidates": [],
        },
    ]
    draft = save_script_draft(
        repo,
        {
            "episode_id": package["episode_id"],
            "bundle_hash": package["bundle_hash"],
            "segments": segments,
            "show_notes": "A maker-reported supervised test, with its limits made explicit.",
            "originating_operation_id": writer["operation_id"],
        },
    )
    with pytest.raises(PodcastError, match="reviewer"):
        seal_script(
            repo,
            {
                "episode_id": package["episode_id"],
                "bundle_hash": package["bundle_hash"],
                "draft_hash": draft["draft_hash"],
                "review": {"accepted": True},
                "originating_operation_id": writer["operation_id"],
            },
        )
    finish(
        repo,
        operation_id=writer["operation_id"],
        lease_token=writer_lease["lease_token"],
        outcome="succeeded",
        reason_code=None,
        result={"draft_hash": draft["draft_hash"]},
    )
    reviewer = enqueue(
        repo,
        {
            "operation_type": "podcast_review",
            "dedupe_key": "fixture-podcast-reviewer",
            "prompt": "Review exact draft.",
            "priority": 100,
        },
    )
    reviewer_lease = claim_operation(repo, run_id="review-run", cycle_id="episode-cycle", profile="deep")
    assert reviewer_lease and reviewer_lease["operation_id"] == reviewer["operation_id"]
    episode = seal_script(
        repo,
        {
            "episode_id": package["episode_id"],
            "bundle_hash": package["bundle_hash"],
            "draft_hash": draft["draft_hash"],
            "originating_operation_id": reviewer["operation_id"],
            "review": {
                "accepted": True,
                "factual_support": True,
                "attribution": True,
                "listening_quality": True,
                "novelty": True,
                "density": True,
                "findings": [],
            },
        },
    )
    return {**episode, "package": package, "draft": draft, "reviewer_lease": reviewer_lease}


def test_writer_reviewer_separation_and_full_segment_trace(repo: Path, evidence_chain: dict[str, Any]) -> None:
    episode = reviewed_episode(repo, evidence_chain)
    claim = evidence_chain["claim"]
    nodes = cast(dict[str, Any], trace(repo, episode["revision_id"])["nodes"])
    assert claim["revision_id"] in nodes
    assert evidence_chain["evidence"]["revision_id"] in nodes
    assert evidence_chain["observation"]["revision_id"] in nodes
    assert episode["review_revision_id"] in nodes
    assert episode["script_revision_id"] in nodes
    assert (repo / episode["transcript_path"]).read_text().endswith("\n")
    assert "https://example.com/news/fixturebot-test" in (repo / episode["show_notes_path"]).read_text()


def test_script_rejects_unfrozen_fact_and_source_timing_confusion(repo: Path, evidence_chain: dict[str, Any]) -> None:
    episode = reviewed_episode(repo, evidence_chain)
    package = json.loads((repo / episode["package"]["bundle_path"]).read_text())
    bad = [
        {
            "segment_id": "bad",
            "role": "factual",
            "spoken_text": "An unsupported plausible fact.",
            "claim_revision_ids": ["rev_" + "f" * 20],
            "media_candidates": [
                {
                    "media_id": stable_id("media", "unknown"),
                    "coordinate_system": "episode_audio_time",
                    "start_seconds": 1,
                    "end_seconds": 2,
                }
            ],
        }
    ]
    errors = validate_segments(package, bad)
    assert any("absent from frozen package" in error for error in errors)
    assert any("source-media coordinates" in error for error in errors)


def test_material_claim_correction_blocks_release(repo: Path, evidence_chain: dict[str, Any]) -> None:
    episode = reviewed_episode(repo, evidence_chain)
    claim = evidence_chain["claim"]
    body = {
        key: value
        for key, value in claim.items()
        if key
        not in {
            "schema_version",
            "record_type",
            "id",
            "revision_id",
            "created_at",
            "originating_operation_id",
            "supersedes",
            "status",
            "path",
            "receipt",
        }
    }
    body["value"] = 8
    replacement = register_revision(
        repo,
        {
            "record_type": "claim",
            "id": claim["id"],
            "originating_operation_id": stable_id("operation", "correction"),
            "supersedes": claim["revision_id"],
            "body": body,
        },
    )
    errors = pre_release_errors(repo, episode)
    assert any(replacement["revision_id"] in error for error in errors)
    with pytest.raises(PodcastError, match="superseded"):
        render_temporary(repo, episode_id=episode["id"], render_id="blocked")


def test_render_is_script_bound_measured_and_always_cleaned(repo: Path, evidence_chain: dict[str, Any]) -> None:
    episode = reviewed_episode(repo, evidence_chain)
    observed: dict[str, object] = {}

    def synth(text: str, output: Path, voice: str, timeout: int) -> None:
        assert text and voice == "en-US-AriaNeural" and timeout > 0
        output.write_bytes(b"fixture-mp3")
        observed["path"] = output

    def delivery(path: Path, metadata: dict[str, Any]) -> dict[str, str]:
        assert path.is_file()
        assert metadata["transcript_hash"] == episode["transcript_hash"]
        return {"state": "acknowledged"}

    render = render_temporary(
        repo,
        episode_id=episode["id"],
        render_id="first",
        synthesizer=synth,
        duration_probe=lambda _: 700.25,
        deliver=delivery,
    )
    assert render["status"] == "validated"
    assert render["duration_seconds"] == 700.25
    assert render["cleanup_observed"] is True
    assert not Path(str(observed["path"])).exists()
    assert all(item["coordinate_system"] == "episode_audio_time" for item in render["timings"])
    assert "path" not in " ".join(render)


def test_out_of_range_and_synthesis_failure_record_metadata_without_media(
    repo: Path, evidence_chain: dict[str, Any]
) -> None:
    episode = reviewed_episode(repo, evidence_chain)
    paths: list[Path] = []

    def synth(_: str, output: Path, __: str, ___: int) -> None:
        output.write_bytes(b"temporary")
        paths.append(output)

    with pytest.raises(PodcastError, match="outside"):
        render_temporary(
            repo,
            episode_id=episode["id"],
            render_id="short",
            synthesizer=synth,
            duration_probe=lambda _: 599.9,
        )
    failed = json.loads((repo / f"data/records/episodes/{episode['id']}/artifacts/render-short.json").read_text())
    assert failed["status"] == "failed"
    assert failed["cleanup_observed"] is True
    assert all(not path.exists() for path in paths)


def _published(repo: Path, episode: dict[str, Any]) -> str:
    reserve(repo, episode_id=episode["id"], local_date="2026-09-06")
    commit_transcript(repo, episode_id=episode["id"], local_date="2026-09-06", source_commit="a" * 40)
    return cast(str, (repo / episode["transcript_path"]).read_text())


def test_telegram_text_exact_hash_and_ambiguous_delivery_blocks_replay(
    repo: Path, evidence_chain: dict[str, Any]
) -> None:
    episode = reviewed_episode(repo, evidence_chain)
    text = _published(repo, episode)
    with pytest.raises(TelegramError, match="does not match"):
        deliver_text(
            repo,
            local_date="2026-09-06",
            text=text + "changed",
            token="fixture",
            chat_id="fixture",
            sender=lambda *_: {"ok": True},
        )

    def timeout(*_: object) -> dict[str, Any]:
        raise TimeoutError

    state = deliver_text(
        repo,
        local_date="2026-09-06",
        text=text,
        token="fixture",
        chat_id="fixture",
        sender=timeout,
    )
    assert state["state"] == "delivery_unknown"
    with pytest.raises(TelegramError, match="cannot be retried"):
        deliver_text(
            repo,
            local_date="2026-09-06",
            text=text,
            token="fixture",
            chat_id="fixture",
            sender=timeout,
        )
    reconciled = reconcile(
        repo,
        {
            "local_date": "2026-09-06",
            "channel": "telegram_text",
            "resolution": "acknowledged",
            "message_ids": [42],
        },
    )
    assert reconciled["state"] == "acknowledged"


def test_telegram_audio_definitive_failure_then_safe_new_attempt(
    repo: Path, evidence_chain: dict[str, Any], tmp_path: Path
) -> None:
    episode = reviewed_episode(repo, evidence_chain)
    _published(repo, episode)
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"audio")
    metadata = {
        "render_id": "render-one",
        "audio_sha256": content_hash(b"audio"),
        "audio_bytes": 5,
        "mime_type": "audio/mpeg",
        "transcript_hash": episode["transcript_hash"],
    }

    def rejected(*_: object) -> dict[str, Any]:
        raise TelegramError("known rejection")

    first = deliver_audio(
        repo,
        local_date="2026-09-06",
        audio_path=audio,
        metadata=metadata,
        token="fixture",
        chat_id="fixture",
        sender=rejected,
    )
    assert first["state"] == "failed"
    second = deliver_audio(
        repo,
        local_date="2026-09-06",
        audio_path=audio,
        metadata={**metadata, "render_id": "render-two"},
        token="fixture",
        chat_id="fixture",
        sender=lambda *_: {"ok": True, "result": {"message_id": 7}},
    )
    assert second["state"] == "acknowledged"
    assert second["attempt_count"] == 2


def test_post_send_receipt_failure_remains_reconciliation_required(
    repo: Path, evidence_chain: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    episode = reviewed_episode(repo, evidence_chain)
    text = _published(repo, episode)
    import robotelier.telegram as telegram_module

    real_update: Any = telegram_module.update_channel  # type: ignore[attr-defined]
    calls = 0

    def fail_after_intent(*args: object, **kwargs: object) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        if calls > 1:
            raise OSError("fixture receipt disk failure")
        return cast(dict[str, Any], real_update(*args, **kwargs))

    monkeypatch.setattr(telegram_module, "update_channel", fail_after_intent)
    with pytest.raises(TelegramError, match="receipt commit failed"):
        deliver_text(
            repo,
            local_date="2026-09-06",
            text=text,
            token="fixture",
            chat_id="fixture",
            sender=lambda *_: {"ok": True, "result": {"message_id": 9}},
        )
    outbox = json.loads((repo / "data/published/outbox/2026-09-06.json").read_text())
    assert outbox["telegram_text"]["state"] == "intent_written"
