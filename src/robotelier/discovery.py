"""Bounded multi-source discovery with durable registration before cursors."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from robotelier.config import load_settings
from robotelier.identity import canonical_url, source_identity
from robotelier.media import register_media
from robotelier.provenance import register_revision
from robotelier.sources.adapters import Adapter
from robotelier.storage import atomic_write_json
from robotelier.utils import ContractError, content_hash, format_timestamp, stable_id, utc_now


def _classification(value: str) -> str:
    if value not in {"ingest", "defer", "ignore"}:
        raise ContractError(f"invalid triage classification: {value}")
    return value


def register_candidate(
    root: Path,
    candidate: Any,
    *,
    operation_id: str,
    classification: str = "defer",
    now: datetime | None = None,
) -> dict[str, Any]:
    instant = now or utc_now()
    decision = _classification(classification)
    source_id = source_identity(candidate.url, platform=candidate.adapter_id, external_id=candidate.external_id)
    origin_url = canonical_url(candidate.origin_url) if candidate.origin_url else candidate.url
    origin_group = stable_id("origin", origin_url)
    source = register_revision(
        root,
        {
            "record_type": "source",
            "id": source_id,
            "originating_operation_id": operation_id,
            "body": {
                "canonical_url": candidate.url,
                "discovered_url": candidate.url,
                "publisher": candidate.publisher,
                "author": candidate.author,
                "original_title": candidate.title,
                "language": candidate.language,
                "platform": candidate.adapter_id,
                "stable_external_id": candidate.external_id,
                "source_kind": candidate.source_kind,
                "origin_group_id": origin_group,
                "original_source_url": origin_url if origin_url != candidate.url else None,
                "triage": {
                    "classification": decision,
                    "reason": "adapter-supplied deterministic decision",
                },
            },
        },
    )
    observation_id = stable_id(
        "source_revision",
        f"{source_id}:{candidate.adapter_id}:{candidate.external_id or candidate.url}",
    )
    observation = register_revision(
        root,
        {
            "record_type": "source_revision",
            "id": observation_id,
            "originating_operation_id": operation_id,
            "created_at": format_timestamp(instant),
            "body": {
                "source_id": source_id,
                "published_at": candidate.published_at,
                "event_at": candidate.event_at,
                "modified_at": None,
                "retrieved_at": format_timestamp(instant),
                "date_precision": "unknown",
                "access_status": "metadata_only",
                "retrieval_method": "adapter_metadata",
                "effective_url": candidate.url,
                "content_hash": None,
                "hash_scope": "none",
                "retained_excerpt": None,
                "english_summary": None,
                "observation_id": observation_id,
            },
        },
    )
    media_ids: list[str] = []
    source_revision_id = observation["revision_id"]
    for item in candidate.media:
        body = {
            **item,
            "page_url": item.get("page_url", candidate.url),
            "source_revision_ids": [source_revision_id],
        }
        result = register_media(
            root,
            {
                "originating_operation_id": operation_id,
                "body": body,
            },
        )
        media_ids.append(result["id"])
    return {
        "source_id": source_id,
        "source_identity_revision_id": source["revision_id"],
        "source_revision_id": source_revision_id,
        "media_ids": media_ids,
        "classification": decision,
    }


def scan_adapters(
    root: Path,
    adapters: list[Adapter],
    *,
    operation_id: str,
    classifications: dict[str, str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    instant = now or utc_now()
    settings = load_settings(root)
    remaining = settings.discovery.maximum_candidates
    results: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = []
    for adapter in adapters:
        attempted = format_timestamp(instant)
        cursor_path = root / "data" / "cursors" / f"{adapter.adapter_id}.json"
        previous: dict[str, Any] = {}
        if cursor_path.exists():
            loaded = json.loads(cursor_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                previous = loaded
        try:
            candidates = adapter.scan(limit=min(settings.discovery.page_limit, remaining))
            registered_count = 0
            for candidate in candidates:
                key = candidate.external_id or candidate.url
                decision = (classifications or {}).get(key, "defer")
                results.append(
                    register_candidate(
                        root,
                        candidate,
                        operation_id=operation_id,
                        classification=decision,
                        now=instant,
                    )
                )
                remaining -= 1
                registered_count += 1
                if remaining == 0:
                    break
            cursor = {
                "schema_version": 1,
                "adapter_id": adapter.adapter_id,
                "last_attempted_at": attempted,
                "last_successful_checkpoint": attempted,
                "overlap_hours": settings.discovery.overlap_hours,
                "status": "succeeded",
                "registered_count": registered_count,
                "coverage": "bounded_window",
                "non_exhaustive": True,
                "retry_history": [],
            }
            cursor_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(cursor_path, cursor, allowed_root=root)
            coverage.append(cursor)
        except Exception as exc:
            retries = list(previous.get("retry_history", []))
            retries.append({"at": attempted, "reason": type(exc).__name__})
            cursor = {
                "schema_version": 1,
                "adapter_id": adapter.adapter_id,
                "last_attempted_at": attempted,
                "last_successful_checkpoint": previous.get("last_successful_checkpoint"),
                "overlap_hours": settings.discovery.overlap_hours,
                "status": "failed",
                "reason": type(exc).__name__,
                "coverage": "unknown",
                "non_exhaustive": True,
                "retry_history": retries[-10:],
            }
            cursor_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(cursor_path, cursor, allowed_root=root)
            coverage.append(cursor)
        if remaining == 0:
            break
    if remaining == 0 and len(coverage) < len(adapters):
        for adapter in adapters[len(coverage) :]:
            coverage.append(
                {
                    "adapter_id": adapter.adapter_id,
                    "last_attempted_at": None,
                    "status": "deferred",
                    "reason": "candidate_bound_reached",
                    "coverage": "not_attempted",
                }
            )
    return {
        "operation_id": operation_id,
        "registered": results,
        "coverage": coverage,
        "deferred_by_bound": remaining == 0,
        "result_hash": content_hash(results),
    }


def load_subscription_registry(root: Path) -> list[dict[str, Any]]:
    path = root / "data" / "subscriptions" / "registry.json"
    if not path.exists():
        return []
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ContractError("subscription registry must be an array")
    return value
