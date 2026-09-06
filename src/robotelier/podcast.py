"""Frozen evidence, canonical scripts and temporary script-bound TTS."""

from __future__ import annotations

import json
import mimetypes
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from robotelier.config import load_settings
from robotelier.models import build_revision, load_records, record_path, validate_document
from robotelier.operations import all_operations, enqueue
from robotelier.provenance import rebuild_indexes
from robotelier.storage import ConflictError, Transaction, atomic_write_json
from robotelier.utils import (
    ContractError,
    content_hash,
    format_timestamp,
    stable_id,
    utc_now,
    words,
)


class PodcastError(ContractError):
    pass


def _episode_directory(root: Path, episode_id: str) -> Path:
    return root / "data" / "records" / "episodes" / episode_id


def freeze(root: Path, request: dict[str, Any]) -> dict[str, Any]:
    required = {
        "idea_revision_id",
        "intended_local_date",
        "source_commit",
        "originating_operation_id",
    }
    missing = sorted(required - set(request))
    if missing:
        raise PodcastError(f"freeze request missing fields: {missing}")
    ideas = {row["revision_id"]: row for row in load_records(root, "idea")}
    idea = ideas.get(request["idea_revision_id"])
    if idea is None or idea.get("state") not in {"ready", "reserved"}:
        raise PodcastError("selected idea revision is not ready")
    gates = idea.get("gates", {})
    if not all(gates.get(key) is True for key in ("dense_enough", "non_redundant", "evidence_ready", "standalone")):
        raise PodcastError("selected idea has incomplete outline gates")
    claims_by_revision = {row["revision_id"]: row for row in load_records(root, "claim")}
    evidence_by_revision = {row["revision_id"]: row for row in load_records(root, "evidence")}
    source_revisions = {row["revision_id"]: row for row in load_records(root, "source_revision")}
    sources = {row["id"]: row for row in load_records(root, "source")}
    claims: list[dict[str, Any]] = []
    evidence: dict[str, dict[str, Any]] = {}
    observations: dict[str, dict[str, Any]] = {}
    source_identities: dict[str, dict[str, Any]] = {}
    for revision_id in idea["claim_revision_ids"]:
        claim = claims_by_revision.get(revision_id)
        if claim is None:
            raise PodcastError(f"idea references missing claim: {revision_id}")
        claims.append(claim)
        for evidence_id in claim.get("supporting_evidence_ids", []):
            item = evidence_by_revision.get(evidence_id)
            if item is None:
                raise PodcastError(f"claim references missing evidence: {evidence_id}")
            evidence[evidence_id] = item
            observation = source_revisions.get(item["source_revision_id"])
            if observation is None:
                raise PodcastError(f"evidence references missing source observation: {evidence_id}")
            observations[observation["revision_id"]] = observation
            identity = sources.get(observation["source_id"])
            if identity is None:
                raise PodcastError(f"source observation lacks source identity: {observation['revision_id']}")
            source_identities[identity["id"]] = identity
    wiki_revisions: list[dict[str, str]] = []
    for path in sorted((root / "data" / "wiki").rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        if any(revision in text for revision in idea["claim_revision_ids"]):
            wiki_revisions.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "sha256": content_hash(text),
                }
            )
    bundle_body = {
        "schema_version": 1,
        "idea_revision": idea,
        "claims": claims,
        "evidence": [evidence[key] for key in sorted(evidence)],
        "source_revisions": [observations[key] for key in sorted(observations)],
        "sources": [source_identities[key] for key in sorted(source_identities)],
        "wiki_revisions": wiki_revisions,
        "coverage_comparison": request.get("coverage_comparison", {}),
        "outline": idea["outline"],
        "editorial_review": {
            "gates": gates,
            "scores": idea.get("scores", {}),
            "reviewed_at": idea.get("reviewed_at"),
        },
        "research_cutoff": request.get("research_cutoff") or format_timestamp(utc_now()),
        "known_limitations": request.get("known_limitations", idea.get("evidence_gaps", [])),
        "language": "en",
        "voice": load_settings(root).podcast.voice,
        "intended_local_date": request["intended_local_date"],
        "source_commit": request["source_commit"],
        "policy_versions": {"editorial": load_settings(root).ranking.policy_version, "freeze": 1},
    }
    bundle_hash = content_hash(bundle_body)
    episode_id = stable_id("episode", f"{request['intended_local_date']}:{request['idea_revision_id']}")
    path = _episode_directory(root, episode_id) / "artifacts" / f"frozen-{bundle_hash}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and json.loads(path.read_text(encoding="utf-8")) != bundle_body:
        raise ConflictError("frozen package hash collision")
    if not path.exists():
        atomic_write_json(path, bundle_body, allowed_root=root)
    return {
        "episode_id": episode_id,
        "bundle_hash": bundle_hash,
        "bundle_path": path.relative_to(root).as_posix(),
        "source_commit": request["source_commit"],
    }


