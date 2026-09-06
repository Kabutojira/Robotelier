from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from robotelier.config import ConfigurationError, load_settings
from robotelier.identity import canonical_url, entity_identity, safe_media_asset_url, source_identity
from robotelier.migrations import migrate_record
from robotelier.utils import ContractError


def test_checked_in_configuration_has_authoritative_limits(repo: Path) -> None:
    settings = load_settings(repo)
    assert settings.budgets.maximum_operations == 20
    assert str(settings.budgets.maximum_known_usd) == "5.00"
    assert str(settings.budgets.maximum_weighted) == "100.00"
    assert settings.budgets.maximum_research == 5
    assert settings.podcast.minimum_seconds == 600
    assert settings.podcast.maximum_seconds == 1200
    assert settings.cadence.timezone == "Europe/Rome"
    assert settings.profiles["x"].provider == "xai-oauth"


def test_invalid_duration_configuration_is_rejected(repo: Path) -> None:
    config = repo / "config.ini"
    config.write_text(config.read_text().replace("minimum_duration_seconds = 600", "minimum_duration_seconds = 599"))
    with pytest.raises(ConfigurationError, match="600-1200"):
        load_settings(repo)


def test_url_identity_removes_tracking_but_preserves_identity_query() -> None:
    first = canonical_url("HTTPS://Example.COM:443/a/?utm_source=x&part=2#fragment")
    second = canonical_url("https://example.com/a?part=2")
    assert first == second == "https://example.com/a?part=2"
    assert source_identity(first) == source_identity(second)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/secret",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/",
        "http://localhost/admin",
        "file:///etc/passwd",
        "https://" + "user:password" + "@example.com/",
    ],
)
def test_private_or_credential_urls_are_rejected(url: str) -> None:
    with pytest.raises(ContractError):
        canonical_url(url)


def test_signed_media_url_is_not_retained() -> None:
    result, status = safe_media_asset_url(
        "https://cdn.example.com/video.mp4?X-Amz-Credential=secret&X-Amz-Signature=abc"
    )
    assert result is None
    assert status == "omitted_signed"


def test_stable_entity_identity_survives_display_name_change() -> None:
    assert entity_identity("robot_version", "maker:unit-42") == entity_identity("robot_version", "MAKER:UNIT-42")


@given(st.text(alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd")), min_size=1, max_size=50))
def test_source_identity_is_deterministic(basis: str) -> None:
    url = f"https://example.com/{basis.encode().hex()}"
    assert source_identity(url) == source_identity(url)


def test_migration_version_one_is_idempotent() -> None:
    record = {"schema_version": 1, "record_type": "claim", "id": "claim_" + "a" * 20}
    migrated = migrate_record(record)
    assert migrated == record
    assert migrated is not record


def test_migration_rejects_future_and_downgrade() -> None:
    with pytest.raises(ContractError, match="not implemented"):
        migrate_record({"schema_version": 1, "record_type": "claim"}, target_version=2)
    with pytest.raises(ContractError, match="downgrades"):
        migrate_record({"schema_version": 2, "record_type": "claim"}, target_version=1)
