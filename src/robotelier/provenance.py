"""Canonical record writes, quotation policy, integrity and trace indexes."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from robotelier.config import load_settings
from robotelier.models import build_revision, load_records, record_path, validate_document
from robotelier.storage import Transaction, atomic_write_json
from robotelier.utils import ContractError, content_hash, stable_id, words


def register_revision(
    root: Path, request: dict[str, Any], *, expected_previous_hash: str | None = None
) -> dict[str, Any]:
    required = {"record_type", "id", "originating_operation_id", "body"}
    missing = sorted(required - set(request))
    if missing or not isinstance(request.get("body"), dict):
        raise ContractError(f"invalid record request; missing/body: {missing}")
    document = build_revision(
        record_type=str(request["record_type"]),
        identity=str(request["id"]),
        originating_operation_id=str(request["originating_operation_id"]),
        body=request["body"],
        supersedes=request.get("supersedes"),
        created_at=request.get("created_at"),
    )
    validate_document(root, document)
    target = record_path(root, document)
    if target.exists():
        existing = json.loads(target.read_text(encoding="utf-8"))
        if existing != document:
            raise ContractError("revision ID collision")
        return {"status": "existing", "path": target.relative_to(root).as_posix(), **document}
    transaction = Transaction(root, transaction_id=document["revision_id"])
    transaction.write_json(target.relative_to(root).as_posix(), document, expected_hash=expected_previous_hash)
    receipt = transaction.commit()
    return {
        "status": "created",
        "path": target.relative_to(root).as_posix(),
        "receipt": receipt,
        **document,
    }


def validate_quotation_budget(root: Path) -> list[str]:
    maximum = load_settings(root).evidence.quotation_words
    sources = {row["revision_id"]: row for row in load_records(root, "source_revision")}
    source_identities = {row["id"]: row for row in load_records(root, "source")}
    counts: dict[str, int] = defaultdict(int)
    for evidence in load_records(root, "evidence"):
        if evidence.get("support_kind") != "quotation":
            continue
        revision = sources.get(evidence.get("source_revision_id"))
        if revision is None:
            continue
        identity = source_identities.get(revision.get("source_id"))
        origin = identity.get("origin_group_id") if identity else revision.get("source_id")
        counts[str(origin)] += words(str(evidence.get("support", "")))
    for revision in sources.values():
        excerpt = revision.get("retained_excerpt")
        if excerpt:
            identity = source_identities.get(revision.get("source_id"))
            origin = identity.get("origin_group_id") if identity else revision.get("source_id")
            counts[str(origin)] += words(str(excerpt))
    return [
        f"origin {origin} retains {count} quoted words; maximum is {maximum}"
        for origin, count in sorted(counts.items())
        if count > maximum
    ]


def validate_source_hashes(root: Path) -> list[str]:
    errors: list[str] = []
    for revision in load_records(root, "source_revision"):
        content = revision.get("content_hash")
        scope = revision.get("hash_scope")
        status = revision.get("access_status")
        if content is None and scope != "none":
            errors.append(f"{revision['revision_id']}: null content_hash requires hash_scope=none")
        if content is not None and scope == "none":
            errors.append(f"{revision['revision_id']}: content_hash requires an actual hash scope")
        if status in {"metadata_only", "unavailable", "deleted", "access_restricted"} and scope == "full_response":
            errors.append(f"{revision['revision_id']}: access status cannot claim full-response hash")
    return errors


def _references(record: dict[str, Any]) -> set[str]:
    keys = {
        "source_id",
        "source_revision_id",
        "subject_id",
        "object_id",
        "idea_revision_id",
        "review_revision_id",
        "script_revision_id",
        "target_revision_id",
        "supersedes",
    }
    list_keys = {
        "source_ids",
        "source_revision_ids",
        "entity_ids",
        "claim_revision_ids",
        "supporting_evidence_ids",
        "contradicting_evidence_ids",
        "premise_claim_revision_ids",
        "development_ids",
        "evidence_ids",
    }
    result = {str(record[key]) for key in keys if isinstance(record.get(key), str)}
    for key in list_keys:
        value = record.get(key)
        if isinstance(value, list):
            result.update(str(item) for item in value if isinstance(item, str))
    for segment in record.get("segments", []) if isinstance(record.get("segments"), list) else []:
        if isinstance(segment, dict):
            result.update(str(item) for item in segment.get("claim_revision_ids", []))
            for candidate in segment.get("media_candidates", []):
                if isinstance(candidate, dict) and isinstance(candidate.get("media_id"), str):
                    result.add(candidate["media_id"])
    return result


def rebuild_indexes(root: Path) -> dict[str, Any]:
    records = load_records(root)
    nodes: dict[str, dict[str, str]] = {}
    forward: dict[str, list[str]] = {}
    reverse: dict[str, list[str]] = defaultdict(list)
    for record in records:
        revision_id = str(record["revision_id"])
        nodes[revision_id] = {
            "identity_id": str(record["id"]),
            "record_type": str(record["record_type"]),
            "path": record_path(root, record).relative_to(root).as_posix(),
        }
        nodes.setdefault(
            str(record["id"]),
            {
                "identity_id": str(record["id"]),
                "record_type": str(record["record_type"]),
                "path": record_path(root, record).parent.relative_to(root).as_posix(),
            },
        )
    known = set(nodes)
    for record in records:
        source = str(record["revision_id"])
        refs = sorted(ref for ref in _references(record) if ref in known)
        forward[source] = refs
        for target in refs:
            reverse[target].append(source)
    document = {
        "schema_version": 1,
        "index_hash": content_hash(nodes),
        "nodes": nodes,
        "forward": forward,
        "reverse": {key: sorted(value) for key, value in sorted(reverse.items())},
    }
    path = root / "data" / "published" / "reference-index.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, document, allowed_root=root)
    return document


def reference_errors(root: Path) -> list[str]:
    records = load_records(root)
    known = {str(row["id"]) for row in records} | {str(row["revision_id"]) for row in records}
    errors: list[str] = []
    for record in records:
        for reference in sorted(_references(record)):
            if reference not in known:
                errors.append(f"{record['revision_id']}: missing reference {reference}")
        if record.get("record_type") == "claim":
            support = record.get("supporting_evidence_ids", [])
            premises = record.get("premise_claim_revision_ids", [])
            if not support and record.get("epistemic_status") != "robotelier_inference":
                errors.append(f"{record['revision_id']}: factual claim has no supporting evidence")
            if record.get("epistemic_status") == "robotelier_inference" and not premises:
                errors.append(f"{record['revision_id']}: inference has no premise claims")
    return errors


def trace(root: Path, node_id: str) -> dict[str, object]:
    path = root / "data" / "published" / "reference-index.json"
    index: dict[str, Any]
    if path.exists():
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ContractError("reference index must be an object")
        index = loaded
    else:
        index = rebuild_indexes(root)
    if node_id not in index["nodes"]:
        raise ContractError(f"unknown trace node: {node_id}")
    seen: set[str] = set()
    queue = [node_id]
    while queue:
        node = queue.pop(0)
        if node in seen:
            continue
        seen.add(node)
        queue.extend(index["forward"].get(node, []))
        queue.extend(index["reverse"].get(node, []))
    return {"root": node_id, "nodes": {key: index["nodes"][key] for key in sorted(seen)}}


def semantic_review_record(
    *,
    target_revision_id: str,
    reviewer_operation_id: str,
    accepted: bool,
    findings: list[dict[str, Any]],
    gates: dict[str, bool],
) -> dict[str, Any]:
    identity = stable_id("review", f"{target_revision_id}:{reviewer_operation_id}")
    return build_revision(
        record_type="review",
        identity=identity,
        originating_operation_id=reviewer_operation_id,
        body={
            "target_revision_id": target_revision_id,
            "reviewer_operation_id": reviewer_operation_id,
            "accepted": accepted,
            "findings": findings,
            "gates": gates,
        },
    )
