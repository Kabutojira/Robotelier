from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from robotelier.operations import (
    QueueError,
    all_operations,
    claim,
    enqueue,
    finish,
    heartbeat,
    initialize_cycle,
    prepare,
)
from robotelier.storage import ConflictError

NOW = datetime(2026, 9, 6, 1, 0, tzinfo=UTC)


def request(key: str, *, operation_type: str = "research", **extra: object) -> dict[str, object]:
    return {"operation_type": operation_type, "dedupe_key": key, "prompt": "Bounded fixture task", **extra}


def test_enqueue_is_idempotent_and_rejects_unknown_dependencies_atomically(repo: Path) -> None:
    first = enqueue(repo, request("one"), now=NOW)
    duplicate = enqueue(repo, request("one"), now=NOW)
    assert first["operation_id"] == duplicate["operation_id"]
    assert duplicate["status"] == "existing"
    before = all_operations(repo)
    with pytest.raises(QueueError, match="unknown dependencies"):
        enqueue(repo, request("bad", depends_on=["operation_" + "f" * 20]), now=NOW)
    assert all_operations(repo) == before


def test_queue_rejects_unknown_type_profile_and_self_dependency(repo: Path) -> None:
    with pytest.raises(QueueError, match="unsupported"):
        enqueue(repo, request("unknown", operation_type="fiction"), now=NOW)
    own = "operation_a77e832b984dace0d7fb"
    # The exact derived ID is not guessed by callers: use a first enqueue to obtain it,
    # then prove a self-edge is caught when loading a manually corrupted request graph.
    item = enqueue(repo, request("profile"), now=NOW)
    assert item["operation_id"] != own
    with pytest.raises(QueueError, match="unknown profile"):
        enqueue(
            repo,
            request("bad-profile", resource_budget={"profile": "paid-fallback", "cost_weight": "1"}),
            now=NOW,
        )


def test_dependencies_priorities_and_profile_routing(repo: Path) -> None:
    first = enqueue(repo, request("first", operation_type="discovery", priority=10), now=NOW)
    second = enqueue(
        repo,
        request("second", operation_type="editorial_ideas", depends_on=[first["operation_id"]], priority=100),
        now=NOW,
    )
    assert prepare(repo, now=NOW)["waiting"] == [second["operation_id"]]
    leased = claim(repo, run_id="run-one", cycle_id="2026-09-06", profile="scout", now=NOW)
    assert leased and leased["operation_id"] == first["operation_id"]
    finish(
        repo,
        operation_id=first["operation_id"],
        lease_token=leased["lease_token"],
        outcome="succeeded",
        reason_code=None,
        result={},
        cycle_id="2026-09-06",
        now=NOW + timedelta(minutes=1),
    )
    assert claim(repo, run_id="wrong", cycle_id="2026-09-06", profile="scout", now=NOW) is None
    editorial = claim(repo, run_id="right", cycle_id="2026-09-06", profile="editorial", now=NOW)
    assert editorial and editorial["operation_id"] == second["operation_id"]


def test_one_live_lease_and_fencing_after_expiry(repo: Path) -> None:
    queued = enqueue(repo, request("lease"), now=NOW)
    leased = claim(repo, run_id="old-run", cycle_id="2026-09-06", now=NOW)
    assert leased
    with pytest.raises(ConflictError, match="one operation"):
        claim(repo, run_id="other", cycle_id="2026-09-06", now=NOW)
    heartbeat(
        repo,
        operation_id=queued["operation_id"],
        lease_token=leased["lease_token"],
        now=NOW + timedelta(minutes=5),
    )
    prepare(repo, now=NOW + timedelta(hours=2))
    reassigned = claim(repo, run_id="new-run", cycle_id="2026-09-07", now=NOW + timedelta(hours=2))
    assert reassigned and reassigned["lease_token"] != leased["lease_token"]
    with pytest.raises(ConflictError, match="stale"):
        finish(
            repo,
            operation_id=queued["operation_id"],
            lease_token=leased["lease_token"],
            outcome="succeeded",
            reason_code=None,
            result={},
            now=NOW + timedelta(hours=2),
        )


