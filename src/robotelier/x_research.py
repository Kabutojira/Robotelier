"""Normalized evidence contract for OpenAI-backed read-only X research."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from robotelier.identity import canonical_url, safe_media_asset_url
from robotelier.storage import atomic_write_json
from robotelier.utils import ContractError, format_timestamp, utc_now

POST_PATH = re.compile(r"^/([^/]+)/status/(\d+)$")
HANDLE = re.compile(r"^[A-Za-z0-9_]{1,15}$")


def _published_at(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ContractError("X citation published_at must be a timestamp or null")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError("X citation published_at is invalid") from exc
    if parsed.tzinfo is None:
        raise ContractError("X citation published_at must include a timezone")
    return format_timestamp(parsed)


def _media_metadata(value: object, post_url: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        direct, direct_status = safe_media_asset_url(item.get("direct_asset_url"))
        result.append(
            {
                "external_media_id": item.get("external_media_id"),
                "media_type": item.get("media_type", "unknown"),
                "page_url": post_url,
                "direct_asset_url": direct,
                "direct_url_status": direct_status,
                "duration_seconds": item.get("duration_seconds"),
                "width": item.get("width"),
                "height": item.get("height"),
                "creator": item.get("creator"),
                "rights_status": item.get("rights_status", "unknown"),
            }
        )
    return result


def normalize_x_response(
    raw: dict[str, Any],
    *,
    query: str,
    account_filter: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    credential_source = raw.get("credential_source")
    if credential_source != "openai-codex":
        raise ContractError("X research must prove credential_source=openai-codex")
    citations = raw.get("citations", [])
    if not isinstance(citations, list):
        citations = []
    posts: list[dict[str, Any]] = []
    invalid: list[str] = []
    for citation in citations:
        if not isinstance(citation, dict) or not isinstance(citation.get("url"), str):
            invalid.append("citation_missing_url")
            continue
        try:
            url = canonical_url(citation["url"])
        except ContractError:
            invalid.append("citation_invalid_url")
            continue
        from urllib.parse import urlsplit

        parsed = urlsplit(url)
        if parsed.hostname not in {"x.com", "twitter.com", "www.x.com", "www.twitter.com"}:
            invalid.append("citation_not_x_post")
            continue
        match = POST_PATH.fullmatch(parsed.path)
        if not match:
            invalid.append("citation_not_status_url")
            continue
        handle, post_id = match.groups()
        if not HANDLE.fullmatch(handle):
            invalid.append("invalid_account_handle")
            continue
        supplied_id = citation.get("post_id")
        supplied_handle = citation.get("account")
        if supplied_id is not None and str(supplied_id) != post_id:
            invalid.append("post_id_mismatch")
            continue
        if supplied_handle is not None and str(supplied_handle).lstrip("@").casefold() != handle.casefold():
            invalid.append("account_mismatch")
            continue
        if account_filter and account_filter.lstrip("@").casefold() != handle.casefold():
            invalid.append("account_filter_mismatch")
            continue
        try:
            published_at = _published_at(citation.get("published_at"))
        except ContractError:
            invalid.append("published_at_invalid")
            continue
        post_url = f"https://x.com/{handle}/status/{post_id}"
        posts.append(
            {
                "post_id": post_id,
                "account": handle,
                "url": post_url,
                "published_at": published_at,
                "inline_citation": citation.get("inline"),
                "access_level": citation.get("access_level", "citation_only"),
                "media": _media_metadata(citation.get("media", []), post_url),
            }
        )
    degradation = raw.get("degradation_reason")
    if not posts:
        status = "x_search_unsourced" if raw.get("answer") else "x_search_unavailable"
        degradation = degradation or "no_resolvable_post_citations"
    elif not raw.get("tool_available"):
        status = "x_search_unavailable"
        degradation = degradation or "search_tool_not_confirmed"
    elif invalid:
        status = "partial"
        degradation = degradation or "some_invalid_citations"
    else:
        status = "evidence_available"
    return {
        "schema_version": 1,
        "status": status,
        "query": query,
        "filters": {"account": account_filter, "date_from": date_from, "date_to": date_to},
        "credential_source": "openai-codex",
        "provider": raw.get("provider"),
        "inference_model": raw.get("inference_model"),
        "search_model": raw.get("search_model"),
        "tool_available": bool(raw.get("tool_available")),
        "provider_success": bool(raw.get("success")),
        "provider_degraded": raw.get("degraded"),
        "degradation_reason": degradation,
        "posts": posts,
        "invalid_citations": invalid,
        "non_exhaustive": True,
        "answer_retained": False,
        "observed_at": format_timestamp(utc_now()),
        "token_refresh": raw.get("token_refresh", "unknown"),
    }


def save_probe(root: Path, run_id: str, normalized: dict[str, Any]) -> Path:
    sanitized = dict(normalized)
    sanitized.pop("answer", None)
    path = root / "data" / "runs" / run_id / "x-capability.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, sanitized, allowed_root=root)
    return path
