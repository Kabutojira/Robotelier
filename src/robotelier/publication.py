"""Daily-slot reservations, independent channel states and clean Git patch bundles."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from robotelier.config import load_settings
from robotelier.models import current_revisions, load_records
from robotelier.podcast import latest_episode, pre_release_errors, render_temporary
from robotelier.storage import ConflictError, RepositoryLock, atomic_write_bytes, atomic_write_json
from robotelier.utils import ContractError, content_hash, format_timestamp, read_json, stable_id, utc_now

COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
RUNTIME_PREFIXES = (
    "data/records/",
    "data/operations/",
    "data/history/",
    "data/cursors/",
    "data/runs/",
    "data/published/",
    "data/wiki/",
    "data/issues/",
    "data/subscriptions/",
)


class PublicationError(ContractError):
    pass


def outbox_path(root: Path, local_date: str) -> Path:
    return root / "data" / "published" / "outbox" / f"{local_date}.json"


def reserve(root: Path, *, episode_id: str, local_date: str) -> dict[str, Any]:
    episode = latest_episode(root, episode_id)
    if episode["intended_local_date"] != local_date:
        raise PublicationError("episode intended date does not match reservation")
    if pre_release_errors(root, episode):
        raise PublicationError("episode has a known material pre-release blocker")
    path = outbox_path(root, local_date)
    path.parent.mkdir(parents=True, exist_ok=True)
    with RepositoryLock(root):
        if path.exists():
            value = read_json(path)
            if value["episode_id"] != episode_id:
                raise ConflictError("local date is already owned by another episode")
            return value
        timestamp = format_timestamp(utc_now())
        value = {
            "schema_version": 1,
            "publication_id": stable_id("publication", local_date),
            "episode_id": episode_id,
            "episode_revision_id": episode["revision_id"],
            "intended_local_date": local_date,
            "destination_alias": load_settings(root).telegram.destination_alias,
            "transcript": {"state": "reserved", "committed_at": None},
            "telegram_text": {"state": "pending", "intent_at": None, "message_ids": []},
            "telegram_audio": {"state": "pending", "intent_at": None, "message_id": None},
            "pages": {"state": "pending", "receipt": None},
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        atomic_write_json(path, value, allowed_root=root)
        return value


def commit_transcript(root: Path, *, episode_id: str, local_date: str, source_commit: str) -> dict[str, Any]:
    path = outbox_path(root, local_date)
    with RepositoryLock(root):
        if not path.exists():
            raise PublicationError("publication slot is not reserved")
        value = read_json(path)
        episode = latest_episode(root, episode_id)
        if value["episode_id"] != episode_id or episode["source_commit"] != source_commit:
            raise PublicationError("publication binding mismatch")
        value["transcript"] = {
            "state": "committed",
            "committed_at": format_timestamp(utc_now()),
            "transcript_hash": episode["transcript_hash"],
            "source_commit": source_commit,
        }
        value["updated_at"] = format_timestamp(utc_now())
        atomic_write_json(path, value, allowed_root=root)
        return value


def update_channel(
    root: Path,
    *,
    local_date: str,
    channel: str,
    state: dict[str, Any],
) -> dict[str, Any]:
    if channel not in {"telegram_text", "telegram_audio", "pages"}:
        raise PublicationError("unknown publication channel")
    path = outbox_path(root, local_date)
    with RepositoryLock(root):
        value = read_json(path)
        value[channel] = state
        value["updated_at"] = format_timestamp(utc_now())
        atomic_write_json(path, value, allowed_root=root)
        return value


def status(root: Path, local_date: str | None = None) -> dict[str, Any]:
    if local_date:
        path = outbox_path(root, local_date)
        return read_json(path) if path.exists() else {"status": "absent"}
    base = root / "data" / "published" / "outbox"
    return {
        "publications": [json.loads(path.read_text(encoding="utf-8")) for path in sorted(base.glob("*.json"))]
        if base.exists()
        else []
    }


def prepare_episode_publication(root: Path, *, local_date: str) -> dict[str, Any]:
    episodes = [
        row
        for row in current_revisions(load_records(root, "episode")).values()
        if row.get("intended_local_date") == local_date and row.get("status") == "reviewed"
    ]
    if not episodes:
        return {"status": "no_reviewed_episode", "local_date": local_date}
    if len(episodes) != 1:
        raise PublicationError("publication date has multiple reviewed episodes")
    episode = episodes[0]
    reserved = reserve(root, episode_id=episode["id"], local_date=local_date)
    committed = commit_transcript(
        root,
        episode_id=episode["id"],
        local_date=local_date,
        source_commit=episode["source_commit"],
    )
    transcript_path = (
        root / "data" / "records" / "episodes" / episode["id"] / "artifacts" / f"transcript-{episode['revision_id']}.md"
    )
    return {
        "status": "transcript_committed",
        "episode_id": episode["id"],
        "episode_revision_id": episode["revision_id"],
        "transcript_path": transcript_path.relative_to(root).as_posix(),
        "publication_id": reserved["publication_id"],
        "transcript_hash": committed["transcript"]["transcript_hash"],
    }


def deliver_episode_publication(
    root: Path,
    *,
    local_date: str,
    token: str,
    chat_id: str,
) -> dict[str, Any]:
    from robotelier.telegram import deliver_audio, deliver_text

    outbox = status(root, local_date)
    if outbox.get("transcript", {}).get("state") != "committed":
        raise PublicationError("delivery requires a committed transcript intent")
    episode = latest_episode(root, str(outbox["episode_id"]))
    transcript_path = (
        root / "data" / "records" / "episodes" / episode["id"] / "artifacts" / f"transcript-{episode['revision_id']}.md"
    )
    transcript = transcript_path.read_text(encoding="utf-8")
    text_state = outbox["telegram_text"]
    if text_state.get("state") in {"pending", "failed"}:
        text_state = deliver_text(
            root,
            local_date=local_date,
            text=transcript,
            token=token,
            chat_id=chat_id,
        )
    outbox = status(root, local_date)
    audio_state = outbox["telegram_audio"]
    render: dict[str, Any] | None = None
    if audio_state.get("state") in {"pending", "failed"}:
        attempts = len(
            list((root / "data" / "records" / "episodes" / episode["id"] / "artifacts").glob("render-*.json"))
        )
        render_id = stable_id("render", f"{episode['revision_id']}:{attempts + 1}")

        def send_audio(path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
            return deliver_audio(
                root,
                local_date=local_date,
                audio_path=path,
                metadata=metadata,
                token=token,
                chat_id=chat_id,
                caption=f"Robotelier — {local_date}",
            )

        render = render_temporary(
            root,
            episode_id=episode["id"],
            render_id=render_id,
            deliver=send_audio,
        )
        audio_state = status(root, local_date)["telegram_audio"]
    return {
        "status": "delivery_attempted",
        "episode_id": episode["id"],
        "telegram_text": text_state,
        "telegram_audio": audio_state,
        "render": render,
    }


def _git(
    root: Path,
    arguments: list[str],
    input_bytes: bytes | None = None,
    *,
    environment: dict[str, str] | None = None,
) -> bytes:
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        input=input_bytes,
        capture_output=True,
        check=False,
        env=environment,
    )
    if result.returncode != 0:
        raise PublicationError(result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout


def create_runtime_bundle(root: Path, output: Path, *, run_id: str, base_sha: str) -> dict[str, Any]:
    root = root.resolve(strict=True)
    output = output.absolute()
    try:
        output.resolve().relative_to(root)
    except ValueError:
        pass
    else:
        raise PublicationError("runtime bundle must be outside the checkout")
    head = _git(root, ["rev-parse", "HEAD"]).decode().strip()
    if head != base_sha or not COMMIT_SHA.fullmatch(base_sha):
        raise PublicationError("runtime bundle base is not the exact HEAD")
    with tempfile.TemporaryDirectory(prefix="robotelier-git-index-") as directory:
        index_path = Path(directory) / "index"
        git_environment = {**os.environ, "GIT_INDEX_FILE": str(index_path)}
        _git(root, ["read-tree", "HEAD"], environment=git_environment)
        _git(root, ["add", "--all", "--", "data"], environment=git_environment)
        paths = tuple(
            sorted(
                filter(
                    None,
                    _git(root, ["diff", "--cached", "--name-only"], environment=git_environment).decode().splitlines(),
                )
            )
        )
        forbidden = [path for path in paths if not path.startswith(RUNTIME_PREFIXES)]
        if forbidden:
            raise PublicationError(f"runtime patch contains forbidden paths: {forbidden}")
        deleted = _git(
            root,
            ["diff", "--cached", "--name-only", "--diff-filter=D"],
            environment=git_environment,
        )
        if deleted:
            raise PublicationError("runtime patch deletion is forbidden")
        _git(root, ["diff", "--cached", "--check"], environment=git_environment)
        patch = _git(
            root,
            ["diff", "--cached", "--binary", "--full-index", "HEAD"],
            environment=git_environment,
        )
    if output.exists():
        if output.is_symlink() or not output.is_dir() or any(output.iterdir()):
            raise PublicationError("bundle directory must be empty and regular")
    else:
        output.mkdir(parents=True)
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "base_sha": base_sha,
        "patch_sha256": content_hash(patch),
        "changed_paths": list(paths),
    }
    atomic_write_bytes(output / "runtime.patch", patch, allowed_root=output)
    atomic_write_json(output / "runtime_manifest.json", manifest, allowed_root=output)
    return manifest


def apply_runtime_bundle(root: Path, bundle: Path) -> dict[str, Any]:
    manifest = read_json(bundle / "runtime_manifest.json")
    patch = (bundle / "runtime.patch").read_bytes()
    if content_hash(patch) != manifest.get("patch_sha256"):
        raise PublicationError("runtime patch hash mismatch")
    if _git(root, ["rev-parse", "HEAD"]).decode().strip() != manifest.get("base_sha"):
        raise PublicationError("checkout is not at runtime bundle base")
    if _git(root, ["status", "--porcelain"]):
        raise PublicationError("target checkout must be clean")
    if patch:
        _git(root, ["apply", "--check", "--index", "--binary", str(bundle / "runtime.patch")])
        _git(root, ["apply", "--index", "--binary", str(bundle / "runtime.patch")])
    actual = sorted(filter(None, _git(root, ["diff", "--cached", "--name-only"]).decode().splitlines()))
    if actual != manifest["changed_paths"]:
        raise PublicationError("applied paths do not match manifest")
    return manifest
