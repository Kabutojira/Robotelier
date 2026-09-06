"""Small deterministic helpers shared by controller modules."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SAFE_ID = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*_[0-9a-f]{20}$")
SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class ContractError(ValueError):
    """Raised when input violates a deterministic contract."""


def utc_now() -> datetime:
    return datetime.now(UTC)


def format_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ContractError("timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_timestamp(value: str, *, nullable: bool = False) -> datetime | None:
    if nullable and not value:
        return None
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ContractError(f"UTC timestamp must end in Z: {value!r}")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ContractError(f"invalid UTC timestamp: {value!r}") from exc
    return parsed.astimezone(UTC)


def canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def content_hash(value: bytes | str | object) -> str:
    if isinstance(value, str):
        payload = value.encode("utf-8")
    elif isinstance(value, bytes):
        payload = value
    else:
        payload = canonical_json(value)
    return hashlib.sha256(payload).hexdigest()


def stable_id(kind: str, basis: str) -> str:
    prefix = re.sub(r"[^a-z0-9]+", "_", kind.lower()).strip("_")
    if not prefix or not re.fullmatch(r"[a-z][a-z0-9_]*", prefix):
        raise ContractError(f"invalid identity kind: {kind!r}")
    digest = hashlib.sha256(f"robotelier:{prefix}:{basis}".encode()).hexdigest()[:20]
    return f"{prefix}_{digest}"


def require_id(value: str, *, prefix: str | None = None) -> str:
    if not isinstance(value, str) or not SAFE_ID.fullmatch(value):
        raise ContractError(f"invalid stable ID: {value!r}")
    if prefix and not value.startswith(f"{prefix}_"):
        raise ContractError(f"expected {prefix} ID, got {value!r}")
    return value


def require_run_id(value: str) -> str:
    if not SAFE_RUN_ID.fullmatch(value):
        raise ContractError(f"invalid run ID: {value!r}")
    return value


def read_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ContractError(f"request is not a regular file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"JSON document must be an object: {path}")
    return value


def require_fields(value: Mapping[str, object], fields: set[str]) -> None:
    missing = sorted(fields - set(value))
    if missing:
        raise ContractError(f"missing required fields: {missing}")


def repository_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "AGENTS.md").is_file() and (candidate / "PLAN.md").is_file():
            return candidate
    raise ContractError("not inside a Robotelier repository")


def words(value: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", value, flags=re.UNICODE))