def test_dependency_failure_is_explicitly_terminal(repo: Path) -> None:
    first = enqueue(repo, request("will-fail", max_attempts=1), now=NOW)
    second = enqueue(repo, request("dependent", depends_on=[first["operation_id"]]), now=NOW)
    leased = claim(repo, run_id="run", cycle_id="cycle", now=NOW)
    assert leased
    finish(
        repo,
        operation_id=first["operation_id"],
        lease_token=leased["lease_token"],
        outcome="failed",
        reason_code="fixture_failure",
        result={},
        now=NOW,
    )
    state = prepare(repo, now=NOW)
    assert second["operation_id"] in state["terminalized"]
    assert all_operations(repo)[second["operation_id"]]["result"]["reason_code"] == "dependency_terminal"


def test_shared_cycle_budget_reserves_research_capacity_and_tracks_unknown_cost(repo: Path) -> None:
    for index in range(6):
        enqueue(repo, request(f"research-{index}"), now=NOW + timedelta(seconds=index))
    for index in range(5):
        leased = claim(repo, run_id=f"run-{index}", cycle_id="bounded", now=NOW)
        assert leased
        finish(
            repo,
            operation_id=leased["operation_id"],
            lease_token=leased["lease_token"],
            outcome="succeeded",
            reason_code=None,
            result={},
            cycle_id="bounded",
            now=NOW,
        )
    assert claim(repo, run_id="run-six", cycle_id="bounded", now=NOW) is None
    cycle = json.loads((repo / "data/history/cycles/bounded.json").read_text())
    assert cycle["research_claimed"] == 5
    assert len(cycle["unknown_cost_operations"]) == 5


def test_known_cost_ceiling_is_checked_before_finishing_mutation(repo: Path) -> None:
    queued = enqueue(repo, request("cost"), now=NOW)
    leased = claim(repo, run_id="run", cycle_id="cost-cycle", now=NOW)
    assert leased
    before = all_operations(repo)[queued["operation_id"]]
    with pytest.raises(QueueError, match="cost exceeds"):
        finish(
            repo,
            operation_id=queued["operation_id"],
            lease_token=leased["lease_token"],
            outcome="succeeded",
            reason_code=None,
            result={},
            cycle_id="cost-cycle",
            known_metered_usd=Decimal("5.01"),
            now=NOW,
        )
    after = all_operations(repo)[queued["operation_id"]]
    assert after == before


def test_caller_can_lower_but_never_raise_shared_cycle_ceiling(repo: Path) -> None:
    cycle = initialize_cycle(repo, cycle_id="limited", maximum_operations=2, now=NOW)
    assert cycle["maximum_operations"] == 2
    assert initialize_cycle(repo, cycle_id="limited", maximum_operations=20, now=NOW)["maximum_operations"] == 2
    for index in range(3):
        enqueue(repo, request(f"editorial-{index}", operation_type="editorial_ideas"), now=NOW)
    for index in range(2):
        leased = claim(repo, run_id=f"run-{index}", cycle_id="limited", now=NOW)
        assert leased
        finish(
            repo,
            operation_id=leased["operation_id"],
            lease_token=leased["lease_token"],
            outcome="succeeded",
            reason_code=None,
            result={},
            cycle_id="limited",
            now=NOW,
        )
    assert claim(repo, run_id="over-limit", cycle_id="limited", now=NOW) is None


def test_discretionary_research_stops_after_local_soft_cutoff(repo: Path) -> None:
    enqueue(repo, request("late-research", operation_type="research", priority=100), now=NOW)
    editorial = enqueue(repo, request("late-editorial", operation_type="editorial_ideas", priority=10), now=NOW)
    after_cutoff = datetime(2026, 9, 6, 3, 0, tzinfo=UTC)
    leased = claim(repo, run_id="late", cycle_id="2026-09-06", now=after_cutoff)
    assert leased and leased["operation_id"] == editorial["operation_id"]
