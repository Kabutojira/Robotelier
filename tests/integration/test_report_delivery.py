from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from robotelier.reports import ReportError, build_daily_report, prepare_daily_summary
from robotelier.telegram import TelegramError, deliver_daily_summary


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(["git", *arguments], cwd=root, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _committed_report(repo: Path) -> str:
    build_daily_report(repo, local_date="2026-09-06")
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Fixture")
    _git(repo, "config", "user.email", "fixture@example.invalid")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "fixture report")
    return _git(repo, "rev-parse", "HEAD")


def test_daily_summary_is_bound_to_committed_report_and_idempotent(repo: Path) -> None:
    source_commit = _committed_report(repo)
    report_url = "https://kabutojira.github.io/Robotelier/daily-reports/daily-report_20260906"
    intent = prepare_daily_summary(
        repo,
        local_date="2026-09-06",
        source_commit=source_commit,
        report_url=report_url,
        delivery_run_id="fixture-delivery",
    )
    assert intent["state"] == "intent_written"
    assert intent["destination_alias"] == "robotelier-listeners"
    assert intent["message_id"] is None

    # Mutable working-tree changes cannot alter the delivered report projection.
    report_path = repo / "data/published/daily-reports/2026-09-06.json"
    changed = json.loads(report_path.read_text())
    changed["research_changes"] = 999
    report_path.write_text(json.dumps(changed))
    calls: list[dict[str, Any]] = []

    def accepted(_: str, payload: dict[str, Any], __: int) -> dict[str, Any]:
        calls.append(payload)
        return {"ok": True, "result": {"message_id": 42}}

    acknowledged = deliver_daily_summary(
        repo,
        local_date="2026-09-06",
        delivery_run_id="fixture-delivery",
        token="bot-secret",
        chat_id="private-chat",
        sender=accepted,
    )
    assert acknowledged["state"] == "acknowledged"
    assert acknowledged["message_id"] == 42
    assert len(calls) == 1
    assert "999 claim revisions" not in calls[0]["text"]
    assert report_url in calls[0]["text"]

    repeated = deliver_daily_summary(
        repo,
        local_date="2026-09-06",
        delivery_run_id="fixture-delivery",
        token="bot-secret",
        chat_id="private-chat",
        sender=accepted,
    )
    assert repeated["state"] == "acknowledged"
    assert len(calls) == 1
    receipt = (repo / "data/published/daily-reports/2026-09-06.telegram.json").read_text()
    assert "bot-secret" not in receipt
    assert "private-chat" not in receipt


def test_ambiguous_daily_summary_blocks_another_workflow_run(repo: Path) -> None:
    source_commit = _committed_report(repo)
    report_url = "https://kabutojira.github.io/Robotelier/daily-reports/daily-report_20260906"
    prepare_daily_summary(
        repo,
        local_date="2026-09-06",
        source_commit=source_commit,
        report_url=report_url,
        delivery_run_id="first-run",
    )

    def timeout(*_: object) -> dict[str, Any]:
        raise TimeoutError

    state = deliver_daily_summary(
        repo,
        local_date="2026-09-06",
        delivery_run_id="first-run",
        token="fixture",
        chat_id="fixture",
        sender=timeout,
    )
    assert state["state"] == "delivery_unknown"
    with pytest.raises(ReportError, match="reconciliation"):
        prepare_daily_summary(
            repo,
            local_date="2026-09-06",
            source_commit=source_commit,
            report_url=report_url,
            delivery_run_id="second-run",
        )
    with pytest.raises(TelegramError, match="cannot be delivered"):
        deliver_daily_summary(
            repo,
            local_date="2026-09-06",
            delivery_run_id="second-run",
            token="fixture",
            chat_id="fixture",
            sender=timeout,
        )


def test_daily_summary_rejects_uncommitted_report_and_unsafe_url(repo: Path) -> None:
    source_commit = _committed_report(repo)
    with pytest.raises(ReportError, match="public HTTPS URL"):
        prepare_daily_summary(
            repo,
            local_date="2026-09-06",
            source_commit=source_commit,
            report_url="https://example.com/report?view=summary",
            delivery_run_id="fixture-run",
        )
    with pytest.raises(ReportError, match="full lowercase Git SHA"):
        prepare_daily_summary(
            repo,
            local_date="2026-09-06",
            source_commit="HEAD",
            report_url="https://example.com/report",
            delivery_run_id="fixture-run",
        )
