"""Canonical record validation and immutable revision construction."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from robotelier.utils import ContractError, content_hash, format_timestamp, require_id, utc_now

RECORD_DIRECTORIES = {
    "entity": "entities",
    "relationship": "relationships",
    "source": "sources",
    "source_revision": "sources",
    "evidence": "evidence",
    "claim": "claims",
    "development": "developments",
    "media": "media",
    "idea": "ideas",
    "episode": "episodes",
    "review": "reviews",
    "script": "scripts",
}


class SchemaError(ContractError):
    pass


def validate_schemas(root: Path) -> list[str]:
    """Validate every checked-in JSON Schema and its local resource graph."""

    errors: list[str] = []
    registry = Registry()
    documents: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted((root / "schemas").glob("*.schema.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise SchemaError("schema root must be an object")
            Draft202012Validator.check_schema(value)
            registry = registry.with_resource(path.resolve().as_uri(), Resource.from_contents(value))
            documents.append((path, value))
        except (OSError, ValueError, SchemaError) as exc:
            errors.append(f"{path.relative_to(root)}: {exc}")
    if not documents:
        errors.append("schemas: no JSON Schemas found")
    for path, value in documents:
        try:
            Draft202012Validator(value, registry=registry)
        except Exception as exc:  # pragma: no cover - defensive library boundary
            errors.append(f"{path.relative_to(root)}: unresolved schema resource: {exc}")
    return errors


def schema_path(root: Path, record_type: str) -> Path:
    path = root / "schemas" / f"{record_type}.schema.json"
    if not path.is_file():
        raise SchemaError(f"unknown schema for record type: {record_type}")
    return path


def validate_document(root: Path, value: dict[str, Any], record_type: str | None = None) -> None:
    kind = record_type or value.get("record_type")
    if not isinstance(kind, str):
        raise SchemaError("record_type is required")
    path = schema_path(root, kind)
    schema = json.loads(path.read_text(encoding="utf-8"))
    schema.setdefault("$id", path.resolve().as_uri())
    registry = Registry()
    for schema_file in sorted((root / "schemas").glob("*.schema.json")):
        document = json.loads(schema_file.read_text(encoding="utf-8"))
        registry = registry.with_resource(schema_file.resolve().as_uri(), Resource.from_contents(document))
    validator = Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(value), key=lambda item: list(item.absolute_path))
    if errors:
        rendered = "; ".join(
            f"{'.'.join(map(str, error.absolute_path)) or '<root>'}: {error.message}" for error in errors
        )
        raise SchemaError(rendered)
    if value.get("record_type") != kind:
        raise SchemaError("record_type does not match selected schema")
    require_id(str(value["id"]))


def build_revision(
    *,
    record_type: str,
    identity: str,
    originating_operation_id: str,
    body: dict[str, Any],
    supersedes: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    require_id(identity)
    timestamp = created_at or format_timestamp(utc_now())
    material = {
        "schema_version": 1,
        "record_type": record_type,
        "id": identity,
        "created_at": timestamp,
        "originating_operation_id": originating_operation_id,
        "supersedes": supersedes,
        **copy.deepcopy(body),
    }
    if "revision_id" in material:
        raise ContractError("body cannot set revision_id")
    material["revision_id"] = f"rev_{content_hash(material)[:20]}"
    return material


def record_path(root: Path, document: dict[str, Any]) -> Path:
    kind = str(document["record_type"])
    directory = RECORD_DIRECTORIES.get(kind)
    if directory is None:
        raise SchemaError(f"unsupported canonical record type: {kind}")
    identity = require_id(str(document["id"]))
    revision = str(document["revision_id"])
    if not revision.startswith("rev_"):
        raise SchemaError("invalid revision_id")
    return root / "data" / "records" / directory / identity / f"{revision}.json"


def load_records(root: Path, record_type: str | None = None) -> list[dict[str, Any]]:
    directories = (
        [RECORD_DIRECTORIES[record_type]]
        if record_type in RECORD_DIRECTORIES
        else sorted(set(RECORD_DIRECTORIES.values()))
    )
    result: list[dict[str, Any]] = []
    for directory in directories:
        base = root / "data" / "records" / directory
        for path in sorted(base.glob("*/*.json")) if base.exists() else []:
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, dict) and (record_type is None or value.get("record_type") == record_type):
                result.append(value)
    return result


def current_revisions(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    superseded = {str(row["supersedes"]) for row in records if row.get("supersedes")}
    current: dict[str, dict[str, Any]] = {}
    for row in records:
        if row["revision_id"] in superseded:
            continue
        identity = str(row["id"])
        if identity in current:
            raise SchemaError(f"identity has multiple current revisions: {identity}")
        current[identity] = row
    return current
