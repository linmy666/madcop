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

        # v3.12 — Multi-strategy web search (inspired by Hermes).
        # Priority:
        # 0. visitproject (if VISITPROJECT_BIN env set — agentic MCP
        #    server, best quality: dedup + rerank + content extraction.
        #    See https://github.com/linmy666/visitproject for the source.)
        # 1. SearXNG (if SEARXNG_URL env set — self-hosted, free, good quality)
        # 2. Tavily API (if TAVILY_API_KEY env set — paid but reliable)
        # 3. Bing cn.bing.com (free, low quality in China)
        # 4. DuckDuckGo lite (blocked in China, kept for VPN users)
        # 5. LLM knowledge fallback (uses active provider's model)

        import os
        visitproject_bin = os.environ.get("VISITPROJECT_BIN", "").strip()
        searxng_url = os.environ.get("SEARXNG_URL", "").strip()
        tavily_key = os.environ.get("TAVILY_API_KEY", "").strip()

        # Strategy 0: visitproject (highest priority — best quality)
        if visitproject_bin:
            try:
                results = self._search_visitproject(query, max_results)
                if results:
                    logger.info(
                        "web_search '%s' [visitproject]: %d results",
                        query, len(results),
                    )
                    return results
            except Exception as e:
                logger.warning("web_search [visitproject] failed: %s", e)

        # Strategy 1: SearXNG
        if searxng_url:
            try:
                results = self._search_searxng(query, max_results, searxng_url)
                if results:
                    logger.info("web_search '%s' [searxng]: %d results", query, len(results))
                    return results
            except Exception as e:
                logger.warning("web_search [searxng] failed: %s", e)

        # Strategy 2: Tavily
        if tavily_key:
            try:
                results = self._search_tavily(query, max_results, tavily_key)
                if results:
                    logger.info("web_search '%s' [tavily]: %d results", query, len(results))
                    return results
            except Exception as e:
                logger.warning("web_search [tavily] failed: %s", e)

        # Strategy 3+4: Playwright Baidu (best free option in China), then Bing, DDG
        for engine, search_fn in [
            ("baidu_pw", self._search_baidu_playwright),
            ("bing", self._search_bing),
            ("ddg", self._search_ddg),
        ]:
            try:
                results = search_fn(query, max_results)
                if results and self._results_are_relevant(results, query):
                    logger.info("web_search '%s' [%s]: %d results", query, engine, len(results))
                    return results
            except Exception as e:
                logger.warning("web_search [%s] failed: %s", engine, e)

        # Strategy 5: LLM knowledge fallback — return a clear message
        # so the agent uses its own knowledge instead of looping.
        return [{"error": "搜索引擎不可用。请用你自己的知识回答，不要再尝试搜索。"}]

    def _search_baidu_playwright(self, query: str, max_results: int) -> list[dict[str, str]]:
        """Search Baidu using Playwright (real browser, bypasses anti-bot).

        This is the most reliable free search method in China. Uses
        headless Chromium with stealth flags + direct URL access.
        """
        from playwright.sync_api import sync_playwright
        import time as _time

        results: list[dict[str, str]] = []
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="zh-CN",
            )
            page = context.new_page()
            page.goto(
                f"https://www.baidu.com/s?wd={urllib.parse.quote(query)}",
                timeout=15000,
            )
            _time.sleep(3)

            # Check for captcha
            content = page.content()
            if "wappass.baidu.com" in content or "captcha" in content.lower():
                browser.close()
                return []

            # Extract results: Baidu uses [class*="result"] h3 a
            items = page.query_selector_all(
                '[class*="result"] h3 a, .c-container h3 a, h3.t a'
            )
            for item in items[:max_results]:
                title = item.inner_text().strip()
                href = item.get_attribute("href") or ""
                if title and href:
                    results.append({"title": title[:120], "url": href, "snippet": ""})

            # Try to get snippets from sibling elements
            if results:
                containers = page.query_selector_all('[class*="result"], .c-container')
                for i, container in enumerate(containers[:len(results)]):
                    snippet_el = container.query_selector(
                        '[class*="content"], [class*="abstract"], span.content-right_8Zs40'
                    )
                    if snippet_el:
                        snippet = snippet_el.inner_text().strip()[:200]
                        if i < len(results):
                            results[i]["snippet"] = snippet

            browser.close()
        return results

    def _search_visitproject(self, query: str, max_results: int) -> list[dict[str, str]]:
        """Search via visitproject (agentic MCP server — best quality).

        visitproject is an open-source (https://github.com/linmy666)
        MCP server that wraps SearXNG with dedup, embedding-based
        rerank, LLM content extraction, and caching. We invoke it as
        a subprocess speaking the stdio MCP protocol via the existing
        ``MCPClient``.

        Env vars (all forwarded to the subprocess):
          VISITPROJECT_BIN          — required; path to dist/index.js
          VISITPROJECT_SEARXNG_URL  — forwarded as SEARXNG_URL
          VISITPROJECT_LLM_PROVIDER — forwarded as LLM_PROVIDER (openai|ollama)
          VISITPROJECT_LLM_BASE_URL — forwarded as LLM_BASE_URL
          VISITPROJECT_LLM_API_KEY  — forwarded as LLM_API_KEY
          VISITPROJECT_LLM_MODEL    — forwarded as LLM_MODEL
          VISITPROJECT_EMBEDDING_MODEL — forwarded as EMBEDDING_MODEL
          (any other VISITPROJECT_* env var is also forwarded with
          the prefix stripped — useful for HTTPS_PROXY etc.)

        A single subprocess is shared across calls (singleton on the
        ``WebSearchTool`` class) so the browser warm-up cost is paid
        once. The subprocess is killed automatically at process exit
        via ``atexit``.
        """
        import atexit
        import os
        from .mcp import MCPClient

        bin_path = os.environ.get("VISITPROJECT_BIN", "").strip()
        if not bin_path:
            return []

        # Build subprocess env: inherit current env, then forward any
        # VISITPROJECT_* vars with the prefix stripped (so users can
        # configure SEARXNG_URL etc. without polluting MadCop's env).
        sub_env = dict(os.environ)
        for k, v in os.environ.items():
            if k.startswith("VISITPROJECT_") and k != "VISITPROJECT_BIN":
                sub_env[k[len("VISITPROJECT_"):]] = v

        # Singleton MCP client (one visitproject subprocess per process).
        client = self.__class__._visitproject_client
        if client is None:
            client = MCPClient(
                command=["node", bin_path],
                env=sub_env,
                timeout_s=60.0,
            )
            client.connect()
            # Kill on process exit so we don't leave zombies.
            atexit.register(client.close)
            self.__class__._visitproject_client = client

        # Call the `search` MCP tool. visitproject returns content as
        # a list of text blocks; the first block's text is the JSON
        # payload: `{"results": [{"title","url","snippet","score"}, ...]}`.
        result = client.call_tool("search", {
            "query": query,
            "max_results": max_results,
            # Default depth is "deep" (agentic). For web_search use
            # we want "quick" to keep latency low — agent can re-call
            # if it needs deeper research.
            "depth": os.environ.get("VISITPROJECT_DEPTH", "quick"),
        })
        if not result:
            return []

        import json as _json
        content_blocks = result.get("content") if isinstance(result, dict) else None
        if not content_blocks and isinstance(result, list):
            content_blocks = result
        if not content_blocks:
            return []

        text = ""
        for block in content_blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                text += block.get("text", "")
        if not text:
            return []

        try:
            parsed = _json.loads(text)
        except Exception:
            # visitproject may return non-JSON text in error cases.
            logger.warning(
                "visitproject returned non-JSON text: %s",
                text[:200],
            )
            return []

        items = parsed.get("results") if isinstance(parsed, dict) else None
        if not items:
            return []

        out: list[dict[str, str]] = []
        for item in items[:max_results]:
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or "").strip()
            url = (item.get("url") or "").strip()
            snippet = (item.get("snippet") or item.get("content") or "").strip()
            if not (title and url):
                continue
            out.append({
                "title": title[:300],
                "url": url[:500],
                "snippet": snippet[:400],
            })
        return out

    # Class-level singleton for the visitproject subprocess. Lazily
    # initialized on first call to _search_visitproject(); killed at
    # interpreter exit via atexit.
    _visitproject_client: Any = None

    def _search_searxng(self, query: str, max_results: int, base_url: str) -> list[dict[str, str]]:
        """Search via a self-hosted SearXNG instance (best quality, free)."""
        url = f"{base_url.rstrip('/')}/search"
        import urllib.parse as up
        params = up.urlencode({"q": query, "format": "json", "pageno": 1})
        data = _http_get(f"{url}?{params}")
        import json as _json
        parsed = _json.loads(data)
        results = []
        for item in parsed.get("results", [])[:max_results]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("content", "")[:200],
            })
        return results

    def _search_tavily(self, query: str, max_results: int, api_key: str) -> list[dict[str, str]]:
        """Search via Tavily API (paid but high quality)."""
        import json as _json
        req = urllib.request.Request(
            "https://api.tavily.com/search",
            data=_json.dumps({
                "api_key": api_key,
                "query": query,
                "max_results": max_results,
                "include_answer": True,
            }).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=_DEFAULT_TIMEOUT) as resp:
            data = _json.loads(resp.read())
        results = []
        # Tavily returns an 'answer' field + 'results' array
        if data.get("answer"):
            results.append({"title": "AI Summary", "url": "", "snippet": data["answer"][:300]})
        for item in data.get("results", [])[:max_results]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("content", "")[:200],
            })
        return results

    def _results_are_relevant(self, results: list[dict], query: str) -> bool:
        """Heuristic: check if search results are actually relevant
        to the query (not dictionary entries or unrelated content)."""
        if not results:
            return False
        # If the first result's title is just a domain name, it's
        # likely the display-URL parsing bug, not a real result.
        first_title = results[0].get("title", "")
        if first_title.startswith("http") or "." in first_title.split()[0:1][0] if first_title.split() else False:
            return False
        # If query has meaningful words but titles look like dictionary
        # entries (pinyin, word definitions), skip.
        query_words = [w.lower() for w in query.replace("+", " ").split() if len(w) > 2]
        if not query_words:
            return True
        # At least one query word should appear in titles or snippets
        all_text = " ".join(r.get("title", "") + r.get("snippet", "") for r in results).lower()
        matches = sum(1 for w in query_words if w in all_text)
        return matches >= max(1, len(query_words) // 3)

    def _search_bing(self, query: str, max_results: int) -> list[dict[str, str]]:
        """Search Bing China HTML endpoint (reachable without VPN)."""
        # www.bing.com redirects to cn.bing.com in China (returns only
        # 173 bytes redirect). Use cn.bing.com directly.
        url = f"https://cn.bing.com/search?q={urllib.parse.quote(query)}&count={max_results}"
        html = _http_get(url).decode("utf-8", errors="replace")

        results: list[dict[str, str]] = []
        block_pattern = re.compile(
            r'<li[^>]*class="b_algo"[^>]*>(.*?)</li>',
            re.DOTALL,
        )
        blocks = block_pattern.findall(html)
        for block in blocks[:max_results]:
            # Remove CSS/JS link tags that pollute the block
            clean_block = re.sub(r'<link[^>]*/?>', '', block)
            # v3.10.3 — Bing has TWO <a> tags per result:
            #   1st: display URL (domain + url concatenated, garbage title)
            #   2nd: actual title text
            # Find ALL external links, pick the one with a real title
            all_links = re.findall(
                r'<a[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>',
                clean_block, re.DOTALL,
            )
            raw_url = ""
            raw_title = ""
            for url, title_html in all_links:
                title_text = re.sub(r"<[^>]+>", "", title_html).strip()
                # Skip bing.com internal links
                if "bing.com" in url:
                    continue
                # Skip links where title is just a domain name (display URL)
                if title_text and not title_text.startswith("http") and "." not in title_text.split()[0] if title_text else True:
                    raw_url = url
                    raw_title = title_text
                    break
                # Fallback: use any non-bing link even if title looks like domain
                if not raw_url:
                    raw_url = url
                    raw_title = title_text
            if not raw_url:
                continue
            # Extract snippet
            snippet_m = re.search(r'<p[^>]*>(.*?)</p>', clean_block, re.DOTALL)
            snippet = re.sub(r"<[^>]+>", "", snippet_m.group(1)).strip() if snippet_m else ""
            # Clean HTML entities
            for ent, char in [("&amp;", "&"), ("&ensp;", " "), ("&#0183;", "·"), ("&lt;", "<"), ("&gt;", ">")]:
                raw_title = raw_title.replace(ent, char)
                snippet = snippet.replace(ent, char)

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
