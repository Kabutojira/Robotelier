"""Trusted, ciphertext-only Hermes OAuth handoff.

The committed envelope contains the Hermes ``auth.json`` document. Restore filters
that document to the selected profile's provider before it enters an isolated agent
home. Seal merges only that provider back into the combined document, then verifies
the new age ciphertext by decrypting it before replacing the committed artifact.
"""

from __future__ import annotations

import copy
import json
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from robotelier.config import load_settings
from robotelier.storage import atomic_write_bytes
from robotelier.utils import ContractError, content_hash

OAUTH_CIPHERTEXT_PATH = Path(".robotelier/credentials/oauth-auth.json.age")
REQUIRED_PROVIDERS = frozenset({"openai-codex"})
MAXIMUM_AUTH_BYTES = 2_000_000


class CredentialError(ContractError):
    """Raised when the ciphertext-only OAuth contract is violated."""


def _tool(name: str) -> str:
    command = shutil.which(name)
    if command is None:
        raise CredentialError(f"pinned runner does not provide the {name} executable")
    return command


def _external_private_file(root: Path, path: Path, label: str) -> Path:
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        pass
    else:
        raise CredentialError(f"{label} must remain outside the public repository")
    metadata = resolved.lstat()
    if resolved.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise CredentialError(f"{label} must be a regular file")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise CredentialError(f"{label} must be readable only by its owner")
    return resolved


