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

# macOS Python sometimes lacks certs; create a fallback SSL context.
import ssl as _ssl
_ssl_ctx = _ssl.create_default_context()
_ssl_ctx_fallback = _ssl.create_default_context()
_ssl_ctx_fallback.check_hostname = False
_ssl_ctx_fallback.verify_mode = _ssl.CERT_NONE


def _http_get(url: str, timeout: int = _DEFAULT_TIMEOUT) -> bytes:
    """Fetch a URL with a timeout. Returns raw bytes."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": _USER_AGENT},
    )
    # Use unverified SSL context — macOS Python often lacks certs.
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx_fallback) as resp:
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

        # v3.10.1 — try Bing first (reachable in China), then DuckDuckGo.
        for engine, search_fn in [
            ("bing", self._search_bing),
            ("ddg", self._search_ddg),
        ]:
            try:
                results = search_fn(query, max_results)
                if results:
                    logger.info("web_search '%s' [%s]: %d results", query, engine, len(results))
                    return results
            except Exception as e:
                logger.warning("web_search [%s] failed: %s", engine, e)
                continue
        return [{"error": "All search engines failed. Network may be blocked."}]

    def _search_bing(self, query: str, max_results: int) -> list[dict[str, str]]:
        """Search Bing HTML endpoint (reachable in China without VPN)."""
        url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}&count={max_results}"
        html = _http_get(url).decode("utf-8", errors="replace")

        results: list[dict[str, str]] = []
        # Bing search results:
        #   <li class="b_algo">
        #     <h2><a href="...">Title</a></h2>
        #     <p class="b_lineclamp...">Snippet</p>
        #   </li>
        block_pattern = re.compile(
            r'<li[^>]*class="b_algo"[^>]*>(.*?)</li>',
            re.DOTALL,
        )
        blocks = block_pattern.findall(html)
        for block in blocks[:max_results]:
            # Extract title + url
            link_m = re.search(r'<a[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL)
            if not link_m:
                continue
            raw_url = link_m.group(1)
            raw_title = re.sub(r"<[^>]+>", "", link_m.group(2)).strip()
            # Extract snippet
            snippet_m = re.search(r'<p[^>]*>(.*?)</p>', block, re.DOTALL)
            snippet = re.sub(r"<[^>]+>", "", snippet_m.group(1)).strip() if snippet_m else ""

            if raw_title and raw_url:
                results.append({
                    "title": raw_title,
                    "url": raw_url,
                    "snippet": snippet,
                })
        return results

    def _search_ddg(self, query: str, max_results: int) -> list[dict[str, str]]:
        """Search DuckDuckGo lite endpoint (more bot-resistant than html)."""
        url = f"https://lite.duckduckgo.com/lite/?q={urllib.parse.quote(query)}"
        html = _http_get(url).decode("utf-8", errors="replace")

        results: list[dict[str, str]] = []

        # lite.duckduckgo.com structure:
        #   <a rel="nofollow" href="//duckduckgo.com/l/?uddg=<url>" class='result-link'>Title</a>
        #   <td class='result-snippet'>Snippet text</td>
        #
        # Parse title+url pairs first, then match with snippets.
        link_pattern = re.compile(
            r"<a[^>]*href=\"([^\"]+)\"[^>]*class='result-link'[^>]*>(.*?)</a>",
            re.DOTALL,
        )
        snippet_pattern = re.compile(
            r"<td[^>]*class='result-snippet'[^>]*>(.*?)</td>",
            re.DOTALL,
        )

        links = link_pattern.findall(html)
        snippets = snippet_pattern.findall(html)

        for i, (raw_url, raw_title) in enumerate(links[:max_results]):
            # DuckDuckGo wraps URLs in a redirect: //duckduckgo.com/l/?uddg=<encoded>
            clean_url = raw_url
            if "uddg=" in raw_url:
                parsed = urllib.parse.parse_qs(
                    urllib.parse.urlparse(raw_url).query
                )
                clean_url = parsed.get("uddg", [raw_url])[0]

            title = re.sub(r"<[^>]+>", "", raw_title).strip()
            snippet = ""
            if i < len(snippets):
                snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip()

            if title and clean_url:
                results.append({
                    "title": title,
                    "url": clean_url,
                    "snippet": snippet,
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
