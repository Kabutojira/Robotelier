"""Concise public daily operational reports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from robotelier.cadence import status as cadence_status
from robotelier.models import current_revisions, load_records
from robotelier.operations import all_operations
from robotelier.publication import status as publication_status
from robotelier.storage import atomic_write_json, atomic_write_text
from robotelier.utils import content_hash, format_timestamp, stable_id, utc_now


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
