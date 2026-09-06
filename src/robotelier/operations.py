"""Sequential operation queue, fencing leases and shared cycle budgets."""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from robotelier.config import load_settings
from robotelier.storage import ConflictError, RepositoryLock, atomic_write_json
from robotelier.utils import (
    ContractError,
    content_hash,
    format_timestamp,
    parse_timestamp,
    stable_id,
    utc_now,
)

TERMINAL = frozenset({"succeeded", "skipped", "blocked", "failed", "cancelled", "superseded"})
FINISH_OUTCOMES = frozenset({"succeeded", "skipped", "blocked", "failed"})
RESEARCH_TYPES = frozenset({"research", "identity_resolution", "evidence_followup"})
OPERATION_PROFILES = {
    "discovery": "scout",
    "triage": "scout",
    "x_research": "x",
    "podcast_review": "deep",
}
OPERATION_TYPES = frozenset(
    {
        "discovery",
        "x_research",
        "triage",
        "research",
        "identity_resolution",
        "evidence_followup",
        "editorial_ideas",
        "editorial_review",
        "podcast_write",
        "podcast_review",
        "wiki_maintenance",
    }
)


class QueueError(ContractError):
    pass


def _operation_path(root: Path, operation_id: str) -> Path:
    return root / "data" / "operations" / "pending" / f"{operation_id}.json"


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise QueueError(f"operation must be an object: {path}")
    return value


def all_operations(root: Path) -> dict[str, dict[str, Any]]:
    base = root / "data" / "operations" / "pending"
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(base.glob("operation_*.json")) if base.exists() else []:
        row = _load(path)
        operation_id = str(row.get("operation_id"))
        if operation_id in result:
            raise QueueError(f"duplicate operation: {operation_id}")
        result[operation_id] = row
    return result


def _defaults_for_type(operation_type: str) -> tuple[list[str], list[str]]:
    role_paths = {
        "discovery": [
            "data/records/sources/",
            "data/records/media/",
            "data/cursors/",
            "data/history/",
            "data/runs/",
        ],
        "x_research": [
            "data/records/sources/",
            "data/records/media/",
            "data/records/evidence/",
            "data/history/",
            "data/runs/",
        ],
        "triage": ["data/operations/", "data/history/", "data/runs/"],
        "research": ["data/records/", "data/wiki/", "data/operations/", "data/history/", "data/runs/"],
        "identity_resolution": [
            "data/records/",
            "data/wiki/",
            "data/operations/",
            "data/history/",
            "data/runs/",
        ],
        "evidence_followup": [
            "data/records/",
            "data/wiki/",
            "data/operations/",
            "data/history/",
            "data/runs/",
        ],
        "editorial_ideas": [
            "data/records/ideas/",
            "data/wiki/podcast-ideas/",
            "data/history/",
            "data/runs/",
        ],
        "editorial_review": [
            "data/records/ideas/",
            "data/records/reviews/",
            "data/history/",
            "data/runs/",
        ],
        "podcast_write": [
            "data/records/scripts/",
            "data/records/episodes/",
            "data/history/",
            "data/runs/",
        ],
        "podcast_review": [
            "data/records/reviews/",
            "data/records/scripts/",
            "data/records/episodes/",
            "data/wiki/podcasts/",
            "data/published/",
            "data/history/",
            "data/runs/",
        ],
        "wiki_maintenance": ["data/wiki/", "data/history/", "data/runs/"],
    }
    commands = {
        "discovery": ["source register", "source observe", "media register", "queue enqueue"],
        "x_research": ["source register", "source observe", "media register", "evidence record"],
        "triage": ["queue enqueue"],
        "research": [
            "source register",
            "source observe",
            "evidence record",
            "claim record",
            "entity upsert",
            "development upsert",
            "queue enqueue",
        ],
        "identity_resolution": ["entity upsert", "entity merge", "queue enqueue"],
        "evidence_followup": [
            "source register",
            "source observe",
            "evidence record",
            "claim record",
            "queue enqueue",
        ],
        "editorial_ideas": ["editorial propose"],
        "editorial_review": ["editorial review"],
        "podcast_write": ["podcast validate-script"],
        "podcast_review": ["podcast validate-script"],
        "wiki_maintenance": ["wiki validate"],
    }
    return role_paths.get(operation_type, ["data/runs/"]), commands.get(operation_type, [])


