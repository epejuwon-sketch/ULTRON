"""Real multi-source Web Research provider with SSRF protection, citation preservation, credibility tagging, and verified-vs-inferred separation."""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from app.core.config import Settings
from app.core.security import validate_outbound_url


class _VisibleTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip = False
        self.title = ""
        self._in_title = False
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        t = tag.lower()
        if t in {"script", "style", "noscript"}:
            self._skip = True
        elif t == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in {"script", "style", "noscript"}:
            self._skip = False
        elif t == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        cleaned = data.strip()
        if not cleaned:
            return
        if self._in_title:
            self.title += (" " + cleaned) if self.title else cleaned
        else:
            self._chunks.append(cleaned)

    def extracted_text(self, max_chars: int = 4000) -> str:
        joined = re.sub(r"\s+", " ", " ".join(self._chunks)).strip()
        return joined[:max_chars]


class _DuckDuckGoResultParser(HTMLParser):
    """Lightweight parser for DuckDuckGo public HTML search results (no JS/headless browser needed)."""

    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict[str, str]] = []
        self._in_title_link = False
        self._in_snippet = False
        self._current_url = ""
        self._current_title: list[str] = []
        self._current_snippet: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        attr_map = dict(attrs)
        cls = str(attr_map.get("class") or "")
        if tag == "a" and "result__a" in cls:
            raw_href = str(attr_map.get("href") or "")
            self._current_url = _unwrap_ddg_url(raw_href)
            self._current_title = []
            self._in_title_link = True
        elif tag in ("a", "div", "span") and "result__snippet" in cls:
            self._current_snippet = []
            self._in_snippet = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_title_link:
            self._in_title_link = False
            title = html.unescape(" ".join(self._current_title)).strip()
            if title and self._current_url.startswith(("http://", "https://")):
                self.results.append({"title": title, "url": self._current_url, "snippet": ""})
        elif self._in_snippet and tag in ("a", "div", "span"):
            self._in_snippet = False
            snippet = html.unescape(" ".join(self._current_snippet)).strip()
            if self.results and snippet and not self.results[-1]["snippet"]:
                self.results[-1]["snippet"] = re.sub(r"\s+", " ", snippet)[:400]

    def handle_data(self, data: str) -> None:
        txt = data.strip()
        if not txt:
            return
        if self._in_title_link:
            self._current_title.append(txt)
        elif self._in_snippet:
            self._current_snippet.append(txt)


def _unwrap_ddg_url(raw_href: str) -> str:
    if not raw_href:
        return ""
    if raw_href.startswith("//"):
        raw_href = "https:" + raw_href
    parsed = urlparse(raw_href)
    if "duckduckgo.com" in (parsed.netloc or "") and parsed.path.startswith("/l/"):
        qs = parse_qs(parsed.query)
        uddg = qs.get("uddg", [""])[0]
        if uddg:
            return unquote(uddg)
    return raw_href