def prepare_selected_episode(root: Path, *, local_date: str) -> dict[str, Any]:
    selection_path = root / "data" / "history" / "editorial-selections" / f"{local_date}.json"
    if not selection_path.is_file() or selection_path.is_symlink():
        return {"status": "no_selection", "local_date": local_date}
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    if not isinstance(selection, dict) or not selection.get("idea_revision_id"):
        return {"status": "no_selection", "local_date": local_date}
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    source_commit = head.stdout.strip()
    if head.returncode != 0 or len(source_commit) != 40:
        raise PodcastError("selected evidence must be frozen from a committed Git revision")
    operation_id = stable_id("operation", f"controller-freeze:{local_date}:{source_commit}")
    package = freeze(
        root,
        {
            "idea_revision_id": selection["idea_revision_id"],
            "intended_local_date": local_date,
            "source_commit": source_commit,
            "originating_operation_id": operation_id,
            "research_cutoff": format_timestamp(utc_now()),
        },
    )
    writer = enqueue(
        root,
        {
            "operation_type": "podcast_write",
            "dedupe_key": f"episode:{package['episode_id']}:{package['bundle_hash']}:write",
            "priority": 100,
            "prompt": (
                "Write one English single-narrator script using only the frozen evidence bundle. "
                "Submit a canonical draft for independent review; do not browse or render."
            ),
            "inputs": package,
            "idea_ids": [selection["idea_id"]],
        },
    )
    return {
        "status": "writer_queued",
        "local_date": local_date,
        "package": package,
        "writer_operation_id": writer["operation_id"],
    }


def load_bundle(root: Path, episode_id: str, bundle_hash: str) -> dict[str, Any]:
    path = _episode_directory(root, episode_id) / "artifacts" / f"frozen-{bundle_hash}.json"
    if not path.is_file() or path.is_symlink():
        raise PodcastError("frozen package is missing")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PodcastError("frozen package must be an object")
    if content_hash(value) != bundle_hash:
        raise PodcastError("frozen package hash mismatch")
    for item in value.get("wiki_revisions", []):
        source = root / item["path"]
        if not source.is_file():
            raise PodcastError(f"frozen wiki source disappeared: {item['path']}")
        # Later wiki changes are allowed; the package preserves its original hash and content links.
    return value


