"""Stable identities, canonical URLs and hostile-URL rejection."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from robotelier.utils import ContractError, stable_id

TRACKING_KEYS = frozenset(
    {
        "fbclid",
        "gclid",
        "mc_cid",
        "mc_eid",
        "ref",
        "ref_src",
        "source",
    }
)
SIGNED_KEYS = frozenset(
    {
        "signature",
        "sig",
        "token",
        "auth",
        "authorization",
        "credential",
        "expires",
        "x-amz-signature",
        "x-amz-credential",
        "x-goog-signature",
        "policy",
        "key-pair-id",
    }
)


def _unsafe_host(host: str) -> bool:
    normalized = host.rstrip(".").lower()
    if normalized in {"localhost", "localhost.localdomain"} or normalized.endswith(".local"):
        return True
    try:
        address = ipaddress.ip_address(normalized.strip("[]"))
    except ValueError:
        return False
    return not address.is_global


def canonical_url(raw: str, *, remove_tracking: bool = True) -> str:
    if not isinstance(raw, str) or len(raw) > 4096:
        raise ContractError("URL is missing or too long")
    parsed = urlsplit(raw.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ContractError(f"unsupported URL: {raw!r}")
    if parsed.username or parsed.password:
        raise ContractError("credential-bearing URL is forbidden")
    if _unsafe_host(parsed.hostname):
        raise ContractError("private, loopback, link-local and metadata-service URLs are forbidden")
    host = parsed.hostname.encode("idna").decode("ascii").lower()
    port = parsed.port
    if port and not (
        (parsed.scheme.lower() == "http" and port == 80) or (parsed.scheme.lower() == "https" and port == 443)
    ):
        host = f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query = parse_qsl(parsed.query, keep_blank_values=True)
    if remove_tracking:
        query = [
            pair for pair in query if not pair[0].lower().startswith("utm_") and pair[0].lower() not in TRACKING_KEYS
        ]
    return urlunsplit((parsed.scheme.lower(), host, path, urlencode(sorted(query)), ""))


def has_signed_query(raw: str) -> bool:
    parsed = urlsplit(raw)
    keys = {key.lower() for key, _ in parse_qsl(parsed.query, keep_blank_values=True)}
    return bool(keys & SIGNED_KEYS) or any("signature" in key or "credential" in key for key in keys)


def safe_media_asset_url(raw: str | None) -> tuple[str | None, str]:
    if raw is None:
        return None, "unknown"
    if not isinstance(raw, str):
        raise ContractError("media asset URL must be a string or null")
    if not raw.strip():
        return None, "unknown"
    canonical = canonical_url(raw, remove_tracking=True)
    if has_signed_query(raw):
        return None, "omitted_signed"
    return canonical, "stable"


def source_identity(url: str, *, platform: str | None = None, external_id: str | None = None) -> str:
    basis = f"{platform}:{external_id}" if platform and external_id else canonical_url(url)
    return stable_id("source", basis)


def entity_identity(entity_type: str, verified_basis: str) -> str:
    return stable_id(f"entity_{entity_type}", verified_basis.strip().casefold())


def media_identity(page_url: str, *, platform: str | None = None, external_id: str | None = None) -> str:
    basis = f"{platform}:{external_id}" if platform and external_id else canonical_url(page_url)
    return stable_id("media", basis)
