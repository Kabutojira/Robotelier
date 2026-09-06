"""Stable JSON CLI for Robotelier's deterministic controller."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any

from robotelier import __version__
from robotelier.agent_runner import (
    configure_home,
    harness_finish,
    harness_start,
    preflight,
    run_hermes,
)
from robotelier.audit import record_command, snapshot
from robotelier.cadence import activate as cadence_activate
from robotelier.cadence import status as cadence_status
from robotelier.config import load_settings
from robotelier.credentials import (
    bootstrap_envelope,
    restore_envelope,
    seal_envelope,
    verify_envelope,
)
from robotelier.daily import finalize as daily_finalize
from robotelier.daily import prepare as daily_prepare
from robotelier.discovery import scan_adapters
from robotelier.editorial import propose, ranked_snapshot, review, select
from robotelier.identity import canonical_url, entity_identity, source_identity
from robotelier.integrity import validate_integrity
from robotelier.knowledge import build_wiki, lint_wiki
from robotelier.media import register_media, retained_media_errors
from robotelier.models import validate_schemas
from robotelier.operations import (
    claim,
    enqueue,
    finish,
    validate_queue,
)
from robotelier.operations import (
    prepare as queue_prepare,
)
from robotelier.podcast import (
    freeze,
    latest_episode,
    load_bundle,
    prepare_selected_episode,
    render_temporary,
    save_script_draft,
    seal_script,
    validate_segments,
)
from robotelier.provenance import (
    reference_errors,
    register_revision,
    trace,
    validate_source_hashes,
)
from robotelier.publication import (
    commit_transcript,
    deliver_episode_publication,
    prepare_episode_publication,
    reserve,
)
from robotelier.publication import status as publication_status
from robotelier.recovery import inspect as recovery_inspect
from robotelier.recovery import resume as recovery_resume
from robotelier.reports import (
    daily_summary_status,
    prepare_daily_summary,
    require_daily_summary_acknowledged,
)
from robotelier.sources import (
    Adapter,
    FeedAdapter,
    FixtureAdapter,
    HttpFeedAdapter,
    MetadataAdapter,
    WebPageAdapter,
)
from robotelier.subscriptions import add_subscription, validate_registry
from robotelier.telegram import deliver_audio, deliver_daily_summary, deliver_text, reconcile
from robotelier.utils import (
    ContractError,
    content_hash,
    read_json,
    repository_root,
    stable_id,
)
from robotelier.x_research import normalize_x_response, save_probe


def _request(args: argparse.Namespace) -> dict[str, Any]:
    return read_json(Path(args.request))


def _print(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, default=str))


@contextmanager
def _credential_identity(identity_file: str | None) -> Iterator[Path]:
    """Resolve an explicit identity or materialize OPENAI_OAUTH_SECRET privately."""

    if identity_file:
        yield Path(identity_file)
        return
    secret = os.environ.get("OPENAI_OAUTH_SECRET", "").strip()
    if not secret:
        raise ContractError("OPENAI_OAUTH_SECRET or --identity-file is required")
    descriptor, raw_path = tempfile.mkstemp(prefix="robotelier-oauth-", suffix=".agekey")
    temporary = Path(raw_path)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(secret)
            stream.write("\n")
        temporary.chmod(0o600)
        yield temporary
    finally:
        temporary.unlink(missing_ok=True)


def _record_request(root: Path, request: dict[str, Any], record_type: str) -> dict[str, Any]:
    return register_revision(
        root,
        {
            "record_type": record_type,
            "id": request["id"],
            "originating_operation_id": request["originating_operation_id"],
            "body": request["body"],
            "supersedes": request.get("supersedes"),
            "created_at": request.get("created_at"),
        },
    )


def _source_register(root: Path, request: dict[str, Any]) -> dict[str, Any]:
    body = dict(request["body"])
    body["canonical_url"] = canonical_url(body["canonical_url"])
    discovered_url = body.get("discovered_url", body["canonical_url"])
    if not isinstance(discovered_url, str):
        raise ContractError("source discovered_url must be a string")
    body["discovered_url"] = canonical_url(discovered_url, remove_tracking=False)
    identity = request.get("id") or source_identity(
        body["canonical_url"],
        platform=body.get("platform"),
        external_id=body.get("stable_external_id"),
    )
    body.setdefault("publisher", None)
    body.setdefault("author", None)
    body.setdefault("original_title", "")
    body.setdefault("language", None)
    body.setdefault("platform", None)
    body.setdefault("stable_external_id", None)
    body.setdefault("source_kind", "web_page")
    body.setdefault(
        "origin_group_id",
        stable_id("origin", body.get("original_source_url") or body["canonical_url"]),
    )
    body.setdefault("original_source_url", None)
    return register_revision(
        root,
        {
            "record_type": "source",
            "id": identity,
            "originating_operation_id": request["originating_operation_id"],
            "body": body,
            "supersedes": request.get("supersedes"),
            "created_at": request.get("created_at"),
        },
    )


def _source_observe(root: Path, request: dict[str, Any]) -> dict[str, Any]:
    body = dict(request["body"])
    basis = f"{body['source_id']}:{body['retrieved_at']}:{body.get('content_hash')}:{body.get('hash_scope')}"
    identity = request.get("id") or stable_id("source_revision", basis)
    body.setdefault("published_at", None)
    body.setdefault("event_at", None)
    body.setdefault("modified_at", None)
    body.setdefault("date_precision", "unknown")
    body.setdefault("retrieval_method", "unknown")
    body.setdefault("effective_url", None)
    body.setdefault("content_hash", None)
    body.setdefault("hash_scope", "none")
    body.setdefault("retained_excerpt", None)
    body.setdefault("english_summary", None)
    body.setdefault("observation_id", identity)
    return register_revision(
        root,
        {
            "record_type": "source_revision",
            "id": identity,
            "originating_operation_id": request["originating_operation_id"],
            "body": body,
            "supersedes": request.get("supersedes"),
            "created_at": request.get("created_at"),
        },
    )


def _evidence_record(root: Path, request: dict[str, Any]) -> dict[str, Any]:
    body = request["body"]
    identity = request.get("id") or stable_id(
        "evidence",
        f"{body['source_revision_id']}:{content_hash(body['locator'])}:{content_hash(body['support'])}",
    )
    return _record_request(root, {**request, "id": identity}, "evidence")


def _claim_record(root: Path, request: dict[str, Any]) -> dict[str, Any]:
    body = request["body"]
    identity = request.get("id") or stable_id("claim", f"{body['subject_id']}:{body['predicate']}")
    return _record_request(root, {**request, "id": identity}, "claim")


def _entity_upsert(root: Path, request: dict[str, Any]) -> dict[str, Any]:
    body = dict(request["body"])
    basis = body.get("verified_identity_basis") or next(iter(body.get("external_ids", {}).values()), None)
    if not basis:
        raise ContractError("entity upsert requires a verified identity basis or external ID")
    identity = request.get("id") or entity_identity(body["entity_type"], str(basis))
    body.pop("verified_identity_basis", None)
    body.setdefault("aliases", [])
    body.setdefault("canonical_urls", [])
    body["canonical_urls"] = [canonical_url(value) for value in body["canonical_urls"]]
    body.setdefault("external_ids", {})
    body.setdefault("parent_ids", [])
    body.setdefault("lifecycle", "unknown")
    body.setdefault("planned_availability", None)
    body.setdefault("actual_availability", None)
    body.setdefault("review_at", None)
    body.setdefault(
        "wiki_path",
        f"data/wiki/{'robots' if body['entity_type'].startswith('robot') else 'companies'}/{identity}.md",
    )
    return _record_request(root, {**request, "id": identity, "body": body}, "entity")


def _entity_merge(root: Path, request: dict[str, Any]) -> dict[str, Any]:
    source_id, target_id = request["source_id"], request["target_id"]
    if source_id == target_id:
        raise ContractError("cannot merge an entity into itself")
    redirects = root / "data" / "records" / "entities" / "redirects.json"
    current = json.loads(redirects.read_text(encoding="utf-8")) if redirects.exists() else {}
    current[source_id] = {
        "target_id": target_id,
        "reason": request["reason"],
        "originating_operation_id": request["originating_operation_id"],
    }
    from robotelier.storage import atomic_write_json

    atomic_write_json(redirects, current, allowed_root=root)
    return {"status": "merged", "source_id": source_id, "target_id": target_id}


def _development_upsert(root: Path, request: dict[str, Any]) -> dict[str, Any]:
    body = request["body"]
    identity = request.get("id") or stable_id(
        "development",
        f"{body.get('event_at')}:{'|'.join(sorted(body.get('origin_group_ids', [])))}",
    )
    return _record_request(root, {**request, "id": identity}, "development")


def _discovery(root: Path, request: dict[str, Any]) -> dict[str, Any]:
    adapters: list[Adapter] = []
    for value in request.get("adapters", []):
        if value["type"] == "fixture":
            adapters.append(FixtureAdapter(value["adapter_id"], root / value["path"]))
        elif value["type"] == "feed_payload":
            adapters.append(FeedAdapter(value["adapter_id"], value["payload"], publisher=value.get("publisher")))
        elif value["type"] == "feed_url":
            adapters.append(
                HttpFeedAdapter(
                    value["adapter_id"],
                    value["url"],
                    maximum_bytes=load_settings(root).evidence.maximum_page_bytes,
                    publisher=value.get("publisher"),
                )
            )
        elif value["type"] == "web_page":
            adapters.append(
                WebPageAdapter(
                    value["adapter_id"],
                    value["url"],
                    maximum_bytes=load_settings(root).evidence.maximum_page_bytes,
                    publisher=value.get("publisher"),
                    language=value.get("language"),
                )
            )
        elif value["type"] == "metadata":
            adapters.append(MetadataAdapter(value["adapter_id"], value["items"]))
        else:
            raise ContractError(f"unsupported adapter type: {value['type']}")
    return scan_adapters(
        root,
        adapters,
        operation_id=request["originating_operation_id"],
        classifications=request.get("classifications"),
    )


def _doctor(root: Path, live: bool) -> dict[str, Any]:
    settings = load_settings(root)
    checks: dict[str, Any] = {
        "configuration": "passed",
        "python": sys.version.split()[0],
        "ffprobe": shutil.which("ffprobe"),
        "edge_tts": shutil.which("edge-tts"),
        "native_wiki_required": settings.native_wiki_version,
        "live": live,
        "production_enabled": settings.publication_enabled,
    }
    blockers: list[str] = []
    if not checks["ffprobe"]:
        blockers.append("ffprobe_unavailable")
    if live:
        for profile, variable in (
            ("editorial", "ROBOTELIER_OPENAI_HERMES_HOME"),
            ("x", "ROBOTELIER_GROK_HERMES_HOME"),
        ):
            raw = os.environ.get(variable)
            if not raw:
                blockers.append(f"{variable.lower()}_missing")
                continue
            try:
                checks[f"profile_{profile}"] = preflight(root, Path(raw), profile=profile, live=True)
            except ContractError as exc:
                blockers.append(f"{profile}_profile:{exc}")
        blockers.append("x_evidence_probe_not_run_by_doctor")
        blockers.append("telegram_delivery_not_run_by_doctor")
    checks["status"] = "blocked" if blockers else "passed"
    checks["blockers"] = blockers
    return checks


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="robotelier")
    parser.add_argument("--version", action="version", version=__version__)
    groups = parser.add_subparsers(dest="group", required=True)

    def actions(name: str, choices: list[str]) -> dict[str, argparse.ArgumentParser]:
        parent = groups.add_parser(name)
        sub = parent.add_subparsers(dest="action", required=True)
        return {choice: sub.add_parser(choice) for choice in choices}

    actions("config", ["validate"])
    schema = actions("schema", ["validate"])
    schema["validate"].add_argument("--strict", action="store_true")
    credential = actions("credential", ["bootstrap", "restore", "seal", "verify"])
    for name in ("restore", "seal"):
        item = credential[name]
        item.add_argument("--profile", required=True)
        item.add_argument("--hermes-home", required=True)
    for item in credential.values():
        item.add_argument("--identity-file")
    credential["bootstrap"].add_argument("--auth-file", required=True)
    credential["verify"].add_argument("--auth-file", required=True)
    doctor = groups.add_parser("doctor")
    mode = doctor.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true")
    mode.add_argument("--live", action="store_true")
    daily = actions("daily", ["prepare", "finalize"])
    daily["prepare"].add_argument("--run-id", required=True)
    daily["prepare"].add_argument("--intended-slot", required=True)
    daily["prepare"].add_argument("--trigger", default="manual")
    daily["prepare"].add_argument("--dry-run", action="store_true")
    daily["prepare"].add_argument("--maximum-operations", type=int, default=20)
    daily["prepare"].add_argument("--publish-pages", action=argparse.BooleanOptionalAction, default=False)
    daily["prepare"].add_argument("--send-telegram", action=argparse.BooleanOptionalAction, default=False)
    daily["prepare"].add_argument("--resume-id")
    daily["finalize"].add_argument("--run-id", required=True)
    report = actions("report", ["prepare-summary", "deliver-summary", "status", "verify-summary"])
    report["prepare-summary"].add_argument("--local-date", required=True)
    report["prepare-summary"].add_argument("--source-commit", required=True)
    report["prepare-summary"].add_argument("--report-url", required=True)
    report["prepare-summary"].add_argument("--delivery-run-id", required=True)
    report["deliver-summary"].add_argument("--delivery-run-id", required=True)
    for name in ("deliver-summary", "status", "verify-summary"):
        report[name].add_argument("--local-date", required=True)

    source = actions("source", ["register", "observe", "validate"])
    source["register"].add_argument("--request", required=True)
    source["observe"].add_argument("--request", required=True)
    subscription = actions("subscription", ["add", "list", "validate"])
    subscription["add"].add_argument("--request", required=True)
    media = actions("media", ["register", "validate"])
    media["register"].add_argument("--request", required=True)
    evidence = actions("evidence", ["record"])
    evidence["record"].add_argument("--request", required=True)
    development = actions("development", ["upsert"])
    development["upsert"].add_argument("--request", required=True)
    editorial = actions("editorial", ["propose", "review", "rank", "select", "validate"])
    editorial["propose"].add_argument("--request", required=True)
    editorial["review"].add_argument("--request", required=True)
    editorial["rank"].add_argument("--reference-time", required=True)
    editorial["select"].add_argument("--reference-time", required=True)
    editorial["select"].add_argument("--local-date", required=True)

    discovery = actions("discovery", ["scan", "backfill"])
    for item in discovery.values():
        item.add_argument("--request", required=True)
        item.add_argument("--dry-run", action="store_true")

    claim_cmd = actions("claim", ["record", "supersede", "trace"])
    claim_cmd["record"].add_argument("--request", required=True)
    claim_cmd["supersede"].add_argument("--request", required=True)
    claim_cmd["trace"].add_argument("--claim-id", required=True)
    entity = actions("entity", ["upsert", "merge"])
    entity["upsert"].add_argument("--request", required=True)
    entity["merge"].add_argument("--request", required=True)

    queue = actions("queue", ["enqueue", "prepare", "claim", "finish", "validate"])
    queue["enqueue"].add_argument("--request", required=True)
    queue["prepare"].add_argument("--cycle-id")
    queue["claim"].add_argument("--run-id", required=True)
    queue["claim"].add_argument("--cycle-id", required=True)
    queue["finish"].add_argument("--request", required=True)

    agent = actions("agent", ["configure", "preflight", "run", "harness"])
    for key in ("configure", "preflight", "run"):
        agent[key].add_argument("--profile", default="editorial")
        agent[key].add_argument("--hermes-home", required=True)
    agent["configure"].add_argument("--replace-unmanaged", action="store_true")
    agent["preflight"].add_argument("--live", action="store_true")
    agent["run"].add_argument("--run-id", required=True)
    agent["run"].add_argument("--cycle-id", required=True)
    agent["run"].add_argument("--maximum-operations", type=int, default=20)
    harness_sub = agent["harness"].add_subparsers(dest="harness_action", required=True)
    harness = {name: harness_sub.add_parser(name) for name in ("start", "finish")}
    for item in harness.values():
        item.add_argument("--run-id", required=True)
        item.add_argument("--operation-id", required=True)
        item.add_argument("--cycle-id", required=True)

    cadence = actions("cadence", ["status", "plan", "activate"])
    for item in cadence.values():
        item.add_argument("--at")

    podcast = actions(
        "podcast",
        [
            "freeze",
            "validate-context",
            "validate-script",
            "render-draft",
            "seal-render",
            "validate-render",
            "prepare",
        ],
    )
    for name in ("freeze", "validate-context", "validate-script", "seal-render", "validate-render"):
        podcast[name].add_argument("--request", required=True)
    podcast["render-draft"].add_argument("--episode-id", required=True)
    podcast["render-draft"].add_argument("--render-id", required=True)
    podcast["render-draft"].add_argument("--dry-run", action="store_true")
    podcast["prepare"].add_argument("--local-date", required=True)

    publication = actions("publication", ["reserve", "commit", "status", "prepare", "deliver"])
    publication["reserve"].add_argument("--episode-id", required=True)
    publication["reserve"].add_argument("--local-date", required=True)
    publication["commit"].add_argument("--episode-id", required=True)
    publication["commit"].add_argument("--local-date", required=True)
    publication["commit"].add_argument("--source-commit", required=True)
    publication["status"].add_argument("--local-date")
    publication["prepare"].add_argument("--local-date", required=True)
    publication["deliver"].add_argument("--local-date", required=True)

    telegram = actions("telegram", ["deliver-text", "deliver-audio", "reconcile"])
    telegram["deliver-text"].add_argument("--request", required=True)
    telegram["deliver-audio"].add_argument("--request", required=True)
    telegram["reconcile"].add_argument("--request", required=True)

    wiki = actions("wiki", ["validate", "maintain", "build"])
    wiki["maintain"].add_argument("--dry-run", action="store_true")
    wiki["maintain"].add_argument("--hermes-home")
    wiki["maintain"].add_argument("--run-id")

    integrity = actions("integrity", ["check"])
    integrity["check"].add_argument("--strict", action="store_true")
    recovery = actions("recovery", ["inspect", "resume"])
    recovery["inspect"].add_argument("--slot", required=True)
    recovery["resume"].add_argument("--request", required=True)
    xprobe = actions("x", ["normalize-probe"])
    xprobe["normalize-probe"].add_argument("--request", required=True)
    return parser


def _dispatch(root: Path, args: argparse.Namespace) -> object:
    key = (args.group, getattr(args, "action", None))
    if key == ("config", "validate"):
        settings = load_settings(root)
        return {
            "status": "passed",
            "timezone": settings.cadence.timezone,
            "profiles": sorted(settings.profiles),
        }
    if key == ("schema", "validate"):
        errors = validate_schemas(root)
        if args.strict:
            errors.extend(validate_integrity(root, strict=True))
        return {
            "status": "passed" if not errors else "failed",
            "schemas": len(list((root / "schemas").glob("*.schema.json"))),
            "errors": sorted(set(errors)),
        }
    if key == ("credential", "bootstrap"):
        with _credential_identity(args.identity_file) as identity:
            return bootstrap_envelope(root, auth_file=Path(args.auth_file), identity=identity)
    if key == ("credential", "restore"):
        with _credential_identity(args.identity_file) as identity:
            return restore_envelope(
                root,
                profile=args.profile,
                home=Path(args.hermes_home),
                identity=identity,
            )
    if key == ("credential", "seal"):
        with _credential_identity(args.identity_file) as identity:
            return seal_envelope(
                root,
                profile=args.profile,
                home=Path(args.hermes_home),
                identity=identity,
            )
    if key == ("credential", "verify"):
        with _credential_identity(args.identity_file) as identity:
            return verify_envelope(root, auth_file=Path(args.auth_file), identity=identity)
    if args.group == "doctor":
        return _doctor(root, args.live)
    if key == ("daily", "prepare"):
        return daily_prepare(
            root,
            run_id=args.run_id,
            intended_local_date=args.intended_slot,
            trigger=args.trigger,
            dry_run=args.dry_run,
            maximum_operations=args.maximum_operations,
            publish_pages=args.publish_pages,
            send_telegram=args.send_telegram,
            resume_id=args.resume_id,
        )
    if key == ("daily", "finalize"):
        return daily_finalize(root, run_id=args.run_id)
    if key == ("report", "prepare-summary"):
        return prepare_daily_summary(
            root,
            local_date=args.local_date,
            source_commit=args.source_commit,
            report_url=args.report_url,
            delivery_run_id=args.delivery_run_id,
        )
    if key == ("report", "deliver-summary"):
        return deliver_daily_summary(
            root,
            local_date=args.local_date,
            delivery_run_id=args.delivery_run_id,
            token=os.environ["TELEGRAM_BOT_TOKEN"],
            chat_id=os.environ["TELEGRAM_CHAT_ID"],
        )
    if key == ("report", "status"):
        return daily_summary_status(root, local_date=args.local_date)
    if key == ("report", "verify-summary"):
        return require_daily_summary_acknowledged(root, local_date=args.local_date)
    if key == ("source", "register"):
        return _source_register(root, _request(args))
    if key == ("source", "observe"):
        return _source_observe(root, _request(args))
    if key == ("source", "validate"):
        errors = validate_source_hashes(root)
        return {"passed": not errors, "errors": errors}
    if key == ("subscription", "add"):
        return add_subscription(root, _request(args))
    if key == ("subscription", "list"):
        return json.loads((root / "data" / "subscriptions" / "registry.json").read_text(encoding="utf-8"))
    if key == ("subscription", "validate"):
        errors = validate_registry(root)
        return {"passed": not errors, "errors": errors}
    if key == ("media", "register"):
        return register_media(root, _request(args))
    if key == ("media", "validate"):
        errors = retained_media_errors(root)
        return {"passed": not errors, "errors": errors}
    if key == ("evidence", "record"):
        return _evidence_record(root, _request(args))
    if key == ("claim", "record"):
        return _claim_record(root, _request(args))
    if key == ("claim", "supersede"):
        request = _request(args)
        if not request.get("supersedes"):
            raise ContractError("claim supersede request requires supersedes revision")
        return _claim_record(root, request)
    if key == ("claim", "trace"):
        return trace(root, args.claim_id)
    if key == ("entity", "upsert"):
        return _entity_upsert(root, _request(args))
    if key == ("entity", "merge"):
        return _entity_merge(root, _request(args))
    if key == ("development", "upsert"):
        return _development_upsert(root, _request(args))
    if args.group == "discovery":
        if args.dry_run:
            return {"status": "dry_run", "network": False, "mutations": False}
        return _discovery(root, _request(args))
    if key == ("queue", "enqueue"):
        return enqueue(root, _request(args))
    if key == ("queue", "prepare"):
        return queue_prepare(root)
    if key == ("queue", "claim"):
        return claim(root, run_id=args.run_id, cycle_id=args.cycle_id) or {"status": "empty"}
    if key == ("queue", "finish"):
        request = _request(args)
        return finish(
            root,
            operation_id=request["operation_id"],
            lease_token=request["lease_token"],
            outcome=request["outcome"],
            reason_code=request.get("reason_code"),
            result=request.get("result", {}),
            cycle_id=request.get("cycle_id"),
            known_metered_usd=Decimal(str(request["known_metered_usd"]))
            if request.get("known_metered_usd") is not None
            else None,
            supplied_usage=request.get("supplied_usage"),
        )
    if key == ("queue", "validate"):
        errors = validate_queue(root)
        return {"passed": not errors, "errors": errors}
    if key == ("agent", "configure"):
        return {
            "config_path": str(
                configure_home(
                    root,
                    Path(args.hermes_home),
                    profile=args.profile,
                    replace_unmanaged=args.replace_unmanaged,
                )
            )
        }
    if key == ("agent", "preflight"):
        return preflight(root, Path(args.hermes_home), profile=args.profile, live=args.live)
    if key == ("agent", "run"):
        return {
            "operations": run_hermes(
                root,
                home=Path(args.hermes_home),
                profile=args.profile,
                run_id=args.run_id,
                cycle_id=args.cycle_id,
                maximum_operations=args.maximum_operations,
                environment=dict(os.environ),
            )
        }
    if key == ("agent", "harness") and args.harness_action == "start":
        return harness_start(root, run_id=args.run_id, operation_id=args.operation_id, cycle_id=args.cycle_id)
    if key == ("agent", "harness") and args.harness_action == "finish":
        return harness_finish(root, run_id=args.run_id, operation_id=args.operation_id, cycle_id=args.cycle_id)
    if key == ("editorial", "propose"):
        return propose(root, _request(args))
    if key == ("editorial", "review"):
        return review(root, _request(args))
    if key == ("editorial", "rank"):
        return ranked_snapshot(root, reference_time=args.reference_time)
    if key == ("editorial", "select"):
        return select(root, local_date=args.local_date, reference_time=args.reference_time)
    if key == ("editorial", "validate"):
        errors = reference_errors(root)
        return {"passed": not errors, "errors": errors}
    if args.group == "cadence":
        if args.at:
            from datetime import datetime

            instant = datetime.fromisoformat(args.at.replace("Z", "+00:00"))
        else:
            instant = None
        if args.action == "activate":
            return cadence_activate(root, now=instant)
        value = cadence_status(root, now=instant)
        if args.action == "plan":
            value["actions"] = {
                "healthy": ["daily_research"],
                "prepare_weekly_candidate": ["reserve_weekly_candidate"],
                "evidence_priority": ["prioritize_named_evidence_gaps"],
                "outline_due": ["complete_reviewed_dense_outline"],
                "cadence_breach": ["record_breach", "alert_operator", "continue_evidence_work"],
            }[value["phase"]]
        return value
    if key == ("podcast", "freeze"):
        return freeze(root, _request(args))
    if key == ("podcast", "prepare"):
        return prepare_selected_episode(root, local_date=args.local_date)
    if key == ("podcast", "validate-context"):
        request = _request(args)
        bundle = load_bundle(root, request["episode_id"], request["bundle_hash"])
        return {"passed": True, "bundle_hash": content_hash(bundle)}
    if key == ("podcast", "validate-script"):
        request = _request(args)
        if request.get("seal"):
            return seal_script(root, request)
        if request.get("save_draft"):
            return save_script_draft(root, request)
        bundle = load_bundle(root, request["episode_id"], request["bundle_hash"])
        errors = validate_segments(bundle, request["segments"])
        return {"passed": not errors, "errors": errors}
    if key == ("podcast", "render-draft"):
        if args.dry_run:
            episode = latest_episode(root, args.episode_id)
            return {
                "status": "dry_run",
                "transcript_hash": episode["transcript_hash"],
                "rendered": False,
            }
        return render_temporary(root, episode_id=args.episode_id, render_id=args.render_id)
    if key == ("podcast", "seal-render"):
        request = _request(args)
        forbidden = [name for name in request if "path" in name.lower() or "url" in name.lower()]
        if forbidden:
            raise ContractError(f"render metadata cannot retain media locations: {forbidden}")
        episode = latest_episode(root, request["episode_id"])
        if request["transcript_hash"] != episode["transcript_hash"]:
            raise ContractError("render transcript hash mismatch")
        if not 600 <= float(request["duration_seconds"]) <= 1200:
            raise ContractError("render duration outside 600-1200 seconds")
        from robotelier.storage import atomic_write_json

        path = (
            root / "data" / "records" / "episodes" / episode["id"] / "artifacts" / f"render-{request['render_id']}.json"
        )
        atomic_write_json(path, request, allowed_root=root)
        return {"status": "sealed", "render_id": request["render_id"]}
    if key == ("podcast", "validate-render"):
        request = _request(args)
        episode = latest_episode(root, request["episode_id"])
        path = (
            root / "data" / "records" / "episodes" / episode["id"] / "artifacts" / f"render-{request['render_id']}.json"
        )
        value = json.loads(path.read_text(encoding="utf-8"))
        errors = []
        if value.get("transcript_hash") != episode["transcript_hash"]:
            errors.append("transcript_hash_mismatch")
        if not 600 <= float(value.get("duration_seconds", 0)) <= 1200:
            errors.append("duration_out_of_range")
        return {"passed": not errors, "errors": errors}
    if key == ("publication", "reserve"):
        return reserve(root, episode_id=args.episode_id, local_date=args.local_date)
    if key == ("publication", "commit"):
        return commit_transcript(
            root,
            episode_id=args.episode_id,
            local_date=args.local_date,
            source_commit=args.source_commit,
        )
    if key == ("publication", "status"):
        return publication_status(root, args.local_date)
    if key == ("publication", "prepare"):
        return prepare_episode_publication(root, local_date=args.local_date)
    if key == ("publication", "deliver"):
        return deliver_episode_publication(
            root,
            local_date=args.local_date,
            token=os.environ["TELEGRAM_BOT_TOKEN"],
            chat_id=os.environ["TELEGRAM_CHAT_ID"],
        )
    if key == ("telegram", "deliver-text"):
        request = _request(args)
        return deliver_text(
            root,
            local_date=request["local_date"],
            text=request["text"],
            token=os.environ["TELEGRAM_BOT_TOKEN"],
            chat_id=os.environ["TELEGRAM_CHAT_ID"],
        )
    if key == ("telegram", "deliver-audio"):
        request = _request(args)
        audio_path = Path(request["audio_path"])
        try:
            audio_path.resolve().relative_to(root.resolve())
        except ValueError:
            pass
        else:
            raise ContractError("temporary audio path must be outside repository")
        try:
            return deliver_audio(
                root,
                local_date=request["local_date"],
                audio_path=audio_path,
                metadata=request["metadata"],
                token=os.environ["TELEGRAM_BOT_TOKEN"],
                chat_id=os.environ["TELEGRAM_CHAT_ID"],
                caption=request.get("caption", "Robotelier"),
            )
        finally:
            audio_path.unlink(missing_ok=True)
    if key == ("telegram", "reconcile"):
        return reconcile(root, _request(args))
    if key == ("wiki", "validate"):
        errors = lint_wiki(root)
        return {"passed": not errors, "errors": errors}
    if key == ("wiki", "build"):
        errors = lint_wiki(root)
        if errors:
            raise ContractError("wiki validation failed: " + "; ".join(errors))
        return build_wiki(root)
    if key == ("wiki", "maintain"):
        if args.dry_run:
            return {
                "status": "dry_run",
                "toolsets": ["file", "terminal"],
                "web": False,
                "mutations": False,
            }
        raise ContractError("live native maintenance requires the scheduled audited harness")
    if key == ("integrity", "check"):
        errors = validate_integrity(root, strict=args.strict)
        if args.strict and errors:
            raise ContractError("strict integrity check failed: " + "; ".join(errors))
        return {"passed": not errors, "errors": errors}
    if key == ("recovery", "inspect"):
        return recovery_inspect(root, local_date=args.slot)
    if key == ("recovery", "resume"):
        return recovery_resume(root, _request(args))
    if key == ("x", "normalize-probe"):
        request = _request(args)
        normalized = normalize_x_response(
            request["response"],
            query=request["query"],
            account_filter=request.get("account_filter"),
            date_from=request.get("date_from"),
            date_to=request.get("date_to"),
        )
        if request.get("run_id"):
            save_probe(root, request["run_id"], normalized)
        return normalized
    raise ContractError(f"unimplemented command: {key}")


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = _parser()
    args = parser.parse_args(arguments)
    try:
        root = repository_root()
    except ContractError as exc:
        _print({"status": "error", "error": str(exc), "error_type": type(exc).__name__})
        return 2
    audit_run = os.environ.get("ROBOTELIER_AUDIT_RUN_ID")
    audit_operation = os.environ.get("ROBOTELIER_AUDIT_OPERATION_ID")
    before = snapshot(root) if audit_run and audit_operation else None
    exit_code = 0
    try:
        result = _dispatch(root, args)
        _print(result)
    except (ContractError, KeyError, ValueError, OSError) as exc:
        exit_code = 2
        _print({"status": "error", "error": str(exc), "error_type": type(exc).__name__})
    finally:
        if before is not None and audit_run and audit_operation:
            try:
                record_command(
                    root,
                    run_id=audit_run,
                    operation_id=audit_operation,
                    argv=arguments,
                    exit_code=exit_code,
                    before=before,
                    after=snapshot(root),
                )
            except Exception as exc:
                _print({"status": "audit_error", "error": str(exc)})
                exit_code = 2
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
