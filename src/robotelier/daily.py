"""Deterministic daily phase manifests and dry-run controls."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from robotelier.cadence import activate, slot_for_date
from robotelier.config import load_settings
from robotelier.editorial import select
from robotelier.operations import enqueue, initialize_cycle, validate_queue
from robotelier.operations import prepare as prepare_queue
from robotelier.reports import build_daily_report
from robotelier.storage import atomic_write_json
from robotelier.utils import ContractError, format_timestamp, read_json, utc_now


def _seed_daily_operations(root: Path, *, intended_local_date: str) -> list[str]:
    prefix = f"daily:{intended_local_date}"
    discovery = enqueue(
        root,
        {
            "operation_type": "discovery",
            "dedupe_key": f"{prefix}:discovery",
            "priority": 90,
            "prompt": (
                "Run bounded non-X discovery from the active versioned registry and query definitions. "
                "Register source and media metadata before classification; report each adapter's coverage."
            ),
            "inputs": {
                "intended_local_date": intended_local_date,
                "registry_path": "data/subscriptions/registry.json",
                "queries_path": "data/subscriptions/queries.json",
            },
        },
    )
    x_research = enqueue(
        root,
        {
            "operation_type": "x_research",
            "dedupe_key": f"{prefix}:x-research",
            "priority": 90,
            "prompt": (
                "Run bounded read-only X-focused discovery with the controller-provisioned "
                "openai-codex/gpt-5.6-sol profile. Record resolvable originating-post evidence "
                "or an explicit degraded/unsourced outcome."
            ),
            "inputs": {
                "intended_local_date": intended_local_date,
                "queries_path": "data/subscriptions/queries.json",
            },
        },
    )
    triage = enqueue(
        root,
        {
            "operation_type": "triage",
            "dedupe_key": f"{prefix}:triage",
            "priority": 70,
            "depends_on": [discovery["operation_id"]],
            "prompt": (
                "Classify registered candidates and enqueue at most five specific substantive investigations. "
                "Treat X degradation as a visible coverage gap, not a blocker for supported non-X research."
            ),
            "inputs": {"intended_local_date": intended_local_date},
        },
    )
    ideas = enqueue(
        root,
        {
            "operation_type": "editorial_ideas",
            "dedupe_key": f"{prefix}:editorial-ideas",
            "priority": 40,
            "depends_on": [triage["operation_id"]],
            "prompt": (
                "Propose or revise evidence-linked podcast ideas from accepted new research and older "
                "uncovered findings; do not force thin material into an episode."
            ),
            "inputs": {"intended_local_date": intended_local_date},
        },
    )
    review = enqueue(
        root,
        {
            "operation_type": "editorial_review",
            "dedupe_key": f"{prefix}:editorial-review",
            "priority": 30,
            "depends_on": [ideas["operation_id"]],
            "prompt": (
                "Independently review the full active idea set, record rubric scores and readiness gates, "
                "and leave deterministic selection to the controller."
            ),
            "inputs": {"intended_local_date": intended_local_date},
        },
    )
    return [
        discovery["operation_id"],
        x_research["operation_id"],
        triage["operation_id"],
        ideas["operation_id"],
        review["operation_id"],
    ]


def prepare(
    root: Path,
    *,
    run_id: str,
    intended_local_date: str,
    trigger: str,
    dry_run: bool,
    maximum_operations: int,
    publish_pages: bool,
    send_telegram: bool,
    resume_id: str | None,
) -> dict[str, Any]:
    from datetime import date

    slot = slot_for_date(root, date.fromisoformat(intended_local_date))
    configured_maximum = load_settings(root).budgets.maximum_operations
    if not 1 <= maximum_operations <= configured_maximum:
        raise ContractError(f"maximum_operations must be between 1 and {configured_maximum}")
    queue_state: dict[str, Any]
    seeded_operations: list[str] = []
    if dry_run:
        errors = validate_queue(root)
        queue_state = {"validated": not errors, "errors": errors, "mutated": False}
    else:
        activate(root)
        initialize_cycle(root, cycle_id=intended_local_date, maximum_operations=maximum_operations)
        seeded_operations = _seed_daily_operations(root, intended_local_date=intended_local_date)
        queue_state = prepare_queue(root)
    document = {
        "schema_version": 1,
        "run_id": run_id,
        "intended_local_date": intended_local_date,
        "trigger": trigger,
        "dry_run": dry_run,
        "maximum_operations": maximum_operations,
        "publish_pages": publish_pages,
        "send_telegram": send_telegram,
        "resume_id": resume_id,
        "slot": slot,
        "phase": "prepared",
        "prepared_at": format_timestamp(utc_now()),
        "queue": queue_state,
        "seeded_operations": seeded_operations,
    }
    if dry_run:
        document["dry_run_guarantees"] = [
            "no_inference",
            "no_network_research",
            "no_commit",
            "no_push",
            "no_render",
            "no_delivery",
        ]
        return document
    path = root / "data" / "runs" / run_id / "daily_run.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, document, allowed_root=root)
    return document


def finalize(root: Path, *, run_id: str, incidents: list[str] | None = None) -> dict[str, Any]:
    path = root / "data" / "runs" / run_id / "daily_run.json"
    if not path.exists():
        raise ContractError("daily run was not prepared")
    document = read_json(path)
    selection = select(
        root,
        local_date=document["intended_local_date"],
        reference_time=format_timestamp(utc_now()),
    )
    production: dict[str, Any] = {
        "selection": selection,
        "status": (
            "selection_ready_for_committed_freeze"
            if selection.get("idea_revision_id")
            else "no_episode_insufficient_material"
        ),
    }
    report = build_daily_report(root, local_date=document["intended_local_date"], incidents=incidents)
    document.update(
        {
            "phase": "finalized",
            "finalized_at": format_timestamp(utc_now()),
            "report_path": report["report_path"],
            "report_hash": report["hash"],
            "production": production,
        }
    )
    atomic_write_json(path, document, allowed_root=root)
    return document
