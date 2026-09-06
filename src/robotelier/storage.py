"""Atomic Git-native storage with locks, journals, CAS and recovery."""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from collections.abc import Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from robotelier.utils import ContractError, content_hash, format_timestamp, utc_now


class UnsafeWriteError(ContractError):
    pass


class ConflictError(ContractError):
    pass


def validate_destination(destination: Path, allowed_root: Path) -> Path:
    root = allowed_root.resolve(strict=True)
    target = destination if destination.is_absolute() else root / destination
    target = target.absolute()
    try:
        relative = target.relative_to(root)
    except ValueError as exc:
        raise UnsafeWriteError(f"destination escapes allowed root: {target}") from exc
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise UnsafeWriteError(f"symlink destination is forbidden: {current}")
    if not target.parent.is_dir():
        raise UnsafeWriteError(f"destination parent does not exist: {target.parent}")
    return target


def atomic_write_bytes(destination: Path, content: bytes, *, allowed_root: Path) -> None:
    target = validate_destination(destination, allowed_root)
    descriptor, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        directory = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def atomic_write_text(destination: Path, content: str, *, allowed_root: Path) -> None:
    atomic_write_bytes(destination, content.encode("utf-8"), allowed_root=allowed_root)


def atomic_write_json(destination: Path, value: object, *, allowed_root: Path) -> None:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    atomic_write_text(destination, payload, allowed_root=allowed_root)


def append_jsonl(destination: Path, value: Mapping[str, object], *, allowed_root: Path) -> None:
    target = validate_destination(destination, allowed_root)
    line = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        pass


class RepositoryLock(AbstractContextManager["RepositoryLock"]):
    def __init__(self, root: Path, *, blocking: bool = True) -> None:
        self.root = root.resolve(strict=True)
        self.blocking = blocking
        self._handle: Any = None

    def __enter__(self) -> RepositoryLock:
        path = self.root / "data" / ".controller.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = path.open("a+")
        mode = fcntl.LOCK_EX | (0 if self.blocking else fcntl.LOCK_NB)
        try:
            fcntl.flock(self._handle, mode)
        except BlockingIOError as exc:
            self._handle.close()
            raise ConflictError("another controller owns the repository lock") from exc
        return self

    def __exit__(self, *args: object) -> None:
        if self._handle is not None:
            fcntl.flock(self._handle, fcntl.LOCK_UN)
            self._handle.close()


@dataclass(slots=True)
class PendingWrite:
    relative_path: str
    value: object
    expected_hash: str | None
    kind: str


class Transaction:
    """Controller-owned multi-file transaction with a durable recovery journal."""

    def __init__(self, root: Path, *, transaction_id: str, now: datetime | None = None) -> None:
        self.root = root.resolve(strict=True)
        self.transaction_id = transaction_id
        self.now = now or utc_now()
        self.writes: list[PendingWrite] = []

    def write_json(self, relative_path: str, value: object, *, expected_hash: str | None = None) -> None:
        path = Path(relative_path)
        if path.is_absolute() or ".." in path.parts or not relative_path.startswith("data/"):
            raise UnsafeWriteError(f"transaction path is outside data/: {relative_path}")
        if any(item.relative_path == relative_path for item in self.writes):
            raise ContractError(f"duplicate transaction path: {relative_path}")
        self.writes.append(PendingWrite(relative_path, value, expected_hash, "json"))

    def write_text(self, relative_path: str, value: str, *, expected_hash: str | None = None) -> None:
        path = Path(relative_path)
        if path.is_absolute() or ".." in path.parts or not relative_path.startswith("data/"):
            raise UnsafeWriteError(f"transaction path is outside data/: {relative_path}")
        if any(item.relative_path == relative_path for item in self.writes):
            raise ContractError(f"duplicate transaction path: {relative_path}")
        self.writes.append(PendingWrite(relative_path, value, expected_hash, "text"))

    def commit(self) -> dict[str, object]:
        if not self.writes:
            raise ContractError("transaction has no writes")
        journal_dir = self.root / "data" / "history"
        journal_dir.mkdir(parents=True, exist_ok=True)
        shard = journal_dir / f"transactions-{self.now.year}.jsonl"
        staged: list[tuple[Path, bytes, bytes | None]] = []
        with RepositoryLock(self.root):
            for item in self.writes:
                target = self.root / item.relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                validate_destination(target, self.root)
                before = target.read_bytes() if target.exists() else None
                actual = content_hash(before) if before is not None else None
                if item.expected_hash != actual and item.expected_hash is not None:
                    raise ConflictError(
                        f"CAS conflict for {item.relative_path}: expected {item.expected_hash}, got {actual}"
                    )
                if item.kind == "json":
                    payload = (
                        json.dumps(
                            item.value,
                            ensure_ascii=False,
                            sort_keys=True,
                            indent=2,
                            allow_nan=False,
                        ).encode("utf-8")
                        + b"\n"
                    )
                elif item.kind == "text" and isinstance(item.value, str):
                    payload = item.value.encode("utf-8")
                else:
                    raise ContractError(f"unsupported pending write kind: {item.kind}")
                staged.append((target, payload, before))
            prepared = {
                "event_id": f"txn-{self.transaction_id}-prepared",
                "transaction_id": self.transaction_id,
                "state": "prepared",
                "at": format_timestamp(self.now),
                "writes": [
                    {"path": item.relative_path, "sha256": content_hash(payload)}
                    for item, (_, payload, _) in zip(self.writes, staged, strict=True)
                ],
            }
            append_jsonl(shard, prepared, allowed_root=self.root)
            applied: list[tuple[Path, bytes | None]] = []
            try:
                for target, payload, before in staged:
                    atomic_write_bytes(target, payload, allowed_root=self.root)
                    applied.append((target, before))
            except BaseException:
                for target, before in reversed(applied):
                    if before is None:
                        target.unlink(missing_ok=True)
                    else:
                        atomic_write_bytes(target, before, allowed_root=self.root)
                append_jsonl(
                    shard,
                    {
                        **prepared,
                        "event_id": f"txn-{self.transaction_id}-rolled-back",
                        "state": "rolled_back",
                    },
                    allowed_root=self.root,
                )
                raise
            receipt: dict[str, object] = {
                "transaction_id": self.transaction_id,
                "state": "committed",
                "at": format_timestamp(self.now),
                "writes": prepared["writes"],
            }
            append_jsonl(
                shard,
                {**receipt, "event_id": f"txn-{self.transaction_id}-committed"},
                allowed_root=self.root,
            )
            return receipt


def recover_transactions(root: Path) -> list[str]:
    """Report prepared journals lacking a terminal record; never guesses missing bytes."""
    states: dict[str, str] = {}
    history = root / "data" / "history"
    for shard in sorted(history.glob("transactions-*.jsonl")) if history.exists() else []:
        for line in shard.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            states[str(event["transaction_id"])] = str(event["state"])
    return sorted(key for key, state in states.items() if state == "prepared")