def _parse_auth(raw: bytes, *, require_all: bool) -> dict[str, Any]:
    if not raw or len(raw) > MAXIMUM_AUTH_BYTES:
        raise CredentialError("Hermes auth.json is empty or exceeds the safety bound")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CredentialError("Hermes auth.json is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict) or not isinstance(value.get("providers"), dict):
        raise CredentialError("Hermes auth.json must contain a providers object")
    providers = set(value["providers"])
    if require_all and not REQUIRED_PROVIDERS.issubset(providers):
        missing = ", ".join(sorted(REQUIRED_PROVIDERS - providers))
        raise CredentialError(f"combined Hermes auth.json is missing OAuth provider(s): {missing}")
    if b"XAI_API_KEY" in raw or "xai-api-key" in providers:
        raise CredentialError("Hermes auth.json contains a forbidden paid X API-key route")
    return value


def _decrypt(identity: Path, ciphertext: Path) -> bytes:
    completed = subprocess.run(
        [_tool("age"), "--decrypt", "--identity", str(identity), str(ciphertext)],
        capture_output=True,
        check=False,
        timeout=30,
    )
    if completed.returncode != 0:
        raise CredentialError("age could not decrypt the OAuth envelope")
    return completed.stdout


def _recipient(identity: Path) -> str:
    completed = subprocess.run(
        [_tool("age-keygen"), "-y", str(identity)],
        capture_output=True,
        check=False,
        timeout=30,
        text=True,
    )
    recipient = completed.stdout.strip()
    if (
        completed.returncode != 0
        or not recipient.startswith("age1")
        or any(character.isspace() for character in recipient)
    ):
        raise CredentialError("age-keygen could not derive the OAuth recipient")
    return recipient


def _capability_document(combined: dict[str, Any], provider: str) -> dict[str, Any]:
    providers = combined["providers"]
    if provider not in providers:
        raise CredentialError(f"combined Hermes auth.json does not contain {provider}")
    filtered = copy.deepcopy(combined)
    filtered["providers"] = {provider: copy.deepcopy(providers[provider])}
    filtered["active_provider"] = provider
    pool = combined.get("credential_pool")
    if isinstance(pool, dict):
        filtered["credential_pool"] = {provider: copy.deepcopy(pool[provider])} if provider in pool else {}
    return filtered


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"


def _encrypt_verified(plaintext: bytes, identity: Path) -> bytes:
    recipient = _recipient(identity)
    temporary_directory = Path(tempfile.mkdtemp(prefix="robotelier-oauth-"))
    plaintext_path = temporary_directory / "auth.json"
    ciphertext_path = temporary_directory / "auth.json.age"
    verified_path = temporary_directory / "auth.verified.json"
    try:
        plaintext_path.write_bytes(plaintext)
        plaintext_path.chmod(0o600)
        completed = subprocess.run(
            [
                _tool("age"),
                "--encrypt",
                "--recipient",
                recipient,
                "--output",
                str(ciphertext_path),
                str(plaintext_path),
            ],
            capture_output=True,
            check=False,
            timeout=30,
        )
        if completed.returncode != 0 or not ciphertext_path.is_file() or ciphertext_path.is_symlink():
            raise CredentialError("age could not encrypt Hermes auth.json")
        verified = _decrypt(identity, ciphertext_path)
        verified_path.write_bytes(verified)
        verified_path.chmod(0o600)
        if verified != plaintext:
            raise CredentialError("OAuth ciphertext round-trip verification failed")
        ciphertext = ciphertext_path.read_bytes()
        if not ciphertext:
            raise CredentialError("age produced an empty OAuth envelope")
        return ciphertext
    finally:
        for path in (plaintext_path, ciphertext_path, verified_path):
            path.unlink(missing_ok=True)
        temporary_directory.rmdir()


def bootstrap_envelope(root: Path, *, auth_file: Path, identity: Path) -> dict[str, Any]:
    """Encrypt one external combined Hermes auth file into the exact public artifact."""

    source = _external_private_file(root, auth_file, "plaintext Hermes auth.json")
    private_identity = _external_private_file(root, identity, "age identity")
    plaintext = source.read_bytes()
    _parse_auth(plaintext, require_all=True)
    ciphertext = _encrypt_verified(plaintext, private_identity)
    destination = root / OAUTH_CIPHERTEXT_PATH
    destination.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(destination, ciphertext, allowed_root=root)
    destination.chmod(0o600)
    return {
        "status": "sealed",
        "artifact": OAUTH_CIPHERTEXT_PATH.as_posix(),
        "ciphertext_sha256": content_hash(ciphertext),
        "providers": sorted(REQUIRED_PROVIDERS),
        "round_trip_verified": True,
    }


def restore_envelope(
    root: Path,
    *,
    profile: str,
    home: Path,
    identity: Path,
) -> dict[str, Any]:
    """Restore only the selected profile's provider into its isolated Hermes home."""

    encrypted = root / OAUTH_CIPHERTEXT_PATH
    if encrypted.is_symlink() or not encrypted.is_file():
        raise CredentialError(f"required OAuth ciphertext is missing: {OAUTH_CIPHERTEXT_PATH}")
    private_identity = _external_private_file(root, identity, "age identity")
    selected = load_settings(root).profiles.get(profile)
    if selected is None:
        raise CredentialError(f"unknown credential profile: {profile}")
    combined = _parse_auth(_decrypt(private_identity, encrypted), require_all=True)
    filtered = _capability_document(combined, selected.provider)
    resolved_home = home.resolve()
    resolved_home.mkdir(parents=True, exist_ok=True)
    auth_path = resolved_home / "auth.json"
    atomic_write_bytes(auth_path, _canonical_bytes(filtered), allowed_root=resolved_home)
    auth_path.chmod(0o600)
    return {
        "status": "restored",
        "artifact": OAUTH_CIPHERTEXT_PATH.as_posix(),
        "provider": selected.provider,
        "capability_scoped": True,
    }


def seal_envelope(
    root: Path,
    *,
    profile: str,
    home: Path,
    identity: Path,
) -> dict[str, Any]:
    """Merge and verify one provider refresh without exposing the other provider."""

    selected = load_settings(root).profiles.get(profile)
    if selected is None:
        raise CredentialError(f"unknown credential profile: {profile}")
    encrypted = root / OAUTH_CIPHERTEXT_PATH
    if encrypted.is_symlink() or not encrypted.is_file():
        raise CredentialError(f"required OAuth ciphertext is missing: {OAUTH_CIPHERTEXT_PATH}")
    private_identity = _external_private_file(root, identity, "age identity")
    auth_path = home.resolve() / "auth.json"
    if auth_path.is_symlink() or not auth_path.is_file():
        raise CredentialError("refreshed Hermes auth.json must be a regular file")
    if stat.S_IMODE(auth_path.stat().st_mode) & 0o077:
        raise CredentialError("refreshed Hermes auth.json must be readable only by its owner")
    scoped = _parse_auth(auth_path.read_bytes(), require_all=False)
    if set(scoped["providers"]) != {selected.provider}:
        raise CredentialError("refreshed Hermes auth.json exceeds its provider capability")
    combined_raw = _decrypt(private_identity, encrypted)
    combined = _parse_auth(combined_raw, require_all=True)
    current_scoped = _capability_document(combined, selected.provider)
    if _canonical_bytes(current_scoped) == _canonical_bytes(scoped):
        return {
            "status": "unchanged",
            "artifact": OAUTH_CIPHERTEXT_PATH.as_posix(),
            "provider": selected.provider,
            "ciphertext_sha256": content_hash(encrypted.read_bytes()),
            "round_trip_verified": True,
        }

    combined["providers"][selected.provider] = copy.deepcopy(scoped["providers"][selected.provider])
    combined_pool = combined.get("credential_pool")
    scoped_pool = scoped.get("credential_pool")
    if isinstance(combined_pool, dict) and isinstance(scoped_pool, dict) and selected.provider in scoped_pool:
        combined_pool[selected.provider] = copy.deepcopy(scoped_pool[selected.provider])
    if "updated_at" in scoped:
        combined["updated_at"] = scoped["updated_at"]
    plaintext = _canonical_bytes(combined)
    _parse_auth(plaintext, require_all=True)
    ciphertext = _encrypt_verified(plaintext, private_identity)
    atomic_write_bytes(encrypted, ciphertext, allowed_root=root)
    encrypted.chmod(0o600)
    return {
        "status": "sealed",
        "artifact": OAUTH_CIPHERTEXT_PATH.as_posix(),
        "provider": selected.provider,
        "ciphertext_sha256": content_hash(ciphertext),
        "round_trip_verified": True,
    }


def verify_envelope(root: Path, *, auth_file: Path, identity: Path) -> dict[str, Any]:
    """Verify that the committed ciphertext decrypts byte-for-byte to an external auth file."""

    source = _external_private_file(root, auth_file, "plaintext Hermes auth.json")
    private_identity = _external_private_file(root, identity, "age identity")
    encrypted = root / OAUTH_CIPHERTEXT_PATH
    if encrypted.is_symlink() or not encrypted.is_file():
        raise CredentialError(f"required OAuth ciphertext is missing: {OAUTH_CIPHERTEXT_PATH}")
    expected = source.read_bytes()
    _parse_auth(expected, require_all=True)
    if _decrypt(private_identity, encrypted) != expected:
        raise CredentialError("committed OAuth ciphertext does not match the supplied auth.json")
    return {
        "status": "verified",
        "artifact": OAUTH_CIPHERTEXT_PATH.as_posix(),
        "ciphertext_sha256": content_hash(encrypted.read_bytes()),
        "providers": sorted(REQUIRED_PROVIDERS),
        "byte_for_byte": True,
    }
