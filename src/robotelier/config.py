"""Strict repository configuration with typed, unit-bearing values."""

from __future__ import annotations

import configparser
import os
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from robotelier.utils import ContractError


class ConfigurationError(ContractError):
    """Raised when configuration is unsafe or incomplete."""


@dataclass(frozen=True, slots=True)
class Paths:
    data_dir: Path
    wiki_path: Path
    schemas_dir: Path
    skills_dir: Path
    published_dir: Path


@dataclass(frozen=True, slots=True)
class Budgets:
    maximum_operations: int
    maximum_known_usd: Decimal
    maximum_weighted: Decimal
    maximum_research: int
    unknown_cost_policy: str


@dataclass(frozen=True, slots=True)
class Operations:
    lease_minutes: int
    default_max_attempts: int


@dataclass(frozen=True, slots=True)
class Discovery:
    maximum_candidates: int
    maximum_new_subscriptions: int
    overlap_hours: int
    bootstrap_days: int
    page_limit: int


@dataclass(frozen=True, slots=True)
class Evidence:
    quotation_words: int
    maximum_page_bytes: int


@dataclass(frozen=True, slots=True)
class Ranking:
    policy_version: str
    weights: dict[str, Decimal]
    maximum_aging_bonus: Decimal
    maximum_diversity_bonus: Decimal
    maximum_weekly_urgency: Decimal
    maximum_repetition_penalty: Decimal
    maximum_hype_penalty: Decimal


@dataclass(frozen=True, slots=True)
class Cadence:
    timezone: str
    research_time: str
    soft_cutoff: str
    publication_time: str
    release_time: str
    recovery_time: str
    late_release_end: str
    weekly_days: int


@dataclass(frozen=True, slots=True)
class Podcast:
    tts_command: str
    voice: str
    edge_tts_version: str
    chunk_characters: int
    minimum_seconds: int
    maximum_seconds: int
    maximum_attempts: int
    timeout_seconds: int


@dataclass(frozen=True, slots=True)
class Telegram:
    destination_alias: str
    maximum_attempts: int
    timeout_seconds: int
    text_limit: int
    caption_limit: int
    audio_maximum_bytes: int


@dataclass(frozen=True, slots=True)
class HermesProfile:
    provider: str
    model: str
    maximum_turns: int
    timeout_seconds: int
    cost_weight: Decimal


@dataclass(frozen=True, slots=True)
class Settings:
    root: Path
    paths: Paths
    budgets: Budgets
    operations: Operations
    discovery: Discovery
    evidence: Evidence
    ranking: Ranking
    cadence: Cadence
    podcast: Podcast
    telegram: Telegram
    profiles: dict[str, HermesProfile]
    publication_enabled: bool
    publish_pages: bool
    send_telegram: bool
    native_wiki_version: str


def _positive(parser: configparser.ConfigParser, section: str, key: str) -> int:
    try:
        value = parser.getint(section, key)
    except (configparser.Error, ValueError) as exc:
        raise ConfigurationError(f"{section}.{key} must be an integer") from exc
    if value <= 0:
        raise ConfigurationError(f"{section}.{key} must be positive")
    return value


def _decimal(parser: configparser.ConfigParser, section: str, key: str) -> Decimal:
    try:
        value = Decimal(parser.get(section, key))
    except (configparser.Error, InvalidOperation) as exc:
        raise ConfigurationError(f"{section}.{key} must be a decimal") from exc
    if not value.is_finite() or value < 0:
        raise ConfigurationError(f"{section}.{key} must be finite and nonnegative")
    return value


def _clock(value: str, label: str) -> str:
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
        raise ConfigurationError(f"{label} must be HH:MM")
    return value


def _path(root: Path, raw: str, label: str) -> Path:
    candidate = root / raw
    resolved_parent = candidate.parent.resolve()
    try:
        resolved_parent.relative_to(root)
    except ValueError as exc:
        raise ConfigurationError(f"{label} escapes repository") from exc
    return candidate


