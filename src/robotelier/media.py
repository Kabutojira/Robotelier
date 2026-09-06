"""Metadata-only media registration and validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from robotelier.identity import canonical_url, media_identity, safe_media_asset_url
from robotelier.provenance import register_revision
from robotelier.utils import ContractError

MEDIA_SUFFIXES = frozenset(
    {
        ".mp3",
        ".wav",
        ".ogg",
        ".m4a",
        ".aac",
        ".flac",
        ".mp4",
        ".webm",
        ".mov",
        ".avi",
        ".mkv",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".avif",
        ".bmp",
        ".tiff",
        ".svgz",
    }
)


def register_media(root: Path, request: dict[str, Any]) -> dict[str, Any]:
    body = request.get("body")
    if not isinstance(body, dict):
        raise ContractError("media request requires body")
    page_url = canonical_url(str(body.get("page_url", "")))
    direct, direct_status = safe_media_asset_url(body.get("direct_asset_url"))
    identity = request.get("id") or media_identity(
        page_url, platform=body.get("platform"), external_id=body.get("external_media_id")
    )
    normalized = {
        "media_type": body.get("media_type"),
        "platform": body.get("platform"),
        "external_media_id": body.get("external_media_id"),
        "source_revision_ids": body.get("source_revision_ids", []),
        "identity_basis": body.get("identity_basis", "page_url"),
        "dedupe_aliases": body.get("dedupe_aliases", []),
        "page_url": page_url,
        "direct_asset_url": direct,
        "direct_url_status": direct_status,
        "uploader": body.get("uploader"),
        "original_creator": body.get("original_creator"),
        "rights_status": body.get("rights_status", "unknown"),
        "title": body.get("title"),
        "description": body.get("description"),
        "entity_ids": body.get("entity_ids", []),
        "claim_revision_ids": body.get("claim_revision_ids", []),
        "technical": body.get(
            "technical",
            {
                "mime": None,
                "width": None,
                "height": None,
                "duration_seconds": None,
                "caption_availability": "unknown",
                "frame_rate": None,
            },
        ),
        "context": body.get(
            "context",
            {
                "depiction": "unknown",
                "source_time_ranges": [],
                "reality": "unknown",
                "speed_caveat": "unknown",
                "teleoperation_caveat": "unknown",
                "description_provenance": "source_metadata",
            },
        ),
        "availability": body.get(
            "availability",
            {
                "status": "unknown",
                "verified_at": None,
                "replacement_observations": [],
                "reresolution": "use_page_url",
            },
        ),
        "reuse_readiness": body.get(
            "reuse_readiness",
            {
                "status": "unknown",
                "license_evidence_url": None,
                "conditions": None,
            },
        ),
    }
    return register_revision(
        root,
        {
            "record_type": "media",
            "id": identity,
            "originating_operation_id": request["originating_operation_id"],
            "body": normalized,
            "supersedes": request.get("supersedes"),
            "created_at": request.get("created_at"),
        },
    )


def retained_media_errors(root: Path) -> list[str]:
    errors: list[str] = []
    ignored_roots = (".git", ".venv", "site/node_modules", "site/public", "site/quartz")
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root)
        relative_text = relative.as_posix()
        if any(relative_text == item or relative_text.startswith(item + "/") for item in ignored_roots):
            continue
        if path.suffix.lower() in MEDIA_SUFFIXES:
            errors.append(f"retained media file is forbidden: {relative.as_posix()}")
        if path.suffix.lower() in {".json", ".jsonl", ".md", ".txt", ".yml", ".yaml"}:
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                errors.append(f"non-text bytes in public text path: {relative.as_posix()}")
                continue
            if "data:image/" in text or "data:video/" in text or "data:audio/" in text:
                errors.append(f"embedded base64 media is forbidden: {relative.as_posix()}")
    return errors
