"""Content snapshots and observed command receipts."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from robotelier.storage import atomic_write_json
from robotelier.utils import format_timestamp, utc_now

IGNORED = frozenset(
    {
        ".git",
        ".venv",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".hypothesis",
        "__pycache__",
        "site/node_modules",
        "site/public",
    }
)


@dataclass(frozen=True, slots=True)
class FileState:
    kind: str
    sha256: str
    size: int
    mode: int


@dataclass(frozen=True, slots=True)
class Snapshot:
    files: dict[str, FileState]


@dataclass(frozen=True, slots=True)
class Delta:
    created: tuple[str, ...]
    modified: tuple[str, ...]
    deleted: tuple[str, ...]

    @property
    def changed(self) -> tuple[str, ...]:
        return tuple(sorted((*self.created, *self.modified, *self.deleted)))


def _ignored(relative: Path) -> bool:
    value = relative.as_posix()
    return any(value == prefix or value.startswith(prefix + "/") for prefix in IGNORED)


def snapshot(root: Path) -> Snapshot:
    root = root.resolve(strict=True)
    files: dict[str, FileState] = {}
    for current, directories, names in os.walk(root, followlinks=False):
        current_path = Path(current)
        kept: list[str] = []
        for name in sorted(directories):
            path = current_path / name
            relative = path.relative_to(root)
            if _ignored(relative):
                continue
            if path.is_symlink():
                target = os.readlink(path).encode("utf-8", errors="surrogateescape")
                files[relative.as_posix()] = FileState(
                    "symlink",
                    hashlib.sha256(target).hexdigest(),
                    len(target),
                    stat.S_IMODE(path.lstat().st_mode),
                )
            else:
                kept.append(name)
        directories[:] = kept
        for name in sorted(names):
            path = current_path / name
            relative = path.relative_to(root)
            if _ignored(relative) or path.suffix == ".pyc":
                continue
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                payload = os.readlink(path).encode("utf-8", errors="surrogateescape")
                kind = "symlink"
            elif stat.S_ISREG(metadata.st_mode):
                payload = path.read_bytes()
                kind = "file"
            else:
                payload = b""
                kind = "special"
            files[relative.as_posix()] = FileState(
                kind,
                hashlib.sha256(payload).hexdigest(),
                len(payload),
                stat.S_IMODE(metadata.st_mode),
            )
    return Snapshot(files)


def compare(before: Snapshot, after: Snapshot) -> Delta:
    old, new = set(before.files), set(after.files)
    return Delta(
        tuple(sorted(new - old)),
        tuple(sorted(path for path in old & new if before.files[path] != after.files[path])),
        tuple(sorted(old - new)),
    )


def record_command(
    root: Path,
    *,
    run_id: str,
    operation_id: str,
    argv: list[str],
    exit_code: int,
    before: Snapshot,
    after: Snapshot,
) -> None:
    path = root / "data" / "runs" / run_id / operation_id / "command_audit.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        loaded = json.loads(path.read_text())
        if not isinstance(loaded, dict) or not isinstance(loaded.get("entries"), list):
            raise ValueError("command audit is not an object with entries")
        document: dict[str, object] = loaded
    else:
        document = {
            "audit_version": 1,
            "run_id": run_id,
            "operation_id": operation_id,
            "entries": [],
        }
    delta = compare(before, after)
    entries = document["entries"]
    assert isinstance(entries, list)
    entries.append(
        {
            "argv": ["robotelier", *argv],
            "exit_code": exit_code,
            "completed_at": format_timestamp(utc_now()),
            "changed_paths": list(delta.changed),
        }
    )
    atomic_write_json(path, document, allowed_root=root)
