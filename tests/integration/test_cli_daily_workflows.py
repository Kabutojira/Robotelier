from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from robotelier.audit import compare, snapshot
from robotelier.cli import main
from robotelier.daily import prepare
from robotelier.operations import all_operations


def test_cli_configuration_integrity_and_dry_discovery(repo: Path, monkeypatch: object, capsys: object) -> None:
    del monkeypatch, capsys
    current = Path.cwd()
    try:
        __import__("os").chdir(repo)
        assert main(["config", "validate"]) == 0
        assert main(["doctor", "--offline"]) == 0
        request = repo / "data/operations/requests/discovery.json"
        request.write_text(json.dumps({"originating_operation_id": "fixture", "adapters": []}))
        assert main(["discovery", "scan", "--request", str(request), "--dry-run"]) == 0
    finally:
        __import__("os").chdir(current)


def test_strict_integrity_cli_fails_closed(repo: Path) -> None:
    marker = repo / "unsafe.txt"
    marker.write_text("access_" + "token = " + "abcdefghijklmnopqrstuvwxyz\n")
    current = Path.cwd()
    try:
        __import__("os").chdir(repo)
        assert main(["integrity", "check", "--strict"]) == 2
    finally:
        __import__("os").chdir(current)


def test_daily_dry_run_has_no_mutations(repo: Path) -> None:
    before = snapshot(repo)
    result = prepare(
        repo,
        run_id="dry-run",
        intended_local_date="2026-09-06",
        trigger="manual",
        dry_run=True,
        maximum_operations=20,
        publish_pages=False,
        send_telegram=False,
        resume_id=None,
    )
    assert result["dry_run_guarantees"] == [
        "no_inference",
        "no_network_research",
        "no_commit",
        "no_push",
        "no_render",
        "no_delivery",
    ]
    assert compare(before, snapshot(repo)).changed == ()


def test_daily_prepare_seeds_one_bounded_sequential_chain(repo: Path) -> None:
    result = prepare(
        repo,
        run_id="daily-fixture",
        intended_local_date="2026-09-06",
        trigger="scheduled-like",
        dry_run=False,
        maximum_operations=20,
        publish_pages=False,
        send_telegram=False,
        resume_id=None,
    )
    operations = all_operations(repo)
    assert len(result["seeded_operations"]) == 5
    assert {row["operation_type"] for row in operations.values()} == {
        "discovery",
        "x_research",
        "triage",
        "editorial_ideas",
        "editorial_review",
    }
    assert all(
        row["resource_budget"]["profile"] != "x" or row["operation_type"] == "x_research" for row in operations.values()
    )
    repeated = prepare(
        repo,
        run_id="daily-fixture-retry",
        intended_local_date="2026-09-06",
        trigger="recovery",
        dry_run=False,
        maximum_operations=20,
        publish_pages=False,
        send_telegram=False,
        resume_id="daily-fixture",
    )
    assert repeated["seeded_operations"] == result["seeded_operations"]
    assert len(all_operations(repo)) == 5


def test_workflows_are_offline_for_prs_serialized_and_never_transfer_audio() -> None:
    root = Path(__file__).resolve().parents[2]
    workflows: dict[str, dict[Any, Any]] = {}
    for path in sorted((root / ".github/workflows").glob("*.yml")):
        value = yaml.safe_load(path.read_text())
        assert isinstance(value, dict)
        workflows[path.name] = value
        text = path.read_text()
        assert "XAI_API_KEY" not in text
        assert "*.mp3" not in text
        assert "upload-artifact" not in text or path.name == "pages.yml"
    assert "pull_request" in workflows["ci.yml"][True]
    for name in ("research.yml", "publish.yml", "recover.yml"):
        assert workflows[name]["concurrency"]["group"] == "robotelier-write"
        assert workflows[name][True]["schedule"][0]["timezone"] == "Europe/Rome"
        assert "pull_request" not in workflows[name][True]
    ci_text = (root / ".github/workflows/ci.yml").read_text()
    assert "secrets." not in ci_text
    assert "hermes chat" not in ci_text
    research_text = (root / ".github/workflows/research.yml").read_text()
    publish_text = (root / ".github/workflows/publish.yml").read_text()
    for text in (research_text, publish_text):
        assert "secrets.OPENAI_OAUTH_SECRET" in text
        assert "ROBOTELIER_AGE_IDENTITY" not in text
        assert "ROBOTELIER_AGE_RECIPIENT" not in text
        assert ".robotelier/credentials/oauth-auth.json.age" in text
        assert "python3 -m pip" not in text
        assert "uv tool install --no-cache uv==0.12.2" in text
        assert '== "uv 0.12.2"*' in text
    assert "secrets.TELEGRAM_BOT_TOKEN" in publish_text
    assert "secrets.TELEGRAM_CHAT_ID" in publish_text
    assert "secrets.TELEGRAM_BOT_TOKEN" in research_text
    assert "secrets.TELEGRAM_CHAT_ID" in research_text
    assert "report prepare-summary" in research_text
    assert "report deliver-summary" in research_text
    assert "report verify-summary" in research_text
    assert "GROK_HOME" not in research_text
    assert '--profile x --hermes-home "$OPENAI_HOME"' in research_text
    assert "--publish-pages" in research_text
    assert "--send-telegram" in research_text
    pages_text = (root / ".github/workflows/pages.yml").read_text()
    assert "vars.ROBOTELIER_PAGES_ENABLED == 'true'" in pages_text
    assert "vars.ROBOTELIER_PRODUCTION_ENABLED" not in pages_text
    assert "actions/deploy-pages@" in pages_text


def test_workflow_schedules_match_contract() -> None:
    root = Path(__file__).resolve().parents[2] / ".github/workflows"
    expected = {"research.yml": "17 3 * * *", "publish.yml": "7 5 * * *", "recover.yml": "17 6 * * *"}
    for name, cron in expected.items():
        workflow = yaml.safe_load((root / name).read_text())
        assert workflow[True]["schedule"] == [{"cron": cron, "timezone": "Europe/Rome"}]
