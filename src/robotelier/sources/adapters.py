"""Bounded, metadata-only source adapter implementations."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from robotelier.identity import canonical_url
from robotelier.utils import ContractError

ADAPTER_ID = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")
TEXT_CONTENT_TYPES = (
    "application/atom+xml",
    "application/json",
    "application/rss+xml",
    "application/xml",
    "text/html",
    "text/plain",
    "text/xml",
)


def validate_adapter_id(value: str) -> str:
    if not ADAPTER_ID.fullmatch(value):
        raise ContractError(f"invalid adapter ID: {value!r}")
    return value


class Adapter(Protocol):
    adapter_id: str

    def scan(self, *, limit: int) -> list[Any]: ...


@dataclass(frozen=True, slots=True)
class Candidate:
    adapter_id: str
    external_id: str | None
    url: str
    title: str
    publisher: str | None
    author: str | None
    language: str | None
    published_at: str | None
    event_at: str | None
    source_kind: str
    origin_url: str | None
    media: tuple[dict[str, Any], ...]

    @classmethod
    def from_mapping(cls, adapter_id: str, value: dict[str, Any]) -> Candidate:
        if not isinstance(value.get("url"), str) or not isinstance(value.get("title"), str):
            raise ContractError("candidate requires url and title")
        media = value.get("media", [])
        if not isinstance(media, list) or any(not isinstance(item, dict) for item in media):
            raise ContractError("candidate media must be an array of objects")
        return cls(
            adapter_id,
            value.get("external_id"),
            canonical_url(value["url"]),
            value["title"],
            value.get("publisher"),
            value.get("author"),
            value.get("language"),
            value.get("published_at"),
            value.get("event_at"),
            value.get("source_kind", "web_page"),
            value.get("origin_url"),
            tuple(media),
        )


class FixtureAdapter:
    """Deterministic adapter used by offline rehearsals and recorded provider contracts."""

    def __init__(self, adapter_id: str, path: Path) -> None:
        self.adapter_id = validate_adapter_id(adapter_id)
        self.path = path

    def scan(self, *, limit: int) -> list[Candidate]:
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(value, list):
            raise ContractError("fixture adapter input must be an array")
        return [Candidate.from_mapping(self.adapter_id, row) for row in value[:limit]]


class FeedAdapter:
    """Parse already-retrieved RSS/Atom text; network retrieval remains controller-owned."""

    def __init__(self, adapter_id: str, payload: str, *, publisher: str | None = None) -> None:
        self.adapter_id = validate_adapter_id(adapter_id)
        self.payload = payload
        self.publisher = publisher

    @staticmethod
    def _text(element: ET.Element, names: tuple[str, ...]) -> str | None:
        for child in element.iter():
            if child.tag.rsplit("}", 1)[-1] in names and child.text and child.text.strip():
                return child.text.strip()
        return None

    def scan(self, *, limit: int) -> list[Candidate]:
        try:
            root = ET.fromstring(self.payload)
        except ET.ParseError as exc:
            raise ContractError(f"invalid RSS/Atom XML: {exc}") from exc
        entries = [node for node in root.iter() if node.tag.rsplit("}", 1)[-1] in {"item", "entry"}]
        result: list[Candidate] = []
        for entry in entries[:limit]:
            title = self._text(entry, ("title",)) or "Untitled source"
            link = self._text(entry, ("link",))
            if link is None:
                for child in entry.iter():
                    if child.tag.rsplit("}", 1)[-1] == "link" and child.attrib.get("href"):
                        link = child.attrib["href"]
                        break
            if not link:
                continue
            result.append(
                Candidate(
                    self.adapter_id,
                    self._text(entry, ("guid", "id")),
                    canonical_url(link),
                    title,
                    self.publisher,
                    self._text(entry, ("author", "creator")),
                    None,
                    self._text(entry, ("published", "pubDate", "updated")),
                    None,
                    "feed_entry",
                    None,
                    (),
                )
            )
        return result


class _SafeRedirects(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> Request | None:
        canonical_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_text(url: str, *, maximum_bytes: int, timeout_seconds: int = 30) -> tuple[str, str, str]:
    safe_url = canonical_url(url)
    opener = build_opener(_SafeRedirects())
    request = Request(
        safe_url,
        headers={"User-Agent": "Robotelier/0.1 (+https://github.com/)"},
    )
    with opener.open(request, timeout=timeout_seconds) as response:
        effective = canonical_url(response.geturl())
        content_type = response.headers.get_content_type().lower()
        if content_type not in TEXT_CONTENT_TYPES and not content_type.startswith("text/"):
            raise ContractError(f"source returned forbidden content type: {content_type}")
        payload = response.read(maximum_bytes + 1)
        if len(payload) > maximum_bytes:
            raise ContractError("source response exceeds configured text-byte limit")
        charset = response.headers.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset), effective, content_type
    except (LookupError, UnicodeDecodeError) as exc:
        raise ContractError("source response is not valid permitted text") from exc


class HttpFeedAdapter:
    """Fetch and parse one bounded official RSS/Atom feed without retaining its body."""

    def __init__(
        self,
        adapter_id: str,
        url: str,
        *,
        maximum_bytes: int,
        publisher: str | None = None,
    ) -> None:
        self.adapter_id = validate_adapter_id(adapter_id)
        self.url = canonical_url(url)
        self.maximum_bytes = maximum_bytes
        self.publisher = publisher

    def scan(self, *, limit: int) -> list[Candidate]:
        payload, _, _ = fetch_text(self.url, maximum_bytes=self.maximum_bytes)
        return FeedAdapter(self.adapter_id, payload, publisher=self.publisher).scan(limit=limit)


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() == "a":
            values = dict(attrs)
            self._href = values.get("href")
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "a" and self._href is not None:
            self.links.append((self._href, " ".join("".join(self._text).split())))
            self._href = None
            self._text = []


class WebPageAdapter:
    """Discover bounded public links from an official announcement/index page."""

    def __init__(
        self,
        adapter_id: str,
        url: str,
        *,
        maximum_bytes: int,
        publisher: str | None = None,
        language: str | None = None,
    ) -> None:
        self.adapter_id = validate_adapter_id(adapter_id)
        self.url = canonical_url(url)
        self.maximum_bytes = maximum_bytes
        self.publisher = publisher
        self.language = language

    def scan(self, *, limit: int) -> list[Candidate]:
        payload, effective, _ = fetch_text(self.url, maximum_bytes=self.maximum_bytes)
        parser = _Links()
        parser.feed(payload)
        expected_host = urlsplit(effective).hostname
        seen: set[str] = set()
        result: list[Candidate] = []
        for href, title in parser.links:
            try:
                url = canonical_url(urljoin(effective, href))
            except ContractError:
                continue
            if urlsplit(url).hostname != expected_host or url in seen or url == effective or not title:
                continue
            seen.add(url)
            result.append(
                Candidate(
                    self.adapter_id,
                    url,
                    url,
                    title[:500],
                    self.publisher,
                    None,
                    self.language,
                    None,
                    None,
                    "official_website_link",
                    None,
                    (),
                )
            )
            if len(result) >= limit:
                break
        return result


class MetadataAdapter:
    """Normalize already retrieved repository, paper, event, or video metadata."""

    def __init__(self, adapter_id: str, values: list[dict[str, Any]]) -> None:
        self.adapter_id = validate_adapter_id(adapter_id)
        self.values = values

    def scan(self, *, limit: int) -> list[Candidate]:
        return [Candidate.from_mapping(self.adapter_id, value) for value in self.values[:limit]]
