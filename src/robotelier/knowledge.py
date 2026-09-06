"""Native-compatible Markdown validation and deterministic public views."""

from __future__ import annotations

import html
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from robotelier.config import load_settings
from robotelier.models import load_records
from robotelier.provenance import rebuild_indexes
from robotelier.storage import atomic_write_json, atomic_write_text
from robotelier.utils import ContractError, content_hash, stable_id

PAGE_TYPES = frozenset(
    {
        "company",
        "robot",
        "technology",
        "relationship",
        "event",
        "news",
        "research",
        "comparison",
        "source",
        "media",
        "podcast_idea",
        "podcast",
        "daily_report",
    }
)
EXEMPT = frozenset({"SCHEMA.md", "index.md", "log.md", "research-catalog.md"})
CLAIM_COMMENT = re.compile(r"^<!-- claims: (rev_[0-9a-f]{20}(?:, rev_[0-9a-f]{20})*) -->$")


def parse_page(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ContractError("missing YAML frontmatter")
    try:
        _, raw, body = text.split("---\n", 2)
        frontmatter = yaml.safe_load(raw)
    except (ValueError, yaml.YAMLError) as exc:
        raise ContractError(f"invalid YAML frontmatter: {exc}") from exc
    if not isinstance(frontmatter, dict):
        raise ContractError("frontmatter must be an object")
    return frontmatter, body


def lint_wiki(root: Path) -> list[str]:
    wiki = root / "data" / "wiki"
    claims = {row["revision_id"] for row in load_records(root, "claim")}
    evidence = {row["revision_id"] for row in load_records(root, "evidence")}
    errors: list[str] = []
    page_ids: set[str] = set()
    linked_paths: set[str] = set()
    settings = load_settings(root)
    for path in sorted(wiki.rglob("*.md")):
        relative = path.relative_to(wiki).as_posix()
        if path.stat().st_size > settings.evidence.maximum_page_bytes:
            errors.append(f"{relative}: page exceeds configured byte limit")
        if relative in EXEMPT or relative.startswith("_archive/"):
            continue
        try:
            frontmatter, body = parse_page(path)
        except ContractError as exc:
            errors.append(f"{relative}: {exc}")
            continue
        required = {
            "page_id",
            "title",
            "type",
            "language",
            "status",
            "created_at",
            "updated_at",
            "as_of",
            "review_at",
            "entity_ids",
            "claim_revision_ids",
            "provenance_revision_ids",
        }
        missing = sorted(required - set(frontmatter))
        if missing:
            errors.append(f"{relative}: missing frontmatter {missing}")
        if frontmatter.get("language") != "en" or frontmatter.get("type") not in PAGE_TYPES:
            errors.append(f"{relative}: invalid language or page type")
        page_id = frontmatter.get("page_id")
        if page_id in page_ids:
            errors.append(f"{relative}: duplicate page_id {page_id}")
        elif isinstance(page_id, str):
            page_ids.add(page_id)
        declared = set(frontmatter.get("claim_revision_ids", []))
        missing_claims = sorted(declared - claims)
        if missing_claims:
            errors.append(f"{relative}: unknown claim revisions {missing_claims}")
        for revision in frontmatter.get("provenance_revision_ids", []):
            if revision not in evidence and revision not in claims:
                errors.append(f"{relative}: unknown provenance revision {revision}")
        lines = body.splitlines()
        for index, line in enumerate(lines):
            if not line.startswith("## "):
                continue
            marker = lines[index + 1].strip() if index + 1 < len(lines) else ""
            match = CLAIM_COMMENT.fullmatch(marker)
            if marker != "<!-- nonfactual -->" and not match:
                errors.append(f"{relative}:{index + 1}: section lacks claims/nonfactual marker")
            if match:
                section_claims = set(match.group(1).split(", "))
                if not section_claims <= declared:
                    errors.append(f"{relative}:{index + 1}: section claims absent from frontmatter")
        for match in re.finditer(r"\[[^]]+\]\(([^)]+)\)", body):
            target = match.group(1).split("#", 1)[0]
            if target.startswith(("http://", "https://", "mailto:")) or not target:
                continue
            resolved = (path.parent / target).resolve()
            try:
                rel_target = resolved.relative_to(wiki.resolve()).as_posix()
            except ValueError:
                errors.append(f"{relative}: link escapes wiki: {target}")
                continue
            linked_paths.add(rel_target)
            if not resolved.exists():
                errors.append(f"{relative}: broken link: {target}")
    maintained = {
        path.relative_to(wiki).as_posix()
        for path in wiki.rglob("*.md")
        if path.relative_to(wiki).as_posix() not in EXEMPT
        and not path.relative_to(wiki).as_posix().startswith(("_archive/", "_meta/"))
    }
    index_text = (wiki / "index.md").read_text(encoding="utf-8") if (wiki / "index.md").exists() else ""
    for relative in sorted(maintained):
        if relative not in index_text and relative not in linked_paths:
            errors.append(f"{relative}: maintained page is orphaned")
    return sorted(set(errors))


def render_page(
    *,
    title: str,
    page_type: str,
    body_sections: list[dict[str, Any]],
    created_date: str,
    entity_ids: list[str],
    claim_revision_ids: list[str],
    evidence_revision_ids: list[str],
    status: str = "maintained",
    page_id: str | None = None,
) -> str:
    identity = page_id or stable_id("wiki", f"{page_type}:{title}")
    frontmatter = {
        "page_id": identity,
        "title": title,
        "type": page_type,
        "language": "en",
        "status": status,
        "created_at": created_date,
        "updated_at": created_date,
        "as_of": created_date,
        "review_at": None,
        "entity_ids": entity_ids,
        "claim_revision_ids": sorted(set(claim_revision_ids)),
        "provenance_revision_ids": sorted(set(evidence_revision_ids)),
    }
    lines = [
        "---",
        yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).strip(),
        "---",
        "",
        f"# {title}",
        "",
    ]
    for section in body_sections:
        lines.append(f"## {section['heading']}")
        claims = section.get("claim_revision_ids", [])
        lines.append(f"<!-- claims: {', '.join(claims)} -->" if claims else "<!-- nonfactual -->")
        lines.extend(["", str(section["text"]).strip(), ""])
    return "\n".join(lines).rstrip() + "\n"


