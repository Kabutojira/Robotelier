"""Telegram text/audio outbox with ambiguous-side-effect safety."""

from __future__ import annotations

import json
import mimetypes
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

from robotelier.config import load_settings
from robotelier.publication import outbox_path, update_channel
from robotelier.utils import ContractError, content_hash, format_timestamp, utc_now


class TelegramError(ContractError):
    pass


def split_text(text: str, limit: int) -> list[str]:
    if limit < 1:
        raise TelegramError("message limit must be positive")
    remaining = text.strip()
    chunks: list[str] = []
    while len(remaining) > limit:
        boundary = remaining.rfind("\n\n", 0, limit + 1)
        if boundary < limit // 2:
            boundary = remaining.rfind(" ", 0, limit + 1)
        if boundary < 1:
            boundary = limit
        chunks.append(remaining[:boundary].strip())
        remaining = remaining[boundary:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def _post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        value = json.loads(response.read())
    if not isinstance(value, dict):
        raise TelegramError("Telegram returned a non-object response")
    if not value.get("ok"):
        raise TelegramError("Telegram returned a known rejection")
    return value


def _post_audio(url: str, chat_id: str, path: Path, caption: str, timeout: int) -> dict[str, Any]:
    boundary = f"----robotelier{uuid.uuid4().hex}"
    content = path.read_bytes()
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'.encode(),
        f'--{boundary}\r\nContent-Disposition: form-data; name="caption"\r\n\r\n{caption}\r\n'.encode(),
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="audio"; filename="episode.mp3"\r\n'
            "Content-Type: audio/mpeg\r\n\r\n"
        ).encode()
        + content
        + b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    request = urllib.request.Request(
        url,
        data=b"".join(parts),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        value = json.loads(response.read())
    if not isinstance(value, dict):
        raise TelegramError("Telegram returned a non-object audio response")
    if not value.get("ok"):
        raise TelegramError("Telegram returned a known audio rejection")
    return value


def _message_id(response: dict[str, Any]) -> int:
    result = response.get("result")
    if not isinstance(result, dict):
        raise TelegramError("Telegram acknowledgment lacks message_id")
    message_id = result.get("message_id")
    if not isinstance(message_id, int):
        raise TelegramError("Telegram acknowledgment lacks message_id")
    return message_id


def _require_committed_transcript(root: Path, outbox: dict[str, Any], text: str | None = None) -> None:
    committed = outbox.get("transcript", {})
    if committed.get("state") != "committed" or not committed.get("transcript_hash"):
        raise TelegramError("committed transcript is required before delivery")
    if text is not None and content_hash(text) != committed["transcript_hash"]:
        raise TelegramError("Telegram text does not match the committed transcript")


def _commit_acknowledgment(
    root: Path,
    *,
    local_date: str,
    channel: str,
    state: dict[str, Any],
    intent: dict[str, Any],
) -> dict[str, Any]:
    try:
        update_channel(root, local_date=local_date, channel=channel, state=state)
    except OSError as exc:
        reconciliation = {
            **intent,
            "state": "reconciliation_required",
            "reason_code": "provider_acknowledged_receipt_commit_failed",
        }
        with suppress(OSError):
            update_channel(root, local_date=local_date, channel=channel, state=reconciliation)
        # The durable pre-send intent remains authoritative if even the
        # reconciliation receipt cannot be written; never retry it blindly.
        raise TelegramError("provider acknowledged delivery but receipt commit failed") from exc
    return state


def deliver_text(
    root: Path,
    *,
    local_date: str,
    text: str,
    token: str,
    chat_id: str,
    sender: Callable[[str, dict[str, Any], int], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    settings = load_settings(root).telegram
    path = outbox_path(root, local_date)
    outbox = json.loads(path.read_text(encoding="utf-8"))
    _require_committed_transcript(root, outbox, text)
    current = outbox["telegram_text"]
    if current.get("state") in {
        "intent_written",
        "acknowledged",
        "delivery_unknown",
        "reconciliation_required",
    }:
        raise TelegramError(f"text delivery cannot be retried from {current.get('state')}")
    attempt_count = int(current.get("attempt_count", 0)) + 1
    if attempt_count > settings.maximum_attempts:
        raise TelegramError("text delivery attempt ceiling reached")
    chunks = split_text(text, settings.text_limit)
    intent = {
        "state": "intent_written",
        "intent_at": format_timestamp(utc_now()),
        "message_ids": [],
        "chunk_count": len(chunks),
        "attempt_count": attempt_count,
    }
    update_channel(root, local_date=local_date, channel="telegram_text", state=intent)
    send = sender or _post_json
    ids: list[int] = []
    try:
        for chunk in chunks:
            response = send(
                f"https://api.telegram.org/bot{token}/sendMessage",
                {"chat_id": chat_id, "text": chunk},
                settings.timeout_seconds,
            )
            ids.append(_message_id(response))
    except (urllib.error.HTTPError, TelegramError) as exc:
        reason = f"telegram_http_{exc.code}" if isinstance(exc, urllib.error.HTTPError) else "telegram_rejected"
        state = {
            **intent,
            "state": "reconciliation_required" if ids else "failed",
            "reason_code": "partial_text_delivery" if ids else reason,
            "message_ids": ids,
        }
        update_channel(root, local_date=local_date, channel="telegram_text", state=state)
        return state
    except (TimeoutError, OSError, json.JSONDecodeError):
        state = {
            **intent,
            "state": "delivery_unknown",
            "reason_code": "response_lost",
            "message_ids": ids,
        }
        update_channel(root, local_date=local_date, channel="telegram_text", state=state)
        return state
    state = {
        **intent,
        "state": "acknowledged",
        "acknowledged_at": format_timestamp(utc_now()),
        "message_ids": ids,
    }
    return _commit_acknowledgment(
        root,
        local_date=local_date,
        channel="telegram_text",
        state=state,
        intent=intent,
    )


def deliver_audio(
    root: Path,
    *,
    local_date: str,
    audio_path: Path,
    metadata: dict[str, Any],
    token: str,
    chat_id: str,
    caption: str = "Robotelier",
    sender: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    settings = load_settings(root).telegram
    outbox = json.loads(outbox_path(root, local_date).read_text(encoding="utf-8"))
    _require_committed_transcript(root, outbox)
    current = outbox["telegram_audio"]
    if current.get("state") in {
        "intent_written",
        "acknowledged",
        "delivery_unknown",
        "reconciliation_required",
    }:
        raise TelegramError(f"audio delivery cannot be retried from {current.get('state')}")
    attempt_count = int(current.get("attempt_count", 0)) + 1
    if attempt_count > settings.maximum_attempts:
        raise TelegramError("audio delivery attempt ceiling reached")
    if not audio_path.is_file() or audio_path.is_symlink():
        raise TelegramError("audio must be a regular temporary file")
    if (
        audio_path.stat().st_size != metadata.get("audio_bytes")
        or audio_path.stat().st_size > settings.audio_maximum_bytes
    ):
        raise TelegramError("audio size is invalid")
    mime = metadata.get("mime_type") or mimetypes.guess_type(audio_path.name)[0]
    if mime not in {"audio/mpeg", "audio/mp3"}:
        raise TelegramError(f"unsupported Telegram audio MIME: {mime}")
    if len(caption) > settings.caption_limit:
        raise TelegramError("audio caption exceeds Telegram limit")
    if metadata.get("transcript_hash") != outbox["transcript"]["transcript_hash"]:
        raise TelegramError("audio render is not bound to the committed transcript")
    intent = {
        "state": "intent_written",
        "intent_at": format_timestamp(utc_now()),
        "message_id": None,
        "render_id": metadata["render_id"],
        "audio_sha256": metadata["audio_sha256"],
        "audio_bytes": metadata["audio_bytes"],
        "attempt_count": attempt_count,
    }
    update_channel(root, local_date=local_date, channel="telegram_audio", state=intent)
    send = sender or _post_audio
    try:
        response = send(
            f"https://api.telegram.org/bot{token}/sendAudio",
            chat_id,
            audio_path,
            caption,
            settings.timeout_seconds,
        )
        message_id = _message_id(response)
    except (urllib.error.HTTPError, TelegramError) as exc:
        reason = f"telegram_http_{exc.code}" if isinstance(exc, urllib.error.HTTPError) else "telegram_rejected"
        state = {**intent, "state": "failed", "reason_code": reason}
        update_channel(root, local_date=local_date, channel="telegram_audio", state=state)
        return state
    except (TimeoutError, OSError, json.JSONDecodeError):
        state = {**intent, "state": "delivery_unknown", "reason_code": "response_lost"}
        update_channel(root, local_date=local_date, channel="telegram_audio", state=state)
        return state
    state = {
        **intent,
        "state": "acknowledged",
        "message_id": message_id,
        "acknowledged_at": format_timestamp(utc_now()),
    }
    return _commit_acknowledgment(
        root,
        local_date=local_date,
        channel="telegram_audio",
        state=state,
        intent=intent,
    )


def reconcile(root: Path, request: dict[str, Any]) -> dict[str, Any]:
    local_date = str(request["local_date"])
    channel = str(request["channel"])
    if channel not in {"telegram_text", "telegram_audio"}:
        raise TelegramError("reconciliation channel must be Telegram text or audio")
    outbox = json.loads(outbox_path(root, local_date).read_text(encoding="utf-8"))
    current = outbox[channel]
    if current.get("state") not in {"delivery_unknown", "reconciliation_required"}:
        raise TelegramError("only ambiguous delivery can be reconciled")
    resolution = request.get("resolution")
    if resolution == "acknowledged":
        message_ids = request.get("message_ids")
        if not isinstance(message_ids, list) or not message_ids:
            raise TelegramError("acknowledged reconciliation requires provider message IDs")
        state = {
            **current,
            "state": "acknowledged",
            "message_ids": message_ids,
            "acknowledged_at": request.get("acknowledged_at") or format_timestamp(utc_now()),
            "reconciled": True,
        }
        if channel == "telegram_audio":
            state["message_id"] = message_ids[0]
    elif resolution == "not_delivered":
        state = {
            **current,
            "state": "failed",
            "reason_code": "operator_verified_not_delivered",
            "reconciled": True,
        }
    else:
        raise TelegramError("resolution must be acknowledged or not_delivered")
    update_channel(root, local_date=local_date, channel=channel, state=state)
    return state
