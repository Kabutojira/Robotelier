from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from robotelier.agent_runner import (
    AgentRunError,
    configure_home,
    harness_finish,
    harness_start,
    preflight,
    sanitized_environment,
)
from robotelier.operations import all_operations, enqueue


def _native_skill(home: Path) -> None:
    skill = home / "skills/llm-wiki/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: llm-wiki\nversion: 2.1.0\n---\n\n# Native fixture\n")


def test_isolated_home_disables_persistent_and_expansive_capabilities(repo: Path, tmp_path: Path) -> None:
    home = tmp_path / "hermes"
    config_path = configure_home(repo, home, profile="x")
    _native_skill(home)
    config = config_path.read_text()
    assert "enabled: false" in config
    assert "worktree: false" in config
    assert "mcp_servers: {}" in config
    check = preflight(repo, home, profile="x", live=False)
    assert check["provider"] == "xai-oauth"
    assert check["native_skill_sha256"]
    with pytest.raises(AgentRunError, match=r"auth\.json"):
        preflight(repo, home, profile="x", live=True)


def test_auth_file_must_be_private_and_regular(repo: Path, tmp_path: Path) -> None:
    home = tmp_path / "hermes"
    configure_home(repo, home, profile="scout")
    _native_skill(home)
    auth = home / "auth.json"
    auth.write_text("{}")
    auth.chmod(0o644)
    with pytest.raises(AgentRunError, match="private"):
        preflight(repo, home, profile="scout")
    auth.chmod(stat.S_IRUSR | stat.S_IWUSR)
    assert preflight(repo, home, profile="scout")["auth_status"] == "private_file_present"


def test_agent_environment_excludes_unrelated_secrets(repo: Path, tmp_path: Path) -> None:
    operation = enqueue(
        repo,
        {"operation_type": "x_research", "dedupe_key": "environment", "prompt": "fixture"},
    )
    environment = sanitized_environment(
        repo,
        tmp_path,
        run_id="fixture-run",
        operation=operation,
        source={
            "PATH": "/usr/bin",
            "LANG": "C.UTF-8",
            "XAI_API_KEY": "paid-key",
            "GITHUB_TOKEN": "write-key",
            "TELEGRAM_BOT_TOKEN": "telegram-key",
            "OPENAI_OAUTH_SECRET": "age-identity",
            "UNRELATED_PRIVATE_KEY": "private-key",
        },
    )
    assert set(environment) == {
        "PATH",
        "LANG",
        "HERMES_HOME",
        "WIKI_PATH",
        "ROBOTELIER_SKILLS_DIR",
        "ROBOTELIER_AUDIT_RUN_ID",
        "ROBOTELIER_AUDIT_OPERATION_ID",
        "ROBOTELIER_AUDIT_PATH",
    }
    assert "XAI_API_KEY" not in environment


def test_valid_local_harness_operation_succeeds_once(repo: Path) -> None:
    operation = enqueue(
        repo,
        {"operation_type": "triage", "dedupe_key": "valid-harness", "prompt": "fixture"},
    )
    started = harness_start(
        repo,
        run_id="valid-harness-run",
        operation_id=operation["operation_id"],
        cycle_id="2026-09-06",
    )
    result_path = repo / started["result_path"]
    result_path.write_text(
        json.dumps(
            {
                "operation_id": operation["operation_id"],
                "status": "succeeded",
                "files_changed": [],
            }
        )
    )
    result = harness_finish(
        repo,
        run_id="valid-harness-run",
        operation_id=operation["operation_id"],
        cycle_id="2026-09-06",
    )
    assert result["validation"]["passed"] is True
    assert all_operations(repo)[operation["operation_id"]]["state"] == "succeeded"


def test_direct_structured_edit_and_fake_receipt_are_rejected_and_rolled_back(repo: Path) -> None:
    operation = enqueue(
        repo,
        {"operation_type": "triage", "dedupe_key": "invalid-harness", "prompt": "fixture"},
    )
    started = harness_start(
        repo,
        run_id="invalid-harness-run",
        operation_id=operation["operation_id"],
        cycle_id="2026-09-06",
    )
    invented = repo / "data/records/claims/invented/rev_invented.json"
    invented.parent.mkdir(parents=True)
    invented.write_text('{"model_claimed_receipt": true}\n')
    result_path = repo / started["result_path"]
    result_path.write_text(
        json.dumps(
            {
                "operation_id": operation["operation_id"],
                "status": "succeeded",
                "files_changed": [invented.relative_to(repo).as_posix(), "data/records/claims/fake.json"],
            }
        )
    )
    result = harness_finish(
        repo,
        run_id="invalid-harness-run",
        operation_id=operation["operation_id"],
        cycle_id="2026-09-06",
    )
    assert result["validation"]["passed"] is False
    assert any("invented changed paths" in error for error in result["validation"]["errors"])
    assert any("lack controller CLI receipts" in error for error in result["validation"]["errors"])
    assert not invented.exists()
