"""Safe inspection and exact-stage recovery decisions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from robotelier.publication import outbox_path
from robotelier.storage import atomic_write_json, recover_transactions
from robotelier.utils import ContractError, format_timestamp, stable_id, utc_now


def inspect(root: Path, *, local_date: str) -> dict[str, Any]:
    path = outbox_path(root, local_date)
    outbox = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    actions: list[str] = []
    if outbox:
        for channel in ("telegram_text", "telegram_audio", "pages"):
            state = outbox[channel]["state"]
            if state in {"intent_written", "delivery_unknown", "reconciliation_required"}:
                actions.append(f"reconcile:{channel}")
            elif state == "failed":
                actions.append(f"resume_safe:{channel}")
            elif state == "pending":
                actions.append(f"continue:{channel}")
    return {
        "local_date": local_date,
        "outbox": outbox,
        "safe_actions": actions,
        "incomplete_transactions": recover_transactions(root),
    }


def resume(root: Path, request: dict[str, Any]) -> dict[str, Any]:
    local_date = str(request["local_date"])
    stage = str(request["stage"])
    state = inspect(root, local_date=local_date)
    if f"resume_safe:{stage}" not in state["safe_actions"] and f"continue:{stage}" not in state["safe_actions"]:
        raise ContractError("requested stage is not safely resumable; reconcile ambiguity first")
    receipt = {
        "schema_version": 1,
        "recovery_id": stable_id("recovery", f"{local_date}:{stage}"),
        "local_date": local_date,
        "stage": stage,
        "status": "authorized_for_same_episode",
        "created_at": format_timestamp(utc_now()),
    }
    path = root / "data" / "history" / "recoveries" / f"{receipt['recovery_id']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, receipt, allowed_root=root)
    return receipt