def _extract_domain(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower().removeprefix("www.")
    except Exception:
        return ""


def _classify_domain_credibility(domain: str) -> str:
    if not domain:
        return "web"
    if domain.endswith((".gov", ".edu", ".org")) or any(
        d in domain
        for d in (
            "wikipedia.org",
            "reuters.com",
            "bloomberg.com",
            "ft.com",
            "lamborghini.com",
            "caranddriver.com",
            "edmunds.com",
            "kbb.com",
            "hagerty.com",
            "dupontregistry.com",
            "classic.com",
            "bringatrailer.com",
            "rmsothebys.com",
            "motor1.com",
            "autotrader.com",
            "cars.com",
        )
    ):
        return "established_source"
    return "web_source"


class WebResearchClient:
    """Multi-source web search & SSRF-safe webpage extraction client preserving citations and provenance."""

    def __init__(self, settings: Settings, http_client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._client = http_client

    def _get(self, url: str, params: dict[str, Any] | None = None, timeout: float = 10.0) -> httpx.Response:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; ULTRON-OS-2026-ResearchBot/1.0)",
            "Accept-Language": "en-US,en;q=0.9",
        }
        if self._client is not None:
            return self._client.get(url, params=params, headers=headers, timeout=timeout, follow_redirects=False)
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            return client.get(url, params=params, headers=headers)

    def search(self, query: str, *, max_results: int = 5) -> dict[str, Any]:
        """Search Google Programmable Search + live DuckDuckGo web search + Wikipedia with explicit provenance."""
        verified_sources: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        providers_queried: list[str] = []
        provider_errors: list[dict[str, str]] = []
        retrieved_at = datetime.now(timezone.utc).isoformat()

        def _append_source(provider: str, title: str, url: str, snippet: str) -> None:
            clean_url = (url or "").strip()
            if not clean_url or clean_url in seen_urls:
                return
            seen_urls.add(clean_url)
            domain = _extract_domain(clean_url)
            verified_sources.append(
                {
                    "provider": provider,
                    "title": (title or domain or "Web Source").strip()[:220],
                    "url": clean_url,
                    "domain": domain,
                    "credibility": _classify_domain_credibility(domain),
                    "snippet": re.sub(r"\s+", " ", (snippet or "")).strip()[:420],
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                }
            )

        # 1. Official Google Programmable Search JSON API when configured
        if self._settings.google_search_api_key and self._settings.google_search_cx.strip():
            providers_queried.append("google_custom_search")
            try:
                resp = self._get(
                    "https://www.googleapis.com/customsearch/v1",
                    params={
                        "key": self._settings.google_search_api_key.get_secret_value().strip(),
                        "cx": self._settings.google_search_cx.strip(),
                        "q": query,
                        "num": min(10, max_results),
                    },
                )
                if 200 <= resp.status_code < 300:
                    for item in resp.json().get("items", []):
                        _append_source(
                            "google_custom_search",
                            item.get("title", ""),
                            item.get("link", ""),
                            item.get("snippet", ""),
                        )
                else:
                    provider_errors.append({"provider": "google_custom_search", "error": f"HTTP {resp.status_code}"})
            except httpx.HTTPError as exc:
                provider_errors.append({"provider": "google_custom_search", "error": type(exc).__name__})

        # 2. Live DuckDuckGo public HTML search (real-time market, pricing & news sources without requiring paid key)
        if len(verified_sources) < max_results:
            providers_queried.append("duckduckgo_web")
            try:
                resp = self._get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": query},
                    timeout=8.0,
                )
                if 200 <= resp.status_code < 300:
                    parser = _DuckDuckGoResultParser()
                    parser.feed(resp.text)
                    for item in parser.results[: max_results * 2]:
                        if len(verified_sources) >= max_results:
                            break
                        _append_source("duckduckgo_web", item["title"], item["url"], item["snippet"])
                else:
                    provider_errors.append({"provider": "duckduckgo_web", "error": f"HTTP {resp.status_code}"})
            except httpx.HTTPError as exc:
                provider_errors.append({"provider": "duckduckgo_web", "error": type(exc).__name__})

        # 3. Wikipedia OpenSearch / Query API (public structured encyclopedia & historical specification source)
        if len(verified_sources) < max_results:
            providers_queried.append("wikipedia_api")
            try:
                resp = self._get(
                    "https://en.wikipedia.org/w/api.php",
                    params={
                        "action": "query",
                        "list": "search",
                        "srsearch": query,
                        "srlimit": min(5, max_results),
                        "format": "json",
                    },
                    timeout=8.0,
                )
                if 200 <= resp.status_code < 300:
                    for item in resp.json().get("query", {}).get("search", []):
                        title = item.get("title", "")
                        snippet = re.sub(r"<[^>]+>", "", item.get("snippet", ""))
                        slug = title.replace(" ", "_")
                        _append_source(
                            "wikipedia_api",
                            title,
                            f"https://en.wikipedia.org/wiki/{slug}",
                            snippet,
                        )
                else:
                    provider_errors.append({"provider": "wikipedia_api", "error": f"HTTP {resp.status_code}"})
            except httpx.HTTPError as exc:
                provider_errors.append({"provider": "wikipedia_api", "error": type(exc).__name__})

        top_sources = verified_sources[:max_results]
        return {
            "query": query,
            "retrieved_at": retrieved_at,
            "providers_queried": providers_queried,
            "verified_sources": top_sources,
            "provider_errors": provider_errors,
            "citations": [s["url"] for s in top_sources if s.get("url")],
            "provenance": {
                "source": ", ".join(providers_queried) or "web_research",
                "retrieved_at": retrieved_at,
                "verification_status": "LIVE_VERIFIED" if top_sources else "UNAVAILABLE",
                "cache_status": "live",
                "source_count": len(top_sources),
            },
            "epistemic_notice": (
                "All entries in `verified_sources` were retrieved verbatim from live HTTP responses; "
                "empty results indicate network/provider unavailability rather than fabricated summaries."
            ),
        }

    def fetch_and_extract(self, url: str, *, max_chars: int = 4000) -> dict[str, Any]:
        """SSRF-protected public webpage retrieval and visible text extraction."""
        safe_url = validate_outbound_url(url)
        try:
            resp = self._get(safe_url, timeout=10.0)
        except httpx.HTTPError as exc:
            return {
                "url": safe_url,
                "retrieved": False,
                "error": f"Network error: {type(exc).__name__}",
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
            }
        content_type = resp.headers.get("content-type", "")
        if "html" in content_type.lower():
            parser = _VisibleTextExtractor()
            parser.feed(resp.text)
            title = parser.title
            text = parser.extracted_text(max_chars=max_chars)
        else:
            title = ""
            text = resp.text[:max_chars]

        return {
            "url": safe_url,
            "domain": _extract_domain(safe_url),
            "retrieved": 200 <= resp.status_code < 300,
            "status_code": resp.status_code,
            "content_type": content_type,
            "title": title,
            "extracted_text": text,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        }
