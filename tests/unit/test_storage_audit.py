from __future__ import annotations

from pathlib import Path

import pytest

from robotelier.audit import compare, snapshot
from robotelier.storage import ConflictError, Transaction, UnsafeWriteError, atomic_write_text, recover_transactions
from robotelier.utils import content_hash


def test_atomic_write_rejects_escape(repo: Path, tmp_path: Path) -> None:
    with pytest.raises(UnsafeWriteError):
        atomic_write_text(tmp_path / "outside.txt", "no", allowed_root=repo)


def test_transaction_writes_multiple_files_and_journals(repo: Path) -> None:
    transaction = Transaction(repo, transaction_id="fixture-transaction")
    transaction.write_json("data/history/a.json", {"value": 1})
    transaction.write_text("data/history/b.txt", "two\n")
    receipt = transaction.commit()
    assert receipt["state"] == "committed"
    assert (repo / "data/history/a.json").read_text().endswith("\n")
    assert (repo / "data/history/b.txt").read_text() == "two\n"
    assert recover_transactions(repo) == []


def test_transaction_cas_conflict_leaves_every_target_unchanged(repo: Path) -> None:
    first = repo / "data/history/first.json"
    second = repo / "data/history/second.json"
    first.write_text('{"old":1}\n')
    second.write_text('{"old":2}\n')
    transaction = Transaction(repo, transaction_id="cas-conflict")
    transaction.write_json("data/history/first.json", {"new": 1}, expected_hash=content_hash(first.read_bytes()))
    transaction.write_json("data/history/second.json", {"new": 2}, expected_hash="0" * 64)
    with pytest.raises(ConflictError):
        transaction.commit()
    assert first.read_text() == '{"old":1}\n'
    assert second.read_text() == '{"old":2}\n'


def test_snapshot_observes_created_modified_and_deleted(repo: Path) -> None:
    path = repo / "data/history/snapshot.txt"
    before = snapshot(repo)
    path.write_text("first")
    created = compare(before, snapshot(repo))
    assert "data/history/snapshot.txt" in created.created
    middle = snapshot(repo)
    path.write_text("second")
    modified = compare(middle, snapshot(repo))
    assert "data/history/snapshot.txt" in modified.modified
    middle = snapshot(repo)
    path.unlink()
    deleted = compare(middle, snapshot(repo))
    assert "data/history/snapshot.txt" in deleted.deleted


def test_snapshot_records_symlinks_without_following(repo: Path, tmp_path: Path) -> None:
    link = repo / "data/history/escape"
    link.symlink_to(tmp_path)
    state = snapshot(repo).files["data/history/escape"]
    assert state.kind == "symlink"
