"""Versioned public source registry with bounded autonomous admissions."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

from robotelier.config import load_settings
from robotelier.identity import canonical_url
from robotelier.sources.adapters import validate_adapter_id
from robotelier.storage import Transaction
from robotelier.utils import ContractError, content_hash, format_timestamp, parse_timestamp, utc_now

ADAPTER_TYPES = frozenset({"feed_url", "web_page", "metadata", "x_search"})


def registry_path(root: Path) -> Path:
    return root / "data" / "subscriptions" / "registry.json"


def _subscription_errors(item: dict[str, Any], index: int, seen: set[str]) -> list[str]:
    errors: list[str] = []
    try:
        adapter_id = validate_adapter_id(str(item.get("adapter_id", "")))
        normalized = canonical_url(str(item.get("url", "")))
        canonical_url(str(item.get("verification_basis_url", "")))
    except ContractError as exc:
        return [f"subscription {index}: {exc}"]
    if adapter_id in seen:
        errors.append(f"duplicate subscription adapter ID: {adapter_id}")
    seen.add(adapter_id)
    if normalized != item.get("url"):
        errors.append(f"subscription {adapter_id} URL is not canonical")
    if item.get("adapter_type") not in ADAPTER_TYPES:
        errors.append(f"subscription {adapter_id} has unsupported adapter type")
    for field in ("name", "category", "geography", "language", "verified_at", "verification_basis_url"):
        if not item.get(field):
            errors.append(f"subscription {adapter_id} lacks {field}")
    if item.get("official") not in {True, False} or item.get("active") not in {True, False}:
        errors.append(f"subscription {adapter_id} requires boolean official/active flags")
    return errors


def validate_registry(root: Path) -> list[str]:
    path = registry_path(root)
    errors: list[str] = []
    try:
        values = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"subscription registry cannot be read: {exc}"]
    if not isinstance(values, list):
        return ["subscription registry must be an array"]
    seen: set[str] = set()
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            errors.append(f"subscription {index} must be an object")
            continue
        errors.extend(_subscription_errors(item, index, seen))
    return sorted(set(errors))


def add_subscription(root: Path, request: dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
    body = request.get("body")
    if not isinstance(body, dict):
        raise ContractError("subscription admission requires a body object")
    candidate = dict(body)
    adapter_id = validate_adapter_id(str(candidate.get("adapter_id", "")))
    candidate["adapter_id"] = adapter_id
    candidate["url"] = canonical_url(str(candidate.get("url", "")))
    candidate["verification_basis_url"] = canonical_url(str(candidate.get("verification_basis_url", "")))
    candidate.setdefault("active", False)
    candidate.setdefault("official", False)
    candidate.setdefault("admitted_at", format_timestamp(now))
    candidate_errors = _subscription_errors(candidate, 0, set())
    if candidate_errors:
        raise ContractError("invalid subscription admission: " + "; ".join(candidate_errors))
    if candidate.get("adapter_type") == "x_search" and candidate.get("active"):
        raise ContractError("X subscriptions require a separately recorded live capability activation")
    path = registry_path(root)
    values = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    if not isinstance(values, list) or any(not isinstance(item, dict) for item in values):
        raise ContractError("subscription registry is invalid")
    existing = next((item for item in values if item.get("adapter_id") == adapter_id), None)
    if existing is not None:
        if existing == candidate:
            return {"status": "existing", "subscription": existing}
        raise ContractError("subscription adapter ID already exists; use a reviewed registry revision")
    history = root / "data" / "history" / f"subscriptions-{now.year}.jsonl"
    prior_events: list[dict[str, Any]] = []
    if history.exists():
        for line in history.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            if not isinstance(event, dict):
                raise ContractError("subscription history contains a non-object event")
            prior_events.append(event)
    cutoff = now - timedelta(days=7)
    admissions = 0
    for event in prior_events:
        at = parse_timestamp(event.get("at", ""), nullable=True)
        if event.get("event_type") == "subscription_admitted" and at and at >= cutoff:
            admissions += 1
    if admissions >= load_settings(root).discovery.maximum_new_subscriptions:
        raise ContractError("rolling seven-day subscription admission bound reached")
    values.append(candidate)
    values.sort(key=lambda item: str(item["adapter_id"]))
    event = {
        "event_id": content_hash({"adapter_id": adapter_id, "at": candidate["admitted_at"]})[:24],
        "event_type": "subscription_admitted",
        "adapter_id": adapter_id,
        "at": candidate["admitted_at"],
        "operation_id": request["originating_operation_id"],
    }
    new_history = "".join(
        json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n" for item in [*prior_events, event]
    )
    transaction = Transaction(root, transaction_id=f"subscription-{event['event_id']}")
    transaction.write_json(
        path.relative_to(root).as_posix(),
        values,
        expected_hash=content_hash(path.read_bytes()) if path.exists() else None,
    )
    history.parent.mkdir(parents=True, exist_ok=True)
    transaction.write_text(
        history.relative_to(root).as_posix(),
        new_history,
        expected_hash=content_hash(history.read_bytes()) if history.exists() else None,
    )
    transaction.commit()
    return {"status": "created", "subscription": candidate}
