"""Repository-wide deterministic integrity and policy checks."""

from __future__ import annotations

import json
import re
import stat
import subprocess
from pathlib import Path

from robotelier.credentials import OAUTH_CIPHERTEXT_PATH
from robotelier.identity import canonical_url, has_signed_query
from robotelier.knowledge import lint_wiki
from robotelier.media import retained_media_errors
from robotelier.models import load_records, validate_document
from robotelier.operations import validate_queue
from robotelier.provenance import (
    reference_errors,
    validate_quotation_budget,
    validate_source_hashes,
)
from robotelier.subscriptions import validate_registry
from robotelier.utils import ContractError, content_hash

SECRET_PATTERNS = (
    # Horizontal whitespace is deliberate: an empty example value must never
    # consume the following environment-variable name as though it were a key.
    re.compile(r"(?:bot|api|access|refresh)[_-]?token[ \t]*[:=][ \t]*[A-Za-z0-9_-]{16,}", re.I),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"https?://[^\s/]+:[^\s/@]+@"),
)


def _record_errors(root: Path) -> list[str]:
    errors: list[str] = []
    seen_revisions: set[str] = set()
    for record in load_records(root):
        try:
            validate_document(root, record)
        except ContractError as exc:
            errors.append(f"{record.get('revision_id', '<unknown>')}: {exc}")
        revision = str(record.get("revision_id"))
        if revision in seen_revisions:
            errors.append(f"duplicate revision ID: {revision}")
        seen_revisions.add(revision)
    return errors


def _url_errors(root: Path) -> list[str]:
    errors: list[str] = []
    for source in load_records(root, "source"):
        try:
            normalized = canonical_url(source["canonical_url"])
            if normalized != source["canonical_url"]:
                errors.append(f"{source['revision_id']}: source URL is not canonical")
        except ContractError as exc:
            errors.append(f"{source['revision_id']}: unsafe source URL: {exc}")
    for media in load_records(root, "media"):
        direct = media.get("direct_asset_url")
        if direct and has_signed_query(direct):
            errors.append(f"{media['revision_id']}: signed media URL was retained")
    return errors


def _secret_errors(root: Path) -> list[str]:
    errors: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root)
        if (
            relative.parts[0] in {".git", ".venv"}
            or "node_modules" in relative.parts
            or relative.as_posix().startswith(("site/quartz/", "site/public/"))
        ):
            continue
        if relative.as_posix() == ".env":
            ignored = subprocess.run(
                ["git", "check-ignore", "--quiet", "--", ".env"],
                cwd=root,
                check=False,
                capture_output=True,
            )
            if ignored.returncode != 0:
                errors.append("plaintext .env must not be committed")
            continue
        if path.suffix.lower() not in {
            ".md",
            ".json",
            ".jsonl",
            ".ini",
            ".yml",
            ".yaml",
            ".txt",
            ".example",
            ".py",
            ".toml",
        }:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                errors.append(f"possible secret in {relative.as_posix()}")
                break
    return errors


def _credential_errors(root: Path) -> list[str]:
    """Allow exactly one nonempty age artifact and no plaintext credential files."""

    base = root / OAUTH_CIPHERTEXT_PATH.parent
    if not base.exists():
        return []
    errors: list[str] = []
    files: list[Path] = []
    for path in base.rglob("*"):
        relative = path.relative_to(root).as_posix()
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            errors.append(f"credential artifact must not contain symlinks: {relative}")
        elif stat.S_ISREG(metadata.st_mode):
            files.append(path)
        elif not stat.S_ISDIR(metadata.st_mode):
            errors.append(f"credential artifact contains a special file: {relative}")
    expected = root / OAUTH_CIPHERTEXT_PATH
    for path in files:
        if path != expected:
            errors.append(f"unencrypted or unexpected credential artifact: {path.relative_to(root)}")
    if expected in files:
        ciphertext = expected.read_bytes()
        if not ciphertext or len(ciphertext) > 3_000_000:
            errors.append(f"{OAUTH_CIPHERTEXT_PATH}: ciphertext is empty or exceeds the safety bound")
        elif not ciphertext.startswith(b"age-encryption.org/v1"):
            errors.append(f"{OAUTH_CIPHERTEXT_PATH}: artifact is not an age ciphertext")
    return errors


def _episode_errors(root: Path) -> list[str]:
    errors: list[str] = []
    for episode in load_records(root, "episode"):
        artifact = (
            root
            / "data"
            / "records"
            / "episodes"
            / episode["id"]
            / "artifacts"
            / f"transcript-{episode['revision_id']}.md"
        )
        if not artifact.is_file() or content_hash(artifact.read_text(encoding="utf-8")) != episode["transcript_hash"]:
            errors.append(f"{episode['revision_id']}: transcript missing or hash mismatch")
        for render in artifact.parent.glob("render-*.json") if artifact.parent.exists() else []:
            value = json.loads(render.read_text(encoding="utf-8"))
            if value.get("transcript_hash") != episode["transcript_hash"]:
                errors.append(f"{render.relative_to(root)}: render transcript mismatch")
            if value.get("status") != "failed" and not 600 <= float(value.get("duration_seconds", 0)) <= 1200:
                errors.append(f"{render.relative_to(root)}: render duration outside gate")
            if any("path" in key or "url" in key for key in value if key.startswith("audio")):
                errors.append(f"{render.relative_to(root)}: durable audio location is forbidden")
    return errors


def _outbox_errors(root: Path) -> list[str]:
    errors: list[str] = []
    seen_dates: set[str] = set()
    base = root / "data" / "published" / "outbox"
    for path in sorted(base.glob("*.json")) if base.exists() else []:
        value = json.loads(path.read_text(encoding="utf-8"))
        local_date = value.get("intended_local_date")
        if local_date in seen_dates:
            errors.append(f"duplicate publication slot: {local_date}")
        seen_dates.add(local_date)
        if any(secret in json.dumps(value).upper() for secret in ("BOT_TOKEN", "CHAT_ID", "AUTHORIZATION")):
            errors.append(f"{path.relative_to(root)}: private destination/auth data in public outbox")
        audio_state = value.get("telegram_audio", {}).get("state")
        if audio_state == "delivery_unknown" and value.get("telegram_audio", {}).get("message_id"):
            errors.append(f"{path.relative_to(root)}: ambiguous delivery has fabricated acknowledgment")
    return errors


def validate_integrity(root: Path, *, strict: bool = False) -> list[str]:
    errors = [
        *_record_errors(root),
        *reference_errors(root),
        *validate_source_hashes(root),
        *validate_quotation_budget(root),
        *_url_errors(root),
        *validate_queue(root),
        *retained_media_errors(root),
        *validate_registry(root),
        *_secret_errors(root),
        *_credential_errors(root),
        *_episode_errors(root),
        *_outbox_errors(root),
    ]
    if strict:
        errors.extend(lint_wiki(root))
    return sorted(set(errors))
