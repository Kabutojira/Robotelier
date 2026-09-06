from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from robotelier.integrity import validate_integrity
from robotelier.provenance import (
    rebuild_indexes,
    reference_errors,
    semantic_review_record,
    trace,
    validate_quotation_budget,
    validate_source_hashes,
)
from robotelier.utils import stable_id


def test_complete_source_claim_wiki_trace_is_bidirectional(repo: Path, evidence_chain: dict[str, object]) -> None:
    index = rebuild_indexes(repo)
    claim = evidence_chain["claim"]
    observation = evidence_chain["observation"]
    assert isinstance(claim, dict) and isinstance(observation, dict)
    nodes = cast(dict[str, Any], trace(repo, observation["revision_id"])["nodes"])
    assert claim["revision_id"] in nodes
    reverse_nodes = cast(dict[str, Any], trace(repo, claim["revision_id"])["nodes"])
    assert observation["revision_id"] in reverse_nodes
    assert not reference_errors(repo)
    assert index["reverse"][observation["revision_id"]]


def test_metadata_only_source_cannot_claim_a_full_body_hash(repo: Path, evidence_chain: dict[str, object]) -> None:
    observation = evidence_chain["observation"]
    assert isinstance(observation, dict)
    path = repo / observation["path"]
    value = __import__("json").loads(path.read_text())
    value["access_status"] = "metadata_only"
    value["hash_scope"] = "full_response"
    path.write_text(__import__("json").dumps(value))
    assert any("cannot claim full-response" in error for error in validate_source_hashes(repo))


def test_quotation_budget_is_per_original_source_group(repo: Path, evidence_chain: dict[str, object]) -> None:
    evidence = evidence_chain["evidence"]
    assert isinstance(evidence, dict)
    path = repo / evidence["path"]
    value = __import__("json").loads(path.read_text())
    value["support_kind"] = "quotation"
    value["support"] = "one two three four five six seven eight nine ten " * 3
    path.write_text(__import__("json").dumps(value))
    assert validate_quotation_budget(repo)


def test_semantic_review_can_reject_reachable_but_irrelevant_citation() -> None:
    review = semantic_review_record(
        target_revision_id="rev_" + "1" * 20,
        reviewer_operation_id=stable_id("operation", "semantic-review"),
        accepted=False,
        findings=[
            {
                "code": "unsupported_clause",
                "clause": "The robot was fully autonomous.",
                "reason": "The reachable source reports supervised trials only.",
            }
        ],
        gates={"factual_support": False},
    )
    assert review["accepted"] is False
    assert review["findings"][0]["code"] == "unsupported_clause"


def test_strict_integrity_rejects_media_bytes_and_embedded_data(repo: Path) -> None:
    media = repo / "data/wiki/media/forbidden.mp3"
    media.write_bytes(b"not really audio")
    embedded = repo / "data/wiki/media/embedded.md"
    embedded.write_text("data:image/png;base64,AAAA")
    errors = validate_integrity(repo, strict=True)
    assert any("retained media" in error for error in errors)
    assert any("embedded base64" in error for error in errors)


def test_distinct_robot_version_identity_does_not_transfer_claims(evidence_chain: dict[str, object]) -> None:
    entity = evidence_chain["entity"]
    claim = evidence_chain["claim"]
    assert isinstance(entity, dict) and isinstance(claim, dict)
    other = stable_id("entity_robot_version", "fixturebot:v3")
    assert entity["id"] != other
    assert claim["subject_id"] == entity["id"]
    assert claim["subject_id"] != other
