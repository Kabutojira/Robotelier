from __future__ import annotations

import json
from pathlib import Path

import pytest

from robotelier.credentials import (
    OAUTH_CIPHERTEXT_PATH,
    CredentialError,
    bootstrap_envelope,
    restore_envelope,
    seal_envelope,
    verify_envelope,
)


def _fake_age(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    age = tmp_path / "age"
    age.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        "args = sys.argv[1:]\n"
        "if '--decrypt' in args:\n"
        "    sys.stdout.buffer.write(pathlib.Path(args[-1]).read_bytes())\n"
        "else:\n"
        "    output = pathlib.Path(args[args.index('--output') + 1])\n"
        "    output.write_bytes(pathlib.Path(args[-1]).read_bytes())\n"
    )
    age.chmod(0o700)
    keygen = tmp_path / "age-keygen"
    keygen.write_text("#!/bin/sh\nprintf '%s\\n' age1fixturepublicrecipient\n")
    keygen.chmod(0o700)
    monkeypatch.setattr(
        "robotelier.credentials.shutil.which",
        lambda name: str(age if name == "age" else keygen),
    )


def _identity(tmp_path: Path) -> Path:
    identity = tmp_path / "age-identity"
    identity.write_text("AGE-SECRET-KEY-fixture")
    identity.chmod(0o600)
    return identity


def _combined_auth(tmp_path: Path, *, paid_key: bool = False) -> Path:
    auth = {
        "version": 1,
        "active_provider": "openai-codex",
        "updated_at": "2026-09-06T00:00:00Z",
        "providers": {
            "openai-codex": {"auth_mode": "chatgpt", "tokens": {"refresh": "openai-fixture"}},
            "xai-oauth": {"auth_mode": "oauth_pkce", "tokens": {"refresh": "grok-fixture"}},
        },
        "credential_pool": {"openai-codex": [{"account": "fixture"}]},
    }
    if paid_key:
        auth["XAI_API_KEY"] = "forbidden-fixture"
    path = tmp_path / "auth.json"
    path.write_text(json.dumps(auth))
    path.chmod(0o600)
    return path


def test_combined_envelope_is_verified_and_restored_with_provider_scope(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_age(tmp_path, monkeypatch)
    identity = _identity(tmp_path)
    source = _combined_auth(tmp_path)
    sealed = bootstrap_envelope(repo, auth_file=source, identity=identity)
    assert sealed["round_trip_verified"] is True
    ciphertext = repo / OAUTH_CIPHERTEXT_PATH
    assert ciphertext.is_file()
    assert not (repo / ".robotelier/credentials/auth.json").exists()
    assert verify_envelope(repo, auth_file=source, identity=identity)["byte_for_byte"] is True

    x_home = tmp_path / "x-home"
    result = restore_envelope(repo, profile="x", home=x_home, identity=identity)
    restored = json.loads((x_home / "auth.json").read_text())
    assert result["provider"] == "openai-codex"
    assert set(restored["providers"]) == {"openai-codex"}
    assert set(restored["credential_pool"]) == {"openai-codex"}
    assert (x_home / "auth.json").stat().st_mode & 0o077 == 0

    openai_home = tmp_path / "openai-home"
    restore_envelope(repo, profile="scout", home=openai_home, identity=identity)
    openai = json.loads((openai_home / "auth.json").read_text())
    assert set(openai["providers"]) == {"openai-codex"}
    assert set(openai["credential_pool"]) == {"openai-codex"}


def test_refresh_merge_preserves_unused_provider_and_skips_unchanged_ciphertext(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_age(tmp_path, monkeypatch)
    identity = _identity(tmp_path)
    bootstrap_envelope(repo, auth_file=_combined_auth(tmp_path), identity=identity)
    x_home = tmp_path / "x-home"
    restore_envelope(repo, profile="x", home=x_home, identity=identity)
    before = (repo / OAUTH_CIPHERTEXT_PATH).read_bytes()
    assert seal_envelope(repo, profile="x", home=x_home, identity=identity)["status"] == "unchanged"
    assert (repo / OAUTH_CIPHERTEXT_PATH).read_bytes() == before

    scoped = json.loads((x_home / "auth.json").read_text())
    scoped["providers"]["openai-codex"]["tokens"]["refresh"] = "rotated-fixture"
    (x_home / "auth.json").write_text(json.dumps(scoped))
    (x_home / "auth.json").chmod(0o600)
    assert seal_envelope(repo, profile="x", home=x_home, identity=identity)["status"] == "sealed"

    openai_home = tmp_path / "openai-home"
    restore_envelope(repo, profile="scout", home=openai_home, identity=identity)
    openai = json.loads((openai_home / "auth.json").read_text())
    assert openai["providers"]["openai-codex"]["tokens"]["refresh"] == "rotated-fixture"
    combined = json.loads((repo / OAUTH_CIPHERTEXT_PATH).read_text())
    assert combined["providers"]["xai-oauth"]["tokens"]["refresh"] == "grok-fixture"
    refreshed_x_home = tmp_path / "refreshed-x-home"
    restore_envelope(repo, profile="x", home=refreshed_x_home, identity=identity)
    refreshed_x = json.loads((refreshed_x_home / "auth.json").read_text())
    assert refreshed_x["providers"]["openai-codex"]["tokens"]["refresh"] == "rotated-fixture"


def test_identity_and_plaintext_inside_public_repository_are_rejected(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_age(tmp_path, monkeypatch)
    external_identity = _identity(tmp_path)
    external_auth = _combined_auth(tmp_path)
    internal_identity = repo / "private.key"
    internal_identity.write_text("secret")
    internal_identity.chmod(0o600)
    with pytest.raises(CredentialError, match="outside"):
        bootstrap_envelope(repo, auth_file=external_auth, identity=internal_identity)
    internal_auth = repo / "auth.json"
    internal_auth.write_bytes(external_auth.read_bytes())
    internal_auth.chmod(0o600)
    with pytest.raises(CredentialError, match="outside"):
        bootstrap_envelope(repo, auth_file=internal_auth, identity=external_identity)


def test_paid_x_api_key_route_is_rejected(repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_age(tmp_path, monkeypatch)
    with pytest.raises(CredentialError, match="paid X API-key"):
        bootstrap_envelope(
            repo,
            auth_file=_combined_auth(tmp_path, paid_key=True),
            identity=_identity(tmp_path),
        )