def validate_segments(bundle: dict[str, Any], segments: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    allowed_claims = {row["revision_id"] for row in bundle.get("claims", [])}
    segment_ids: set[str] = set()
    for index, segment in enumerate(segments):
        segment_id = segment.get("segment_id")
        role = segment.get("role")
        text = segment.get("spoken_text")
        claims = segment.get("claim_revision_ids")
        if not isinstance(segment_id, str) or not segment_id or segment_id in segment_ids:
            errors.append(f"segment {index}: missing or duplicate stable ID")
        else:
            segment_ids.add(segment_id)
        if role not in {"factual", "greeting", "transition", "conclusion", "correction"}:
            errors.append(f"segment {segment_id}: invalid semantic role")
        if not isinstance(text, str) or not text.strip():
            errors.append(f"segment {segment_id}: spoken text is empty")
        if not isinstance(claims, list):
            errors.append(f"segment {segment_id}: claim_revision_ids must be an array")
            continue
        if role == "factual" and not claims:
            errors.append(f"segment {segment_id}: factual segment has no claim references")
        if role != "factual" and claims:
            errors.append(f"segment {segment_id}: nonfactual segment cannot carry factual claims")
        missing = sorted(set(claims) - allowed_claims)
        if missing:
            errors.append(f"segment {segment_id}: claims absent from frozen package: {missing}")
        for candidate in segment.get("media_candidates", []):
            if not isinstance(candidate, dict):
                errors.append(f"segment {segment_id}: media candidate must be an object")
                continue
            coordinate = candidate.get("coordinate_system")
            has_range = any(key in candidate for key in ("start_seconds", "end_seconds", "time_range"))
            if coordinate not in {None, "source_media_time"} or (has_range and coordinate != "source_media_time"):
                errors.append(f"segment {segment_id}: media candidate must use source-media coordinates")
    return errors


def _transcript(segments: list[dict[str, Any]]) -> str:
    return "\n\n".join(str(segment["spoken_text"]).strip() for segment in segments).strip() + "\n"


def _show_notes(bundle: dict[str, Any], supplied: str) -> str:
    lines = [supplied.strip(), "", "## Sources", ""]
    for source in bundle.get("sources", []):
        qualification = ""
        if source.get("source_kind") in {"company_announcement", "official_post"}:
            qualification = " — maker statement"
        lines.append(f"- [{source['original_title']}]({source['canonical_url']}){qualification}")
    return "\n".join(lines).strip() + "\n"


def save_script_draft(root: Path, request: dict[str, Any]) -> dict[str, Any]:
    required = {"episode_id", "bundle_hash", "segments", "show_notes", "originating_operation_id"}
    missing = sorted(required - set(request))
    if missing:
        raise PodcastError(f"script draft request missing fields: {missing}")
    operation = all_operations(root).get(str(request["originating_operation_id"]))
    if operation is None or operation.get("operation_type") != "podcast_write" or operation.get("state") != "leased":
        raise PodcastError("script drafts may only be submitted by the actively leased podcast writer")
    bundle = load_bundle(root, request["episode_id"], request["bundle_hash"])
    segments = request["segments"]
    if not isinstance(segments, list):
        raise PodcastError("segments must be an array")
    errors = validate_segments(bundle, segments)
    if errors:
        raise PodcastError("; ".join(errors))
    body = {
        "schema_version": 1,
        "episode_id": request["episode_id"],
        "bundle_hash": request["bundle_hash"],
        "writer_operation_id": request["originating_operation_id"],
        "segments": segments,
        "show_notes": str(request["show_notes"]),
        "repair_round": int(request.get("repair_round", 0)),
        "created_at": format_timestamp(utc_now()),
    }
    if body["repair_round"] not in {0, 1, 2}:
        raise PodcastError("script draft exceeds two editorial repair rounds")
    draft_hash = content_hash(body)
    body["draft_id"] = stable_id("draft", draft_hash)
    script_document = build_revision(
        record_type="script",
        identity=body["draft_id"],
        originating_operation_id=request["originating_operation_id"],
        created_at=body["created_at"],
        body={
            "episode_id": request["episode_id"],
            "frozen_bundle_hash": request["bundle_hash"],
            "writer_operation_id": request["originating_operation_id"],
            "segments": segments,
            "show_notes": str(request["show_notes"]),
            "repair_round": body["repair_round"],
            "draft_hash": draft_hash,
            "status": "pending_review",
        },
    )
    validate_document(root, script_document)
    body["script_revision_id"] = script_document["revision_id"]
    path = _episode_directory(root, request["episode_id"]) / "artifacts" / f"draft-{draft_hash}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    transaction = Transaction(root, transaction_id=script_document["revision_id"])
    transaction.write_json(record_path(root, script_document).relative_to(root).as_posix(), script_document)
    transaction.write_json(path.relative_to(root).as_posix(), body)
    transaction.commit()
    return {
        "status": "drafted",
        "episode_id": request["episode_id"],
        "draft_hash": draft_hash,
        "draft_id": body["draft_id"],
        "script_revision_id": script_document["revision_id"],
        "path": path.relative_to(root).as_posix(),
    }


def _load_script_draft(root: Path, episode_id: str, draft_hash: str) -> dict[str, Any]:
    path = _episode_directory(root, episode_id) / "artifacts" / f"draft-{draft_hash}.json"
    if not path.is_file() or path.is_symlink():
        raise PodcastError("script draft is missing")
    draft = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(draft, dict):
        raise PodcastError("script draft must be an object")
    material = {key: value for key, value in draft.items() if key not in {"draft_id", "script_revision_id"}}
    if content_hash(material) != draft_hash:
        raise PodcastError("script draft hash mismatch")
    return draft


def seal_script(root: Path, request: dict[str, Any]) -> dict[str, Any]:
    required = {
        "episode_id",
        "bundle_hash",
        "draft_hash",
        "review",
        "originating_operation_id",
    }
    missing = sorted(required - set(request))
    if missing:
        raise PodcastError(f"script request missing fields: {missing}")
    bundle = load_bundle(root, request["episode_id"], request["bundle_hash"])
    draft = _load_script_draft(root, request["episode_id"], request["draft_hash"])
    if draft["bundle_hash"] != request["bundle_hash"]:
        raise PodcastError("script draft is bound to a different frozen package")
    reviewer_operation_id = str(request["originating_operation_id"])
    review_operation = all_operations(root).get(reviewer_operation_id)
    if (
        review_operation is None
        or review_operation.get("operation_type") != "podcast_review"
        or review_operation.get("state") != "leased"
    ):
        raise PodcastError("only an actively leased independent podcast reviewer may seal a script")
    if draft["writer_operation_id"] == reviewer_operation_id:
        raise PodcastError("podcast writer and independent reviewer must be different operations")
    segments = draft["segments"]
    errors = validate_segments(bundle, segments)
    review = request["review"]
    if not isinstance(review, dict) or review.get("accepted") is not True:
        errors.append("script requires an accepted independent semantic review")
    if int(review.get("repair_round", draft["repair_round"])) > 2:
        errors.append("script exceeds two editorial repair rounds")
    required_review = {"factual_support", "attribution", "listening_quality", "novelty", "density"}
    if not all(review.get(key) is True for key in required_review):
        errors.append("independent review gates are incomplete")
    if errors:
        raise PodcastError("; ".join(errors))
    transcript = _transcript(segments)
    transcript_hash = content_hash(transcript)
    notes = _show_notes(bundle, draft["show_notes"])
    review_document = build_revision(
        record_type="review",
        identity=stable_id("review", f"{draft['draft_id']}:{reviewer_operation_id}"),
        originating_operation_id=reviewer_operation_id,
        body={
            "target_revision_id": draft["script_revision_id"],
            "reviewer_operation_id": reviewer_operation_id,
            "accepted": True,
            "findings": review.get("findings", []),
            "gates": {key: bool(review.get(key)) for key in required_review},
        },
    )
    validate_document(root, review_document)
    scripts = {row["revision_id"]: row for row in load_records(root, "script")}
    draft_script = scripts.get(draft["script_revision_id"])
    if draft_script is None:
        raise PodcastError("canonical script draft revision is missing")
    accepted_script_body = {
        key: value
        for key, value in draft_script.items()
        if key
        not in {
            "schema_version",
            "record_type",
            "id",
            "revision_id",
            "created_at",
            "originating_operation_id",
            "supersedes",
        }
    }
    accepted_script_body["status"] = "accepted"
    accepted_script = build_revision(
        record_type="script",
        identity=draft_script["id"],
        originating_operation_id=reviewer_operation_id,
        body=accepted_script_body,
        supersedes=draft_script["revision_id"],
    )
    validate_document(root, accepted_script)
    document = build_revision(
        record_type="episode",
        identity=request["episode_id"],
        originating_operation_id=request["originating_operation_id"],
        body={
            "idea_revision_id": bundle["idea_revision"]["revision_id"],
            "intended_local_date": bundle["intended_local_date"],
            "source_commit": bundle["source_commit"],
            "frozen_bundle_hash": request["bundle_hash"],
            "language": "en",
            "narrator_count": 1,
            "segments": segments,
            "review": {**review, "review_revision_id": review_document["revision_id"]},
            "review_revision_id": review_document["revision_id"],
            "script_revision_id": accepted_script["revision_id"],
            "transcript_hash": transcript_hash,
            "show_notes": notes,
            "coverage": request.get("coverage", {}),
            "status": "reviewed",
        },
        supersedes=request.get("supersedes"),
    )
    validate_document(root, document)
    directory = _episode_directory(root, request["episode_id"])
    record = record_path(root, document)
    transcript_path = directory / "artifacts" / f"transcript-{document['revision_id']}.md"
    notes_path = directory / "artifacts" / f"show-notes-{document['revision_id']}.md"
    wiki_path = root / "data" / "wiki" / "podcasts" / f"{request['episode_id']}.md"
    claims = sorted({claim for segment in segments for claim in segment["claim_revision_ids"]})
    frontmatter = (
        "---\n"
        f"page_id: {stable_id('wiki', request['episode_id'])}\n"
        f"title: {bundle['idea_revision']['working_title']}\n"
        "type: podcast\nlanguage: en\nstatus: maintained\n"
        f"created_at: {bundle['intended_local_date']}\nupdated_at: {bundle['intended_local_date']}\n"
        f"as_of: {bundle['intended_local_date']}\nreview_at: null\nentity_ids: []\n"
        f"claim_revision_ids: {json.dumps(claims)}\n"
        f"provenance_revision_ids: {json.dumps(sorted(row['revision_id'] for row in bundle['evidence']))}\n"
        "---\n\n"
    )
    page_lines = [frontmatter, f"# {bundle['idea_revision']['working_title']}\n"]
    for segment in segments:
        page_lines.append(f"\n## {segment['segment_id']}\n")
        if segment["claim_revision_ids"]:
            page_lines.append(f"<!-- claims: {', '.join(segment['claim_revision_ids'])} -->\n\n")
        else:
            page_lines.append("<!-- nonfactual -->\n\n")
        page_lines.append(segment["spoken_text"].strip() + "\n")
    page_lines.extend(["\n## Show notes\n", "<!-- nonfactual -->\n\n", notes])
    transaction = Transaction(root, transaction_id=document["revision_id"])
    transaction.write_json(record_path(root, review_document).relative_to(root).as_posix(), review_document)
    transaction.write_json(record_path(root, accepted_script).relative_to(root).as_posix(), accepted_script)
    transaction.write_json(record.relative_to(root).as_posix(), document)
    transaction.write_text(transcript_path.relative_to(root).as_posix(), transcript)
    transaction.write_text(notes_path.relative_to(root).as_posix(), notes)
    transaction.write_text(wiki_path.relative_to(root).as_posix(), "".join(page_lines))
    transaction.commit()
    rebuild_indexes(root)
    return {
        **document,
        "transcript_path": transcript_path.relative_to(root).as_posix(),
        "show_notes_path": notes_path.relative_to(root).as_posix(),
        "word_count": words(transcript),
    }


def latest_episode(root: Path, episode_id: str) -> dict[str, Any]:
    rows = [row for row in load_records(root, "episode") if row["id"] == episode_id]
    superseded = {row["supersedes"] for row in rows if row.get("supersedes")}
    current = [row for row in rows if row["revision_id"] not in superseded]
    if len(current) != 1:
        raise PodcastError(f"episode does not have exactly one current revision: {episode_id}")
    return current[0]


def pre_release_errors(root: Path, episode: dict[str, Any]) -> list[str]:
    bundle = load_bundle(root, episode["id"], episode["frozen_bundle_hash"])
    errors: list[str] = []
    current_claims = load_records(root, "claim")
    superseded = {row.get("supersedes"): row for row in current_claims if row.get("supersedes")}
    for claim in bundle["claims"]:
        replacement = superseded.get(claim["revision_id"])
        if replacement:
            errors.append(f"frozen claim {claim['revision_id']} was superseded by {replacement['revision_id']}")
    for source in load_records(root, "source_revision"):
        if source.get("supersedes") in {row["revision_id"] for row in bundle["source_revisions"]} and source.get(
            "access_status"
        ) in {"retracted", "contradicted"}:
            errors.append(f"frozen source was {source['access_status']}: {source['revision_id']}")
    return errors


def _default_synthesizer(text: str, output: Path, voice: str, timeout: int) -> None:
    command = shutil.which("edge-tts")
    if command is None:
        raise PodcastError("edge-tts executable is unavailable")
    result = subprocess.run(
        [command, "--voice", voice, "--text", text, "--write-media", str(output)],
        check=False,
        capture_output=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise PodcastError("Edge TTS rendering failed")


def _duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise PodcastError("ffprobe could not inspect rendered audio")
    try:
        return float(result.stdout.strip())
    except ValueError as exc:
        raise PodcastError("ffprobe returned invalid duration") from exc


def render_temporary(
    root: Path,
    *,
    episode_id: str,
    render_id: str,
    deliver: Callable[[Path, dict[str, Any]], Any] | None = None,
    synthesizer: Callable[[str, Path, str, int], None] | None = None,
    duration_probe: Callable[[Path], float] | None = None,
) -> dict[str, Any]:
    episode = latest_episode(root, episode_id)
    blockers = pre_release_errors(root, episode)
    if blockers:
        raise PodcastError("; ".join(blockers))
    settings = load_settings(root).podcast
    artifact_dir = _episode_directory(root, episode_id) / "artifacts"
    transcript_path = artifact_dir / f"transcript-{episode['revision_id']}.md"
    transcript = transcript_path.read_text(encoding="utf-8")
    if content_hash(transcript) != episode["transcript_hash"]:
        raise PodcastError("committed transcript hash mismatch")
    prior = list(artifact_dir.glob("render-*.json"))
    if len(prior) >= settings.maximum_attempts:
        raise PodcastError("render-attempt ceiling reached")
    synth = synthesizer or _default_synthesizer
    probe = duration_probe or _duration
    cleanup_observed = False
    metadata: dict[str, Any] = {
        "schema_version": 1,
        "render_id": render_id,
        "episode_id": episode_id,
        "episode_revision_id": episode["revision_id"],
        "transcript_hash": episode["transcript_hash"],
        "source_commit": episode["source_commit"],
        "voice": settings.voice,
        "backend_version": settings.edge_tts_version,
        "duration_seconds": 0.0,
        "audio_sha256": "",
        "audio_bytes": 0,
        "mime_type": "audio/mpeg",
        "timing_method": "approximate",
        "timings": [],
        "created_at": format_timestamp(utc_now()),
        "cleanup_observed": False,
        "status": "started",
        "reason_code": None,
    }
    temporary_name: str | None = None
    try:
        with tempfile.TemporaryDirectory(prefix=f"robotelier-{render_id}-") as directory:
            temporary_name = directory
            temp = Path(directory)
            try:
                temp.resolve().relative_to(root.resolve())
            except ValueError:
                pass
            else:
                raise PodcastError("render directory must be outside the repository")
            output = temp / "episode.mp3"
            synth(transcript, output, settings.voice, settings.timeout_seconds)
            if not output.is_file() or output.is_symlink():
                raise PodcastError("renderer did not create a regular audio file")
            duration = probe(output)
            if not settings.minimum_seconds <= duration <= settings.maximum_seconds:
                raise PodcastError(
                    f"rendered duration {duration:.3f}s is outside "
                    f"{settings.minimum_seconds}-{settings.maximum_seconds}s"
                )
            payload = output.read_bytes()
            transcript_words = max(1, words(transcript))
            elapsed = 0.0
            timings: list[dict[str, Any]] = []
            for segment in episode["segments"]:
                share = duration * words(segment["spoken_text"]) / transcript_words
                timings.append(
                    {
                        "segment_id": segment["segment_id"],
                        "coordinate_system": "episode_audio_time",
                        "episode_start_seconds": round(elapsed, 3),
                        "episode_end_seconds": round(elapsed + share, 3),
                        "confidence": "approximate",
                    }
                )
                elapsed += share
            metadata.update(
                {
                    "duration_seconds": duration,
                    "audio_sha256": content_hash(payload),
                    "audio_bytes": len(payload),
                    "mime_type": mimetypes.guess_type(output.name)[0] or "audio/mpeg",
                    "timing_method": "approximate",
                    "timings": timings,
                    "status": "validated",
                }
            )
            if deliver is not None:
                delivery = deliver(output, metadata)
                if isinstance(delivery, dict):
                    metadata["delivery_state"] = delivery.get("state", "unknown")
        cleanup_observed = temporary_name is not None and not Path(temporary_name).exists()
    except BaseException as exc:
        metadata["status"] = "failed"
        metadata["reason_code"] = type(exc).__name__
        raise
    finally:
        metadata["cleanup_observed"] = cleanup_observed or (
            temporary_name is not None and not Path(temporary_name).exists()
        )
        path = artifact_dir / f"render-{render_id}.json"
        atomic_write_json(path, metadata, allowed_root=root)
    return metadata
