"""Editorial idea revisions, deterministic ranking and atomic selection."""

from __future__ import annotations

import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from robotelier.config import Ranking, load_settings
from robotelier.models import current_revisions, load_records
from robotelier.provenance import register_revision
from robotelier.storage import ConflictError, RepositoryLock, atomic_write_json
from robotelier.utils import ContractError, content_hash, format_timestamp, stable_id, utc_now

COMPONENTS = (
    "relevance",
    "novelty",
    "significance",
    "timeliness",
    "evidence_readiness",
    "explanatory_value",
)
PASS_GATES = ("dense_enough", "non_redundant", "evidence_ready", "standalone")


def calculate_priority(scores: dict[str, Any], policy: Ranking) -> Decimal:
    components: dict[str, Decimal] = {}
    for key in COMPONENTS:
        value = Decimal(str(scores.get(key)))
        if value < 0 or value > 5:
            raise ContractError(f"score {key} must be 0-5")
        if not scores.get(f"{key}_rationale"):
            raise ContractError(f"score {key} requires evidence-linked rationale")
        components[key] = value
    base = Decimal(20) * sum(policy.weights[key] * components[key] for key in COMPONENTS)
    modifiers = {
        "aging_bonus": (Decimal(0), policy.maximum_aging_bonus),
        "diversity_bonus": (Decimal(0), policy.maximum_diversity_bonus),
        "weekly_urgency": (Decimal(0), policy.maximum_weekly_urgency),
        "repetition_penalty": (Decimal(0), policy.maximum_repetition_penalty),
        "hype_penalty": (Decimal(0), policy.maximum_hype_penalty),
    }
    values: dict[str, Decimal] = {}
    for key, (lower, upper) in modifiers.items():
        value = Decimal(str(scores.get(key, 0)))
        if value < lower or value > upper:
            raise ContractError(f"modifier {key} outside 0-{upper}")
        values[key] = value
    total = (
        base
        + values["aging_bonus"]
        + values["diversity_bonus"]
        + values["weekly_urgency"]
        - values["repetition_penalty"]
        - values["hype_penalty"]
    )
    return max(Decimal(0), min(Decimal(100), total)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def propose(root: Path, request: dict[str, Any]) -> dict[str, Any]:
    body = request.get("body")
    if not isinstance(body, dict):
        raise ContractError("idea proposal requires body")
    identity = request.get("id") or stable_id("idea", str(body.get("listener_question", "")))
    normalized = {
        "state": body.get("state", "proposed"),
        "working_title": body.get("working_title", ""),
        "listener_question": body.get("listener_question", ""),
        "angle": body.get("angle", ""),
        "development_ids": body.get("development_ids", []),
        "claim_revision_ids": body.get("claim_revision_ids", []),
        "origin_group_ids": body.get("origin_group_ids", []),
        "evidence_gaps": body.get("evidence_gaps", []),
        "outline": body.get("outline", []),
        "estimated_duration_seconds": body.get("estimated_duration_seconds", 600),
        "novelty_comparison": body.get("novelty_comparison", ""),
        "scores": body.get("scores", {}),
        "reviewed_at": body.get("reviewed_at"),
        "revalidate_at": body.get("revalidate_at"),
        "editorial_deadline": body.get("editorial_deadline"),
        "ready_at": body.get("ready_at"),
        "gates": body.get("gates", {}),
        "related_operation_ids": body.get("related_operation_ids", []),
    }
    return register_revision(
        root,
        {
            "record_type": "idea",
            "id": identity,
            "originating_operation_id": request["originating_operation_id"],
            "body": normalized,
            "supersedes": request.get("supersedes"),
            "created_at": request.get("created_at"),
        },
    )


def review(root: Path, request: dict[str, Any]) -> dict[str, Any]:
    ideas = current_revisions(load_records(root, "idea"))
    idea_id = str(request.get("idea_id"))
    idea = ideas.get(idea_id)
    if idea is None:
        raise ContractError(f"unknown current idea: {idea_id}")
    scores = request.get("scores")
    gates = request.get("gates")
    if not isinstance(scores, dict) or not isinstance(gates, dict):
        raise ContractError("editorial review requires scores and gates")
    priority = calculate_priority(scores, load_settings(root).ranking)
    reviewed_at = request.get("reviewed_at") or format_timestamp(utc_now())
    state = (
        "ready"
        if all(gates.get(key) is True for key in PASS_GATES) and not idea["evidence_gaps"]
        else "research_needed"
    )
    body = {
        key: value
        for key, value in idea.items()
        if key
        not in {
            "schema_version",
            "record_type",
            "id",
            "revision_id",
            "created_at",
            "originating_operation_id",
            "supersedes",
        }
    }
    body.update(
        {
            "state": state,
            "scores": {
                **scores,
                "priority": str(priority),
                "policy_version": load_settings(root).ranking.policy_version,
            },
            "gates": gates,
            "reviewed_at": reviewed_at,
            "review_rationale": request.get("rationale", ""),
        }
    )
    return register_revision(
        root,
        {
            "record_type": "idea",
            "id": idea_id,
            "originating_operation_id": request["originating_operation_id"],
            "body": body,
            "supersedes": idea["revision_id"],
        },
    )


def ranked_snapshot(root: Path, *, reference_time: str) -> dict[str, Any]:
    current = current_revisions(load_records(root, "idea"))
    rows: list[dict[str, Any]] = []
    for idea in current.values():
        gates = idea.get("gates", {})
        eligible = (
            idea.get("state") == "ready"
            and not idea.get("evidence_gaps")
            and all(gates.get(key) is True for key in PASS_GATES)
            and 600 <= int(idea.get("estimated_duration_seconds", 0)) <= 1200
        )
        rows.append(
            {
                "idea_id": idea["id"],
                "idea_revision_id": idea["revision_id"],
                "priority": Decimal(str(idea.get("scores", {}).get("priority", "0"))),
                "eligible": eligible,
                "exclusion": None if eligible else "readiness_gate",
                "editorial_deadline": idea.get("editorial_deadline") or "9999-12-31T23:59:59Z",
                "ready_at": idea.get("ready_at") or idea["created_at"],
            }
        )
    rows.sort(
        key=lambda row: (
            not row["eligible"],
            -row["priority"],
            row["editorial_deadline"],
            row["ready_at"],
            row["idea_id"],
        )
    )
    serialized = [{**row, "priority": str(row["priority"])} for row in rows]
    return {
        "schema_version": 1,
        "policy_version": load_settings(root).ranking.policy_version,
        "reference_time": reference_time,
        "candidates": serialized,
        "snapshot_hash": content_hash(serialized),
    }


def select(root: Path, *, local_date: str, reference_time: str) -> dict[str, Any]:
    snapshot = ranked_snapshot(root, reference_time=reference_time)
    selected = next((row for row in snapshot["candidates"] if row["eligible"]), None)
    if selected is None:
        return {"status": "no_episode_insufficient_material", "snapshot": snapshot}
    path = root / "data" / "history" / "editorial-selections" / f"{local_date}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with RepositoryLock(root):
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(existing, dict):
                raise ConflictError("selection record must be an object")
            if existing.get("idea_revision_id") != selected["idea_revision_id"]:
                raise ConflictError("local-date selection is already owned by another idea")
            return existing
        selection = {
            "schema_version": 1,
            "local_date": local_date,
            "idea_id": selected["idea_id"],
            "idea_revision_id": selected["idea_revision_id"],
            "snapshot": snapshot,
            "reason": "highest_priority_eligible",
            "selected_at": reference_time,
        }
        atomic_write_json(path, selection, allowed_root=root)
        return selection
