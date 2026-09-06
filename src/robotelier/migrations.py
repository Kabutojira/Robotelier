"""Explicit record-level schema migration boundary.

Version one is the first public canonical format.  This module intentionally
does not invent migrations for records that never existed; it gives future
changes a tested, per-record route instead of a repository-wide data project.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

from robotelier.utils import ContractError

CURRENT_SCHEMA_VERSION = 1
Migration = Callable[[dict[str, Any]], dict[str, Any]]
MIGRATIONS: dict[tuple[str, int], Migration] = {}


def migrate_record(value: dict[str, Any], *, target_version: int = CURRENT_SCHEMA_VERSION) -> dict[str, Any]:
    record = copy.deepcopy(value)
    version = record.get("schema_version")
    kind = record.get("record_type")
    if not isinstance(version, int) or version < 1:
        raise ContractError("record schema_version must be a positive integer")
    if not isinstance(kind, str) or not kind:
        raise ContractError("record_type is required for migration")
    if target_version < version:
        raise ContractError("record downgrades are forbidden")
    if target_version > CURRENT_SCHEMA_VERSION:
        raise ContractError("target schema version is not implemented")
    while version < target_version:
        migration = MIGRATIONS.get((kind, version))
        if migration is None:
            raise ContractError(f"no {kind} migration from schema version {version}")
        record = migration(record)
        next_version = record.get("schema_version")
        if next_version != version + 1:
            raise ContractError("migration did not advance exactly one schema version")
        version = next_version
    return record
