"""Concise public daily operational reports."""

from __future__ import annotations

import json
import re
import subprocess
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from robotelier.cadence import status as cadence_status
from robotelier.config import load_settings
from robotelier.models import current_revisions, load_records
from robotelier.operations import all_operations
from robotelier.publication import status as publication_status
from robotelier.storage import RepositoryLock, atomic_write_json, atomic_write_text
from robotelier.utils import (
    ContractError,
    content_hash,
    format_timestamp,
    read_json,
    require_run_id,
    stable_id,
    utc_now,
)

COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
SUMMARY_STATES = {
    "intent_written",
    "acknowledged",
    "failed",
    "delivery_unknown",
    "reconciliation_required",
}


class ReportError(ContractError):
    pass


def _require_local_date(local_date: str) -> str:
    try:
        parsed = date.fromisoformat(local_date)
    except (TypeError, ValueError) as exc:
        raise ReportError("local date must use YYYY-MM-DD") from exc
    if parsed.isoformat() != local_date:
        raise ReportError("local date must use canonical YYYY-MM-DD")
    return local_date


def daily_report_record_path(root: Path, local_date: str) -> Path:
    return root / "data" / "published" / "daily-reports" / f"{_require_local_date(local_date)}.json"


def daily_summary_delivery_path(root: Path, local_date: str) -> Path:
    return root / "data" / "published" / "daily-reports" / f"{_require_local_date(local_date)}.telegram.json"


def _require_report_url(report_url: str) -> str:
    parsed = urlsplit(report_url)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ReportError("daily report URL must be a public HTTPS URL without credentials, query, or fragment")
    return report_url