def load_settings(root: Path, path: Path | None = None) -> Settings:
    root = root.resolve(strict=True)
    config_path = path or root / "config.ini"
    parser = configparser.ConfigParser(interpolation=None)
    if not parser.read(config_path, encoding="utf-8"):
        raise ConfigurationError(f"configuration not found: {config_path}")
    required = {
        "paths",
        "budgets",
        "operations",
        "discovery",
        "evidence",
        "ranking",
        "cadence",
        "podcast",
        "telegram",
        "publication",
        "hermes",
        "profile_scout",
        "profile_editorial",
        "profile_deep",
        "profile_x",
    }
    missing = sorted(required - set(parser.sections()))
    if missing:
        raise ConfigurationError(f"missing configuration sections: {missing}")
    path_values = {
        key: _path(
            root,
            os.environ.get("WIKI_PATH", parser.get("paths", key)) if key == "wiki_path" else parser.get("paths", key),
            "WIKI_PATH" if key == "wiki_path" else f"paths.{key}",
        )
        for key in ("data_dir", "wiki_path", "schemas_dir", "skills_dir", "published_dir")
    }
    expected_wiki = (root / "data" / "wiki").resolve()
    if path_values["wiki_path"].resolve() != expected_wiki:
        raise ConfigurationError(f"WIKI_PATH must resolve to {expected_wiki}")
    paths = Paths(**path_values)
    budgets = Budgets(
        _positive(parser, "budgets", "maximum_llm_operations_per_cycle"),
        _decimal(parser, "budgets", "maximum_known_metered_usd_per_cycle"),
        _decimal(parser, "budgets", "maximum_weighted_budget_per_cycle"),
        _positive(parser, "budgets", "maximum_substantive_research_per_cycle"),
        parser.get("budgets", "unknown_cost_policy"),
    )
    if budgets.unknown_cost_policy != "record_unknown":
        raise ConfigurationError("budgets.unknown_cost_policy must be record_unknown")
    operations = Operations(
        _positive(parser, "operations", "lease_minutes"),
        _positive(parser, "operations", "default_max_attempts"),
    )
    discovery = Discovery(
        *(
            _positive(parser, "discovery", key)
            for key in (
                "maximum_candidates_per_cycle",
                "maximum_new_subscriptions_per_week",
                "overlap_hours",
                "bootstrap_days",
                "page_limit",
            )
        )
    )
    evidence = Evidence(
        _positive(parser, "evidence", "quotation_words_per_origin"),
        _positive(parser, "evidence", "maximum_page_bytes"),
    )
    score_keys = (
        "relevance",
        "novelty",
        "significance",
        "timeliness",
        "evidence_readiness",
        "explanatory_value",
    )
    weights = {key: _decimal(parser, "ranking", f"{key}_weight") for key in score_keys}
    if sum(weights.values()) != Decimal("1.00"):
        raise ConfigurationError("ranking weights must sum exactly to 1.00")
    ranking = Ranking(
        parser.get("ranking", "policy_version"),
        weights,
        _decimal(parser, "ranking", "maximum_aging_bonus"),
        _decimal(parser, "ranking", "maximum_diversity_bonus"),
        _decimal(parser, "ranking", "maximum_weekly_urgency"),
        _decimal(parser, "ranking", "maximum_repetition_penalty"),
        _decimal(parser, "ranking", "maximum_hype_penalty"),
    )
    timezone = parser.get("cadence", "timezone")
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ConfigurationError(f"unknown cadence timezone: {timezone}") from exc
    cadence = Cadence(
        timezone,
        _clock(parser.get("cadence", "research_time"), "cadence.research_time"),
        _clock(parser.get("cadence", "research_soft_cutoff"), "cadence.research_soft_cutoff"),
        _clock(parser.get("cadence", "publication_time"), "cadence.publication_time"),
        _clock(parser.get("cadence", "release_time"), "cadence.release_time"),
        _clock(parser.get("cadence", "recovery_time"), "cadence.recovery_time"),
        _clock(parser.get("cadence", "late_release_end"), "cadence.late_release_end"),
        _positive(parser, "cadence", "weekly_days"),
    )
    podcast = Podcast(
        parser.get("podcast", "tts_command"),
        parser.get("podcast", "voice"),
        parser.get("podcast", "edge_tts_version"),
        _positive(parser, "podcast", "chunk_character_limit"),
        _positive(parser, "podcast", "minimum_duration_seconds"),
        _positive(parser, "podcast", "maximum_duration_seconds"),
        _positive(parser, "podcast", "maximum_render_attempts"),
        _positive(parser, "podcast", "operation_timeout_seconds"),
    )
    if podcast.minimum_seconds != 600 or podcast.maximum_seconds != 1200:
        raise ConfigurationError("podcast measured duration must be 600-1200 seconds")
    telegram = Telegram(
        parser.get("telegram", "destination_alias"),
        _positive(parser, "telegram", "maximum_attempts"),
        _positive(parser, "telegram", "timeout_seconds"),
        _positive(parser, "telegram", "text_message_limit"),
        _positive(parser, "telegram", "audio_caption_limit"),
        _positive(parser, "telegram", "audio_maximum_bytes"),
    )
    profiles: dict[str, HermesProfile] = {}
    for name in ("scout", "editorial", "deep", "x"):
        section = f"profile_{name}"
        profiles[name] = HermesProfile(
            parser.get(section, "provider"),
            parser.get(section, "model"),
            _positive(parser, section, "maximum_turns"),
            _positive(parser, section, "timeout_seconds"),
            _decimal(parser, section, "cost_weight"),
        )
    if profiles["x"].provider != "openai-codex" or profiles["x"].model != "gpt-5.6-sol":
        raise ConfigurationError("profile_x must use openai-codex/gpt-5.6-sol")
    return Settings(
        root,
        paths,
        budgets,
        operations,
        discovery,
        evidence,
        ranking,
        cadence,
        podcast,
        telegram,
        profiles,
        parser.getboolean("publication", "enabled"),
        parser.getboolean("publication", "publish_pages"),
        parser.getboolean("publication", "send_telegram"),
        parser.get("hermes", "native_skill_version"),
    )