def enqueue(root: Path, request: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    required = {"operation_type", "dedupe_key", "prompt"}
    missing = sorted(required - set(request))
    if missing:
        raise QueueError(f"operation request missing fields: {missing}")
    operation_type = str(request["operation_type"])
    if operation_type not in OPERATION_TYPES:
        raise QueueError(f"unsupported operation type: {operation_type}")
    dedupe_key = str(request["dedupe_key"])
    if not dedupe_key or len(dedupe_key) > 512:
        raise QueueError("dedupe_key must contain 1-512 characters")
    operation_id = stable_id("operation", dedupe_key)
    instant = now or utc_now()
    path = _operation_path(root, operation_id)
    with RepositoryLock(root):
        operations = all_operations(root)
        current_errors = validate_operations(operations)
        if current_errors:
            raise QueueError("existing queue is invalid: " + "; ".join(current_errors))
        existing = operations.get(operation_id)
        if existing is not None:
            if existing.get("dedupe_key") != dedupe_key:
                raise QueueError("operation identity collision")
            return {"status": "existing", **existing}
        settings = load_settings(root)
        allowed_paths, allowed_commands = _defaults_for_type(operation_type)
        payload = {
            "prompt": request["prompt"],
            "inputs": request.get("inputs", {}),
            "entity_ids": request.get("entity_ids", []),
            "development_ids": request.get("development_ids", []),
            "idea_ids": request.get("idea_ids", []),
        }
        operation = {
            "schema_version": 1,
            "operation_id": operation_id,
            "operation_type": operation_type,
            "payload": payload,
            "payload_hash": content_hash(payload),
            "dedupe_key": dedupe_key,
            "priority": int(request.get("priority", 50)),
            "depends_on": sorted(set(request.get("depends_on", []))),
            "earliest_start": request.get("earliest_start"),
            "deadline": request.get("deadline"),
            "resource_budget": request.get(
                "resource_budget",
                {
                    "profile": OPERATION_PROFILES.get(operation_type, "editorial"),
                    "cost_weight": str(
                        settings.profiles[OPERATION_PROFILES.get(operation_type, "editorial")].cost_weight
                    ),
                    "known_metered_usd_ceiling": None,
                },
            ),
            "allowed_paths": request.get("allowed_paths", allowed_paths),
            "allowed_commands": request.get("allowed_commands", allowed_commands),
            "source_refs": sorted(set(request.get("source_refs", []))),
            "state": "queued",
            "attempts": [],
            "max_attempts": int(request.get("max_attempts", settings.operations.default_max_attempts)),
            "lease": None,
            "created_at": format_timestamp(instant),
            "updated_at": format_timestamp(instant),
            "result": None,
        }
        if not 0 <= operation["priority"] <= 100 or operation["max_attempts"] < 1:
            raise QueueError("priority or max_attempts outside bounds")
        unknown_dependencies = sorted(set(operation["depends_on"]) - set(operations))
        if operation_id in operation["depends_on"]:
            raise QueueError("operation cannot depend on itself")
        if unknown_dependencies:
            raise QueueError(f"operation has unknown dependencies: {unknown_dependencies}")
        profile_name = operation["resource_budget"].get("profile")
        if profile_name not in settings.profiles:
            raise QueueError(f"operation has unknown profile: {profile_name}")
        parse_timestamp(operation["earliest_start"], nullable=True)
        parse_timestamp(operation["deadline"], nullable=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(path, operation, allowed_root=root)
    return {"status": "created", **operation}


def _cycle_path(root: Path, cycle_id: str) -> Path:
    return root / "data" / "history" / "cycles" / f"{cycle_id}.json"


def _cycle(root: Path, cycle_id: str, now: datetime) -> dict[str, Any]:
    path = _cycle_path(root, cycle_id)
    if path.exists():
        return _load(path)
    settings = load_settings(root)
    return {
        "schema_version": 1,
        "cycle_id": cycle_id,
        "maximum_operations": settings.budgets.maximum_operations,
        "maximum_known_metered_usd": str(settings.budgets.maximum_known_usd),
        "maximum_weighted": str(settings.budgets.maximum_weighted),
        "maximum_research": settings.budgets.maximum_research,
        "operations_claimed": 0,
        "known_metered_usd": "0",
        "weighted_used": "0",
        "research_claimed": 0,
        "unknown_cost_operations": [],
        "created_at": format_timestamp(now),
        "updated_at": format_timestamp(now),
    }


def initialize_cycle(
    root: Path,
    *,
    cycle_id: str,
    maximum_operations: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    instant = now or utc_now()
    configured = load_settings(root).budgets.maximum_operations
    if not 1 <= maximum_operations <= configured:
        raise QueueError(f"cycle operation ceiling must be between 1 and {configured}")
    path = _cycle_path(root, cycle_id)
    with RepositoryLock(root):
        cycle = _load(path) if path.exists() else _cycle(root, cycle_id, instant)
        claimed = int(cycle["operations_claimed"])
        effective = min(int(cycle["maximum_operations"]), maximum_operations)
        if claimed > effective:
            raise QueueError("cycle already consumed more operations than the requested ceiling")
        cycle["maximum_operations"] = effective
        cycle["updated_at"] = format_timestamp(instant)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(path, cycle, allowed_root=root)
        return cycle


def _expire_stale(root: Path, operations: dict[str, dict[str, Any]], now: datetime) -> None:
    for operation in operations.values():
        lease = operation.get("lease")
        if operation.get("state") != "leased" or not isinstance(lease, dict):
            continue
        expiry = parse_timestamp(str(lease["expires_at"]))
        if expiry and expiry <= now:
            attempt = {
                "attempt_id": lease["attempt_id"],
                "lease_token_hash": content_hash(lease["token"]),
                "run_id": lease["run_id"],
                "started_at": lease["claimed_at"],
                "completed_at": format_timestamp(now),
                "outcome": "expired",
                "reason_code": "lease_expired",
            }
            operation["attempts"].append(attempt)
            operation["lease"] = None
            operation["state"] = "queued" if len(operation["attempts"]) < operation["max_attempts"] else "failed"
            operation["updated_at"] = format_timestamp(now)
            atomic_write_json(_operation_path(root, operation["operation_id"]), operation, allowed_root=root)
            _write_attempt_history(root, operation["operation_id"], attempt)


def _dependency_state(operation: dict[str, Any], operations: dict[str, dict[str, Any]]) -> str:
    states = [operations.get(dep, {}).get("state") for dep in operation["depends_on"]]
    if any(state in {"failed", "blocked", "cancelled", "superseded", "skipped"} for state in states):
        return "blocked"
    return "ready" if all(state == "succeeded" for state in states) else "waiting"


def prepare(root: Path, *, now: datetime | None = None) -> dict[str, Any]:
    instant = now or utc_now()
    with RepositoryLock(root):
        operations = all_operations(root)
        _expire_stale(root, operations, instant)
        operations = all_operations(root)
        ready, waiting, blocked = [], [], []
        for operation in operations.values():
            if operation["state"] != "queued":
                continue
            dependency = _dependency_state(operation, operations)
            earliest = parse_timestamp(operation["earliest_start"], nullable=True)
            deadline = parse_timestamp(operation["deadline"], nullable=True)
            if deadline and instant > deadline:
                operation["state"] = "skipped"
                operation["result"] = {"reason_code": "deadline_expired"}
                operation["updated_at"] = format_timestamp(instant)
                atomic_write_json(_operation_path(root, operation["operation_id"]), operation, allowed_root=root)
                blocked.append(operation["operation_id"])
            elif dependency == "blocked":
                operation["state"] = "blocked"
                operation["result"] = {"reason_code": "dependency_terminal"}
                operation["updated_at"] = format_timestamp(instant)
                atomic_write_json(_operation_path(root, operation["operation_id"]), operation, allowed_root=root)
                blocked.append(operation["operation_id"])
            elif dependency == "ready" and (earliest is None or earliest <= instant):
                ready.append(operation["operation_id"])
            else:
                waiting.append(operation["operation_id"])
        return {"ready": sorted(ready), "waiting": sorted(waiting), "terminalized": sorted(blocked)}


def claim(
    root: Path,
    *,
    run_id: str,
    cycle_id: str,
    profile: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    instant = now or utc_now()
    with RepositoryLock(root):
        operations = all_operations(root)
        _expire_stale(root, operations, instant)
        operations = all_operations(root)
        if any(row["state"] == "leased" for row in operations.values()):
            raise ConflictError("one operation already owns the live agent lease")
        cycle = _cycle(root, cycle_id, instant)
        settings = load_settings(root)
        candidates: list[dict[str, Any]] = []
        for row in operations.values():
            if row["state"] != "queued" or _dependency_state(row, operations) != "ready":
                continue
            if profile is not None and row.get("resource_budget", {}).get("profile") != profile:
                continue
            earliest = parse_timestamp(row["earliest_start"], nullable=True)
            if earliest and earliest > instant:
                continue
            weight = Decimal(str(row["resource_budget"].get("cost_weight", "0")))
            if row["operation_type"] in RESEARCH_TYPES:
                try:
                    from datetime import date

                    from robotelier.cadence import slot_for_date

                    cutoff = parse_timestamp(slot_for_date(root, date.fromisoformat(cycle_id))["soft_cutoff_at"])
                except ValueError:
                    cutoff = None
                if cutoff is not None and instant > cutoff:
                    continue
            if cycle["operations_claimed"] >= cycle["maximum_operations"]:
                continue
            if Decimal(cycle["weighted_used"]) + weight > Decimal(cycle["maximum_weighted"]):
                continue
            if row["operation_type"] in RESEARCH_TYPES and cycle["research_claimed"] >= cycle["maximum_research"]:
                continue
            candidates.append(row)
        if not candidates:
            return None
        candidates.sort(key=lambda row: (-row["priority"], row["created_at"], row["operation_id"]))
        operation = candidates[0]
        token = secrets.token_hex(24)
        attempt_number = len(operation["attempts"]) + 1
        attempt_id = stable_id("attempt", f"{operation['operation_id']}:{attempt_number}")
        operation["state"] = "leased"
        operation["lease"] = {
            "owner": "robotelier-controller",
            "run_id": run_id,
            "token": token,
            "attempt_id": attempt_id,
            "claimed_at": format_timestamp(instant),
            "expires_at": format_timestamp(instant + timedelta(minutes=settings.operations.lease_minutes)),
        }
        operation["updated_at"] = format_timestamp(instant)
        cycle["operations_claimed"] += 1
        cycle["weighted_used"] = str(
            Decimal(cycle["weighted_used"]) + Decimal(str(operation["resource_budget"].get("cost_weight", "0")))
        )
        if operation["operation_type"] in RESEARCH_TYPES:
            cycle["research_claimed"] += 1
        cycle["updated_at"] = format_timestamp(instant)
        cycle_path = _cycle_path(root, cycle_id)
        cycle_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(cycle_path, cycle, allowed_root=root)
        atomic_write_json(_operation_path(root, operation["operation_id"]), operation, allowed_root=root)
        return {**operation, "lease_token": token}


def heartbeat(
    root: Path,
    *,
    operation_id: str,
    lease_token: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    instant = now or utc_now()
    with RepositoryLock(root):
        operation = _load(_operation_path(root, operation_id))
        lease = operation.get("lease")
        if operation["state"] != "leased" or not isinstance(lease, dict) or lease.get("token") != lease_token:
            raise ConflictError("stale or invalid fencing token")
        settings = load_settings(root)
        claimed = parse_timestamp(lease["claimed_at"])
        assert claimed is not None
        maximum = claimed + timedelta(seconds=int(operation["resource_budget"].get("timeout_seconds", 1800)))
        proposed = instant + timedelta(minutes=settings.operations.lease_minutes)
        lease["expires_at"] = format_timestamp(min(proposed, maximum))
        operation["updated_at"] = format_timestamp(instant)
        atomic_write_json(_operation_path(root, operation_id), operation, allowed_root=root)
        return operation


def _write_attempt_history(root: Path, operation_id: str, attempt: dict[str, Any]) -> None:
    path = root / "data" / "operations" / "history" / operation_id / f"{attempt['attempt_id']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, attempt, allowed_root=root)


def finish(
    root: Path,
    *,
    operation_id: str,
    lease_token: str,
    outcome: str,
    reason_code: str | None,
    result: dict[str, Any],
    cycle_id: str | None = None,
    known_metered_usd: Decimal | None = None,
    supplied_usage: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if outcome not in FINISH_OUTCOMES:
        raise QueueError(f"invalid finish outcome: {outcome}")
    if outcome != "succeeded" and not reason_code:
        raise QueueError("non-success outcome requires reason_code")
    instant = now or utc_now()
    with RepositoryLock(root):
        path = _operation_path(root, operation_id)
        operation = _load(path)
        lease = operation.get("lease")
        if operation["state"] != "leased" or not isinstance(lease, dict) or lease.get("token") != lease_token:
            raise ConflictError("stale or invalid fencing token")
        expiry = parse_timestamp(lease["expires_at"])
        if expiry and expiry < instant:
            raise ConflictError("lease expired; stale agent result rejected")
        cycle: dict[str, Any] | None = None
        cycle_path: Path | None = None
        if cycle_id:
            cycle_path = _cycle_path(root, cycle_id)
            cycle = _cycle(root, cycle_id, instant)
            if known_metered_usd is not None:
                total = Decimal(cycle["known_metered_usd"]) + known_metered_usd
                if total > Decimal(cycle["maximum_known_metered_usd"]):
                    raise QueueError("reported metered cost exceeds cycle ceiling")
        attempt = {
            "attempt_id": lease["attempt_id"],
            "run_id": lease["run_id"],
            "lease_token_hash": content_hash(lease_token),
            "started_at": lease["claimed_at"],
            "completed_at": format_timestamp(instant),
            "outcome": outcome,
            "reason_code": reason_code,
            "result": result,
            "supplied_usage": supplied_usage or {},
            "known_metered_usd": str(known_metered_usd) if known_metered_usd is not None else None,
            "cost_status": "known" if known_metered_usd is not None else "unknown",
        }
        operation["attempts"].append(attempt)
        operation["lease"] = None
        if outcome == "failed" and len(operation["attempts"]) < operation["max_attempts"]:
            operation["state"] = "queued"
            operation["result"] = {"retry_reason": reason_code}
        else:
            operation["state"] = outcome
            operation["result"] = {"reason_code": reason_code, **result}
        operation["updated_at"] = format_timestamp(instant)
        _write_attempt_history(root, operation_id, attempt)
        atomic_write_json(path, operation, allowed_root=root)
        if cycle is not None and cycle_path is not None:
            if known_metered_usd is None:
                if operation_id not in cycle["unknown_cost_operations"]:
                    cycle["unknown_cost_operations"].append(operation_id)
            else:
                total = Decimal(cycle["known_metered_usd"]) + known_metered_usd
                cycle["known_metered_usd"] = str(total)
            cycle["updated_at"] = format_timestamp(instant)
            cycle_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(cycle_path, cycle, allowed_root=root)
        return operation


def cancel(root: Path, operation_id: str, reason_code: str, *, now: datetime | None = None) -> dict[str, Any]:
    instant = now or utc_now()
    with RepositoryLock(root):
        operation = _load(_operation_path(root, operation_id))
        if operation["state"] == "leased":
            raise QueueError("cannot cancel an actively leased operation")
        if operation["state"] in TERMINAL:
            return operation
        operation["state"] = "cancelled"
        operation["result"] = {"reason_code": reason_code}
        operation["updated_at"] = format_timestamp(instant)
        atomic_write_json(_operation_path(root, operation_id), operation, allowed_root=root)
        return operation


def validate_operations(operations: dict[str, dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    live = [row["operation_id"] for row in operations.values() if row.get("state") == "leased"]
    if len(live) > 1:
        errors.append(f"multiple live leases: {live}")
    for operation in operations.values():
        for dependency in operation.get("depends_on", []):
            if dependency not in operations:
                errors.append(f"{operation['operation_id']}: missing dependency {dependency}")
        if len(operation.get("attempts", [])) > operation.get("max_attempts", 0):
            errors.append(f"{operation['operation_id']}: attempt ceiling exceeded")
        if operation.get("state") == "leased" and not isinstance(operation.get("lease"), dict):
            errors.append(f"{operation['operation_id']}: leased without lease object")
        if operation.get("state") != "leased" and operation.get("lease") is not None:
            errors.append(f"{operation['operation_id']}: non-leased operation retains lease")
    visiting: set[str] = set()
    visited: set[str] = set()

    def walk(node: str) -> None:
        if node in visiting:
            errors.append(f"dependency cycle includes {node}")
            return
        if node in visited:
            return
        visiting.add(node)
        for dependency in operations[node].get("depends_on", []):
            if dependency in operations:
                walk(dependency)
        visiting.remove(node)
        visited.add(node)

    for operation_id in sorted(operations):
        walk(operation_id)
    dedupe: dict[str, str] = {}
    for operation in operations.values():
        key = operation.get("dedupe_key")
        if key in dedupe and dedupe[key] != operation["operation_id"]:
            errors.append(f"duplicate dedupe key: {key}")
        dedupe[str(key)] = operation["operation_id"]
    return sorted(set(errors))


def validate_queue(root: Path) -> list[str]:
    return validate_operations(all_operations(root))