def build_wiki(root: Path) -> dict[str, Any]:
    wiki = root / "data" / "wiki"
    pages: list[tuple[str, str]] = []
    by_type: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for path in sorted(wiki.rglob("*.md")):
        relative = path.relative_to(wiki).as_posix()
        if relative in EXEMPT or relative.startswith(("_archive/", "_meta/", "raw/", "inbox/")):
            continue
        try:
            frontmatter, _ = parse_page(path)
        except ContractError:
            continue
        pair = (str(frontmatter.get("title", path.stem)), relative)
        pages.append(pair)
        by_type[str(frontmatter.get("type", "unknown"))].append(pair)
    lines = ["# Robotelier", "", "Evidence-backed robotics research and podcast transcripts.", ""]
    for page_type in sorted(by_type):
        lines.extend([f"## {page_type.replace('_', ' ').title()}", ""])
        for title, relative in sorted(by_type[page_type]):
            lines.append(f"- [{title}]({relative})")
        lines.append("")
    atomic_write_text(wiki / "index.md", "\n".join(lines), allowed_root=root)
    reference_index = rebuild_indexes(root)
    catalog = {
        "schema_version": 1,
        "pages": [{"title": title, "path": relative} for title, relative in sorted(pages)],
        "reference_index_hash": reference_index["index_hash"],
    }
    meta = wiki / "_meta"
    meta.mkdir(parents=True, exist_ok=True)
    atomic_write_json(meta / "catalog.json", catalog, allowed_root=root)
    published = root / "data" / "published" / "site"
    published.mkdir(parents=True, exist_ok=True)
    for title, relative in pages:
        source = wiki / relative
        output = published / Path(relative).with_suffix(".html")
        output.parent.mkdir(parents=True, exist_ok=True)
        text = source.read_text(encoding="utf-8")
        escaped = html.escape(text)
        document = (
            '<!doctype html><html lang="en"><meta charset="utf-8">'
            f"<title>{html.escape(title)}</title><body><pre>{escaped}</pre></body></html>\n"
        )
        atomic_write_text(output, document, allowed_root=root)
    return {"pages": len(pages), "catalog_hash": content_hash(catalog)}
