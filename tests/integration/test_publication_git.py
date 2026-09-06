from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from robotelier.publication import PublicationError, apply_runtime_bundle, create_runtime_bundle


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(["git", *arguments], cwd=root, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def test_exact_base_runtime_bundle_does_not_stage_caller_index_and_applies_allowlisted_data(
    repo: Path, tmp_path: Path
) -> None:
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Fixture")
    _git(repo, "config", "user.email", "fixture@example.invalid")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "fixture base")
    base = _git(repo, "rev-parse", "HEAD")
    log = repo / "data/wiki/log.md"
    log.write_text(log.read_text() + "\nFixture runtime update.\n")
    bundle = tmp_path / "bundle"
    manifest = create_runtime_bundle(repo, bundle, run_id="fixture", base_sha=base)
    assert manifest["changed_paths"] == ["data/wiki/log.md"]
    assert _git(repo, "diff", "--cached", "--name-only") == ""
    target = tmp_path / "target"
    _git(tmp_path, "clone", str(repo), str(target))
    applied = apply_runtime_bundle(target, bundle)
    assert applied == manifest
    assert _git(target, "diff", "--cached", "--name-only") == "data/wiki/log.md"


def test_runtime_bundle_rejects_tamper_dirty_checkout_and_wrong_base(repo: Path, tmp_path: Path) -> None:
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Fixture")
    _git(repo, "config", "user.email", "fixture@example.invalid")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "fixture base")
    base = _git(repo, "rev-parse", "HEAD")
    path = repo / "data/wiki/log.md"
    path.write_text(path.read_text() + "\nRuntime update.\n")
    bundle = tmp_path / "bundle"
    create_runtime_bundle(repo, bundle, run_id="fixture", base_sha=base)
    target = tmp_path / "target"
    _git(tmp_path, "clone", str(repo), str(target))
    (target / "unrelated.txt").write_text("dirty")
    with pytest.raises(PublicationError, match="clean"):
        apply_runtime_bundle(target, bundle)
    (target / "unrelated.txt").unlink()
    _git(target, "config", "user.name", "Fixture")
    _git(target, "config", "user.email", "fixture@example.invalid")
    (target / "AGENTS.md").write_text((target / "AGENTS.md").read_text() + "\n")
    _git(target, "add", "AGENTS.md")
    _git(target, "commit", "-m", "new base")
    with pytest.raises(PublicationError, match="not at runtime bundle base"):
        apply_runtime_bundle(target, bundle)
