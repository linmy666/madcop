"""v1.6.0 — Web search and fetch tools.

Two tools the agent can call:

  web_search  — query a search engine, return top results
  web_fetch   — download a URL, return cleaned text/markdown

Both are registered as ``Tool`` subclasses so the agent's tool-use loop
can invoke them like any other tool.

Why no external dependency?
  - DuckDuckGo's HTML endpoint is free, no API key, no rate limit
    for personal use.
  - ``web_fetch`` uses stdlib ``urllib`` + a tiny HTML-to-text
    converter. For production you'd swap in ``httpx`` + ``selectolax``
    or an MCP server, but stdlib is enough for v1.6.

Design (Qian control theory):
  - 稳定性: timeout on every request; never hang the agent loop
  - 可控性: every fetch is logged (URL + status + bytes)
  - 层次化: web_search → list of URLs; web_fetch → one URL's content
"""
from __future__ import annotations

import logging
import re
import urllib.parse
import urllib.request
from typing import Any

from .registry import Tool

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 10
_MAX_CONTENT_BYTES = 200_000  # 200 KB cap — LLMs don't need more
_MAX_RESULTS = 8
_USER_AGENT = "madcop/1.6 (+https://github.com/linmy666/madcop)"


def _http_get(url: str, timeout: int = _DEFAULT_TIMEOUT) -> bytes:
    """Fetch a URL with a timeout. Returns raw bytes."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": _USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        # Read at most _MAX_CONTENT_BYTES to prevent memory bombs
        return resp.read(_MAX_CONTENT_BYTES)


# --------------------------------------------------------------------------- #
# WebSearchTool
# --------------------------------------------------------------------------- #


class WebSearchTool(Tool):
    """Search the web using DuckDuckGo's HTML endpoint.

    Returns a list of ``{title, url, snippet}`` dicts.
    No API key required.
    """

    name = "web_search"
    description = (
        "Search the web for a query. Returns top results with "
        "title, URL, and snippet. Use this to find current information."
    )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (3-5 keywords work best).",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Max results to return (default 5).",
                },
            },
            "required": ["query"],
        }

    def __call__(self, **kwargs: Any) -> list[dict[str, str]]:
        query = kwargs.get("query", "").strip()
        if not query:
            return []

        max_results = int(kwargs.get("max_results", 5))
        max_results = min(max(1, max_results), _MAX_RESULTS)

        try:
            results = self._search_ddg(query, max_results)
            logger.info("web_search '%s': %d results", query, len(results))
            return results
        except Exception as e:
            logger.warning("web_search failed: %s", e)
            return [{"error": f"{type(e).__name__}: {e}"}]

    def _search_ddg(self, query: str, max_results: int) -> list[dict[str, str]]:
        """Search DuckDuckGo HTML endpoint."""
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        html = _http_get(url).decode("utf-8", errors="replace")

        results = []
        # Parse result blocks from DuckDuckGo HTML
        # Results are in <a class="result__a" href="...">title</a>
        # Snippets in <a class="result__snippet" ...>text</a>
        result_blocks = re.findall(
            r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>'
            r'.*?<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
            html, re.DOTALL,
        )

        for raw_url, raw_title, raw_snippet in result_blocks[:max_results]:
            # DuckDuckGo wraps URLs in a redirect
            # //duckduckgo.com/l/?uddg=<encoded_url>
            if "uddg=" in raw_url:
                parsed = urllib.parse.parse_qs(
                    urllib.parse.urlparse(raw_url).query
                )
                clean_url = parsed.get("uddg", [raw_url])[0]
            else:
                clean_url = raw_url

            title = re.sub(r"<[^>]+>", "", raw_title).strip()
            snippet = re.sub(r"<[^>]+>", "", raw_snippet).strip()

            if title and clean_url:
                results.append({
                    "title": title,
                    "url": clean_url,
                    "snippet": snippet[:200],
                })

        return results


# --------------------------------------------------------------------------- #
# WebFetchTool
# --------------------------------------------------------------------------- #


class WebFetchTool(Tool):
    """Fetch a URL and return cleaned text content.

    Strips HTML tags, collapses whitespace, caps at ~4K chars
    (enough for an LLM context window).
    """

    name = "web_fetch"
    description = (
        "Fetch a web page and return its text content. "
        "Good for reading articles, docs, or API responses."
    )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch.",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Max characters to return (default 4000).",
                },
            },
            "required": ["url"],
        }

    def __call__(self, **kwargs: Any) -> dict[str, Any]:
        url = kwargs.get("url", "").strip()
        if not url:
            return {"error": "missing 'url' parameter"}

        if not url.startswith(("http://", "https://")):
            return {"error": f"URL must start with http:// or https:// (got: {url[:50]})"}

        max_chars = int(kwargs.get("max_chars", 4000))

        try:
            raw = _http_get(url)
            content_type = ""
            # Try to detect content type
            if url.endswith(".txt") or url.endswith(".md"):
                text = raw.decode("utf-8", errors="replace")
            elif url.endswith(".json"):
                text = raw.decode("utf-8", errors="replace")
            else:
                # Assume HTML — strip tags
                html = raw.decode("utf-8", errors="replace")
                text = self._html_to_text(html)
                content_type = "html"

            # Truncate
            truncated = len(text) > max_chars
            text = text[:max_chars]

            logger.info("web_fetch '%s': %d chars", url, len(text))
            return {
                "url": url,
                "content": text,
                "chars": len(text),
                "truncated": truncated,
                "content_type": content_type or "text",
            }
        except Exception as e:
            logger.warning("web_fetch '%s' failed: %s", url, e)
            return {"error": f"{type(e).__name__}: {e}"}

    @staticmethod
    def _html_to_text(html: str) -> str:
        """Minimal HTML → text converter.

        Removes scripts, styles, tags. Collapses whitespace.
        Not a full parser — good enough for article reading.
        """
        # Remove script and style blocks
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)

        # Convert common block elements to newlines
        html = re.sub(r"<(?:p|div|br|h[1-6]|li|tr)[^>]*>", "\n", html, flags=re.IGNORECASE)

        # Strip all remaining tags
        text = re.sub(r"<[^>]+>", "", html)

        # Decode common HTML entities
        entities = {
            "&amp;": "&", "&lt;": "<", "&gt;": ">",
            "&quot;": '"', "&#39;": "'", "&nbsp;": " ",
            "&hellip;": "...", "&mdash;": "—", "&ndash;": "–",
        }
        for entity, char in entities.items():
            text = text.replace(entity, char)

        # Collapse whitespace
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()


__all__ = ["WebSearchTool", "WebFetchTool"]
