"""Validate actual agent effects instead of trusting agent bookkeeping."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from robotelier.audit import Delta, Snapshot
from robotelier.integrity import validate_integrity


@dataclass(frozen=True, slots=True)
class AgentValidation:
    passed: bool
    errors: tuple[str, ...]
    changed_paths: tuple[str, ...]
    canonical_result: dict[str, Any] | None


def _within(path: str, prefixes: list[str]) -> bool:
    return any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in prefixes)


def validate_agent_result(
    root: Path,
    *,
    run_id: str,
    operation: dict[str, Any],
    before: Snapshot,
    after: Snapshot,
    delta: Delta,
) -> AgentValidation:
    operation_id = operation["operation_id"]
    result_path = root / "data" / "runs" / run_id / operation_id / "agent_result.json"
    errors: list[str] = []
    result: dict[str, Any] | None = None
    if result_path.is_file() and not result_path.is_symlink():
        try:
            value = json.loads(result_path.read_text(encoding="utf-8"))
            result = value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            result = None
    if result is None:
        errors.append("agent result is missing or invalid")
    elif result.get("operation_id") != operation_id:
        errors.append("agent result operation_id mismatch")
    protected = {
        f"data/runs/{run_id}/{operation_id}/controller_prompt.md",
        f"data/runs/{run_id}/{operation_id}/baseline.json",
        f"data/runs/{run_id}/{operation_id}/validation_report.json",
        f"data/operations/pending/{operation_id}.json",
    }
    changed = tuple(path for path in delta.changed if path != result_path.relative_to(root).as_posix())
    for path in delta.deleted:
        errors.append(f"agent deletion is forbidden: {path}")
    for path in delta.changed:
        if path in protected:
            errors.append(f"agent changed controller-owned file: {path}")
        state = after.files.get(path)
        if state and state.kind != "file":
            errors.append(f"agent created a symlink or special file: {path}")
        if not _within(path, operation.get("allowed_paths", [])) and not path.startswith(
            f"data/runs/{run_id}/{operation_id}/"
        ):
            errors.append(f"path is outside operation scope: {path}")
        if path.startswith(("src/", ".github/", "skills/", "schemas/")):
            errors.append(f"runtime agent cannot modify project code/contracts: {path}")
    reported = set(result.get("files_changed", [])) if result else set()
    invented = sorted(reported - set(changed))
    if invented:
        errors.append(f"agent invented changed paths: {invented}")
    audit_path = root / "data" / "runs" / run_id / operation_id / "command_audit.json"
    audited_paths: set[str] = set()
    audited_commands: list[str] = []
    if audit_path.exists():
        try:
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            for entry in audit.get("entries", []):
                audited_paths.update(entry.get("changed_paths", []))
                argv = entry.get("argv", [])
                audited_commands.append(" ".join(map(str, argv)))
        except (json.JSONDecodeError, AttributeError):
            errors.append("command audit is invalid")
    structured_changes = {
        path
        for path in changed
        if path.startswith(("data/records/", "data/operations/", "data/history/", "data/cursors/"))
    }
    unaudited = sorted(structured_changes - audited_paths)
    if unaudited:
        errors.append(f"structured changes lack controller CLI receipts: {unaudited}")
    allowed_commands = operation.get("allowed_commands", [])
    for command in audited_commands:
        suffix = command.removeprefix("robotelier ")
        if not any(suffix.startswith(allowed) for allowed in allowed_commands):
            errors.append(f"command is outside operation scope: {command}")
    if not errors:
        errors.extend(f"post-run integrity: {error}" for error in validate_integrity(root, strict=True))
    canonical = (
        None
        if result is None
        else {
            **result,
            "files_changed": list(changed),
            "commands_run": audited_commands,
        }
    )
    return AgentValidation(not errors, tuple(sorted(set(errors))), changed, canonical)