def load_committed_daily_report(root: Path, *, local_date: str, source_commit: str) -> dict[str, Any]:
    """Load the report from an exact Git commit, never from mutable checkout state."""

    _require_local_date(local_date)
    if not COMMIT_SHA.fullmatch(source_commit):
        raise ReportError("source commit must be a full lowercase Git SHA")
    relative = daily_report_record_path(root, local_date).relative_to(root).as_posix()
    result = subprocess.run(
        ["git", "show", f"{source_commit}:{relative}"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ReportError("daily report is not present in the source commit")
    try:
        value = json.loads(result.stdout)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReportError("committed daily report is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict) or value.get("local_date") != local_date:
        raise ReportError("committed daily report does not match the requested local date")
    return value


def _summary_text(value: object, *, maximum: int = 180) -> str:
    text = " ".join(str(value).split())
    if len(text) <= maximum:
        return text
    return text[: maximum - 1].rstrip() + "…"


def render_daily_summary(report: dict[str, Any], *, report_url: str) -> str:
    """Render a bounded plain-text Telegram projection of a public report."""

    report_url = _require_report_url(report_url)
    local_date = _require_local_date(str(report.get("local_date", "")))
    coverage = report.get("source_coverage", {})
    cadence = report.get("cadence", {})
    publication = report.get("publication", {})
    if not isinstance(coverage, dict) or not isinstance(cadence, dict) or not isinstance(publication, dict):
        raise ReportError("daily report has invalid summary fields")
    ideas = report.get("top_eligible_ideas", [])
    incidents = report.get("incidents", [])
    if not isinstance(ideas, list) or not isinstance(incidents, list):
        raise ReportError("daily report ideas and incidents must be arrays")
    top_ideas = "; ".join(_summary_text(item) for item in ideas[:3]) or "none ready"
    publication_states = []
    for label, key in (
        ("transcript", "transcript"),
        ("text", "telegram_text"),
        ("audio", "telegram_audio"),
        ("Pages", "pages"),
    ):
        channel = publication.get(key, {})
        state = channel.get("state", "absent") if isinstance(channel, dict) else "absent"
        publication_states.append(f"{label} {_summary_text(state, maximum=40)}")
    lines = [
        f"Robotelier daily report — {local_date}",
        "",
        (
            f"Research: {coverage.get('registered_sources', 0)} registered sources; "
            f"{report.get('research_changes', 0)} claim revisions; "
            f"{report.get('deferred_work', 0)} deferred or blocked operations."
        ),
        (
            f"Editorial: {report.get('accepted_idea_count', 0)} ready ideas; "
            f"{report.get('rejected_idea_count', 0)} rejected. Top ideas: {top_ideas}."
        ),
        (
            f"Cadence: {_summary_text(cadence.get('phase', 'unknown'), maximum=80)}; "
            f"days since listener-release anchor: {cadence.get('days_since_anchor')}."
        ),
        f"Channels: {', '.join(publication_states)}.",
        f"Incidents: {len(incidents)}.",
        "",
        f"Full report: {report_url}",
    ]
    message = "\n".join(lines)
    if len(message) > 4096:
        raise ReportError("daily report summary exceeds Telegram's message limit")
    return message


def prepare_daily_summary(
    root: Path,
    *,
    local_date: str,
    source_commit: str,
    report_url: str,
    delivery_run_id: str,
) -> dict[str, Any]:
    """Write a Git-committable intent before the trusted network delivery step."""

    report = load_committed_daily_report(root, local_date=local_date, source_commit=source_commit)
    require_run_id(delivery_run_id)
    report_url = _require_report_url(report_url)
    message = render_daily_summary(report, report_url=report_url)
    report_hash = content_hash(report)
    message_hash = content_hash(message)
    path = daily_summary_delivery_path(root, local_date)
    path.parent.mkdir(parents=True, exist_ok=True)
    with RepositoryLock(root):
        current = read_json(path) if path.exists() else None
        if current is not None:
            same_binding = all(
                current.get(key) == expected
                for key, expected in {
                    "source_commit": source_commit,
                    "report_hash": report_hash,
                    "message_sha256": message_hash,
                    "report_url": report_url,
                }.items()
            )
            if not same_binding:
                raise ReportError("daily summary date is already bound to a different committed report")
            state = current.get("state")
            if state == "acknowledged":
                return current
            if state == "intent_written" and current.get("delivery_run_id") == delivery_run_id:
                return current
            if state in {"intent_written", "delivery_unknown", "reconciliation_required"}:
                raise ReportError(f"daily summary requires reconciliation from {state}")
            if state != "failed":
                raise ReportError("daily summary has an invalid delivery state")
            attempt_count = int(current.get("attempt_count", 0)) + 1
        else:
            attempt_count = 1
        if attempt_count > load_settings(root).telegram.maximum_attempts:
            raise ReportError("daily summary delivery attempt ceiling reached")
        timestamp = format_timestamp(utc_now())
        intent = {
            "schema_version": 1,
            "summary_id": stable_id("daily_summary", local_date),
            "local_date": local_date,
            "destination_alias": load_settings(root).telegram.destination_alias,
            "delivery_run_id": delivery_run_id,
            "source_commit": source_commit,
            "report_path": daily_report_record_path(root, local_date).relative_to(root).as_posix(),
            "report_hash": report_hash,
            "report_url": report_url,
            "message_sha256": message_hash,
            "state": "intent_written",
            "attempt_count": attempt_count,
            "intent_at": timestamp,
            "acknowledged_at": None,
            "message_id": None,
            "reason_code": None,
            "updated_at": timestamp,
        }
        atomic_write_json(path, intent, allowed_root=root)
        return intent


def daily_summary_status(root: Path, *, local_date: str) -> dict[str, Any]:
    path = daily_summary_delivery_path(root, local_date)
    return read_json(path) if path.exists() else {"state": "absent", "local_date": local_date}


def update_daily_summary(root: Path, *, local_date: str, state: dict[str, Any]) -> dict[str, Any]:
    if state.get("state") not in SUMMARY_STATES:
        raise ReportError("invalid daily summary delivery state")
    path = daily_summary_delivery_path(root, local_date)
    with RepositoryLock(root):
        current = read_json(path)
        immutable = (
            "schema_version",
            "summary_id",
            "local_date",
            "destination_alias",
            "delivery_run_id",
            "source_commit",
            "report_path",
            "report_hash",
            "report_url",
            "message_sha256",
        )
        if any(state.get(key) != current.get(key) for key in immutable):
            raise ReportError("daily summary update changed its immutable binding")
        state["updated_at"] = format_timestamp(utc_now())
        atomic_write_json(path, state, allowed_root=root)
        return state


def require_daily_summary_acknowledged(root: Path, *, local_date: str) -> dict[str, Any]:
    state = daily_summary_status(root, local_date=local_date)
    if state.get("state") != "acknowledged" or not isinstance(state.get("message_id"), int):
        raise ReportError(f"daily summary is not acknowledged: {state.get('state')}")
    return state


def build_daily_report(root: Path, *, local_date: str, incidents: list[str] | None = None) -> dict[str, Any]:
    operations = all_operations(root)
    ideas = current_revisions(load_records(root, "idea"))
    ready = [row for row in ideas.values() if row.get("state") == "ready"]
    rejected = [row for row in ideas.values() if row.get("state") == "rejected"]
    publications = publication_status(root, local_date)
    source_count = len(current_revisions(load_records(root, "source")))
    media_count = len(current_revisions(load_records(root, "media")))
    deferred = [row for row in operations.values() if row["state"] in {"queued", "blocked"}]
    cadence = cadence_status(root)
    document = {
        "schema_version": 1,
        "local_date": local_date,
        "source_coverage": {"registered_sources": source_count, "coverage_complete": False},
        "research_changes": len(load_records(root, "claim")),
        "deferred_work": len(deferred),
        "accepted_idea_count": len(ready),
        "rejected_idea_count": len(rejected),
        "top_eligible_ideas": [
            row["working_title"]
            for row in sorted(ready, key=lambda row: -float(row.get("scores", {}).get("priority", 0)))[:5]
        ],
        "cadence": cadence,
        "publication": publications,
        "missing_media_metadata": sum(
            1 for row in load_records(root, "media") if row.get("technical", {}).get("duration_seconds") is None
        ),
        "registered_media": media_count,
        "incidents": incidents or [],
        "generated_at": format_timestamp(utc_now()),
    }
    lines = [
        "---",
        f"page_id: {stable_id('wiki', 'daily-report:' + local_date)}",
        f"title: Robotelier daily report — {local_date}",
        "type: daily_report",
        "language: en",
        "status: maintained",
        f"created_at: {local_date}",
        f"updated_at: {local_date}",
        f"as_of: {local_date}",
        "review_at: null",
        "entity_ids: []",
        "claim_revision_ids: []",
        "provenance_revision_ids: []",
        "---",
        "",
        f"# Robotelier daily report — {local_date}",
        "",
        "## Status",
        "<!-- nonfactual -->",
        "",
        f"Registered sources: {source_count}. Coverage is bounded and is not claimed exhaustive.",
        "",
        f"Ready ideas: {len(ready)}. Deferred or blocked operations: {len(deferred)}.",
        "",
        f"Cadence phase: `{cadence['phase']}`. Days since anchor: {cadence['days_since_anchor']}.",
        "",
        "## Publication channels",
        "<!-- nonfactual -->",
        "",
        f"Transcript: `{publications.get('transcript', {}).get('state', 'absent')}`; "
        f"Telegram text: `{publications.get('telegram_text', {}).get('state', 'absent')}`; "
        f"Telegram audio: `{publications.get('telegram_audio', {}).get('state', 'absent')}`; "
        f"Pages: `{publications.get('pages', {}).get('state', 'absent')}`.",
        "",
    ]
    if incidents:
        lines.extend(["## Incidents", "<!-- nonfactual -->", "", *[f"- {item}" for item in incidents], ""])
    page = root / "data" / "wiki" / "daily-reports" / f"daily-report_{local_date.replace('-', '')}.md"
    atomic_write_text(page, "\n".join(lines), allowed_root=root)
    record = root / "data" / "published" / "daily-reports" / f"{local_date}.json"
    record.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(record, document, allowed_root=root)
    return {
        **document,
        "report_path": page.relative_to(root).as_posix(),
        "hash": content_hash(document),
    }
