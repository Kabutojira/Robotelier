"""Europe/Rome release slots and rolling local-calendar cadence."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from robotelier.config import load_settings
from robotelier.storage import RepositoryLock, atomic_write_json
from robotelier.utils import format_timestamp, read_json, utc_now


def _local_clock(raw: str) -> time:
    hour, minute = map(int, raw.split(":"))
    return time(hour, minute)


def slot_for_date(root: Path, local_date: date) -> dict[str, str]:
    settings = load_settings(root)
    zone = ZoneInfo(settings.cadence.timezone)

    def stamp(raw: str) -> str:
        value = datetime.combine(local_date, _local_clock(raw), tzinfo=zone)
        return format_timestamp(value.astimezone(UTC))

    return {
        "local_date": local_date.isoformat(),
        "timezone": zone.key,
        "research_at": stamp(settings.cadence.research_time),
        "soft_cutoff_at": stamp(settings.cadence.soft_cutoff),
        "publication_at": stamp(settings.cadence.publication_time),
        "release_at": stamp(settings.cadence.release_time),
        "recovery_at": stamp(settings.cadence.recovery_time),
        "late_release_end_at": stamp(settings.cadence.late_release_end),
    }


def activate(root: Path, *, now: datetime | None = None) -> dict[str, Any]:
    instant = now or utc_now()
    path = root / "data" / "history" / "activation.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with RepositoryLock(root):
        if path.exists():
            return read_json(path)
        zone = ZoneInfo(load_settings(root).cadence.timezone)
        local_date = instant.astimezone(zone).date()
        deadline_date = local_date + timedelta(days=load_settings(root).cadence.weekly_days)
        document = {
            "schema_version": 1,
            "activated_at": format_timestamp(instant),
            "first_release_deadline": slot_for_date(root, deadline_date)["release_at"],
        }
        atomic_write_json(path, document, allowed_root=root)
        return document


def _acknowledged_release_dates(root: Path) -> list[date]:
    zone = ZoneInfo(load_settings(root).cadence.timezone)
    dates: list[date] = []
    for path in (
        sorted((root / "data" / "published" / "outbox").glob("*.json"))
        if (root / "data" / "published" / "outbox").exists()
        else []
    ):
        value = json.loads(path.read_text(encoding="utf-8"))
        audio = value.get("telegram_audio", {})
        if audio.get("state") == "acknowledged" and audio.get("acknowledged_at"):
            timestamp = datetime.fromisoformat(audio["acknowledged_at"].replace("Z", "+00:00"))
            dates.append(timestamp.astimezone(zone).date())
    return sorted(set(dates))


def status(root: Path, *, now: datetime | None = None) -> dict[str, Any]:
    instant = now or utc_now()
    settings = load_settings(root)
    zone = ZoneInfo(settings.cadence.timezone)
    today = instant.astimezone(zone).date()
    activation_path = root / "data" / "history" / "activation.json"
    if activation_path.exists():
        activation = read_json(activation_path)
        activation_state = "activated"
    else:
        activation = {
            "activated_at": format_timestamp(instant),
            "first_release_deadline": slot_for_date(root, today + timedelta(days=settings.cadence.weekly_days))[
                "release_at"
            ],
        }
        activation_state = "activation_required"
    activation_date = datetime.fromisoformat(activation["activated_at"].replace("Z", "+00:00")).astimezone(zone).date()
    releases = _acknowledged_release_dates(root)
    anchor = releases[-1] if releases else activation_date
    days = (today - anchor).days
    deadline_date = anchor + timedelta(days=settings.cadence.weekly_days)
    if days >= settings.cadence.weekly_days:
        phase = "cadence_breach"
    elif days >= 6:
        phase = "outline_due"
    elif days >= 5:
        phase = "evidence_priority"
    elif days >= 4:
        phase = "prepare_weekly_candidate"
    else:
        phase = "healthy"
    return {
        "local_date": today.isoformat(),
        "last_listener_release_date": releases[-1].isoformat() if releases else None,
        "days_since_anchor": days,
        "deadline_local_date": deadline_date.isoformat(),
        "phase": phase,
        "weekly_ready": phase == "healthy",
        "slot": slot_for_date(root, today),
        "activation_state": activation_state,
    }
