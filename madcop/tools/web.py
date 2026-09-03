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
# Pair the unverified context with ProxyHandler (urllib's default opener
# ignores `context=` when a ProxyHandler is active).
_ssl_handler_fallback = urllib.request.HTTPSHandler(context=_ssl_ctx_fallback)
_ssl_ctx_fallback.check_hostname = False
_ssl_ctx_fallback.verify_mode = _ssl.CERT_NONE

# v4 — SSRF guard. Prevents the agent from being prompt-injected
# into fetching internal resources (AWS metadata at 169.254.169.254,
# localhost services, private network hosts). Ported from the
# existing guard in app.py's fetch_provider_models endpoint.
_BLOCKED_IP_HINTS = ("169.254.169.254", "metadata.google.internal")


def _is_ssrf_url(url: str) -> bool:
    """Return True if the URL targets a private/loopback/link-local
    address (SSRF risk). Localhost is allowed for dev/test."""
    import ipaddress
    import socket
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return True
        host = parsed.hostname or ""
        if not host:
            return True
        # Fast-path: block known metadata endpoints by name.
        if host in _BLOCKED_IP_HINTS:
            return True
        # Resolve and check all IPs.
        try:
            addrs = socket.getaddrinfo(host, None)
        except socket.gaierror:
            addrs = []
        for _fam, _typ, _proto, _cn, sa in addrs:
            ip = ipaddress.ip_address(sa[0])
            if ip.is_link_local:
                return True
            if (ip.is_private or ip.is_loopback or ip.is_reserved) and host not in (
                "localhost", "127.0.0.1", "::1",
            ):
                return True
    except Exception:
        # On any parse error, block.
        return True
    return False


def _http_get(url: str, timeout: int = _DEFAULT_TIMEOUT) -> bytes:
    """Fetch a URL with a timeout. Returns raw bytes.

    SSRF-guarded: rejects private/loopback/link-local addresses.
    """
    if _is_ssrf_url(url):
        raise ValueError(
            f"URL blocked by SSRF guard (private/loopback/link-local): {url[:100]}"
        )
    req = urllib.request.Request(
        url,
        headers={"User-Agent": _USER_AGENT},
    )
    # Use unverified SSL context — macOS Python often lacks certs.
    # MADCOP_HTTPS_PROXY lets users route through a local proxy when
    # their ISP blocks outbound HTTPS to duckduckgo / wttr.in / etc.
    handlers = [_ssl_handler_fallback]
    proxy = os.environ.get("MADCOP_HTTPS_PROXY", "").strip()
    if proxy:
        handlers.insert(0, urllib.request.ProxyHandler(
            {"https": proxy, "http": proxy}))
    opener = urllib.request.build_opener(*handlers)
    with opener.open(req, timeout=timeout) as resp:
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
        "Search the web. Returns top results with title, URL, and snippet. "
        "IMPORTANT: use SHORT queries (2-4 keywords, e.g. '台风 最新') "
        "for best results. Long specific queries return irrelevant results. "
        "Use this for any time-sensitive or factual question."
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

        # BUG-FIX (批次4.3): normalize the query so Bing returns better
        # results. The LLM usually writes good queries, but some patterns
        # hurt Bing specifically:
        #   - Leading year ("2026年 台风...") makes Bing match the year
        #     heavily and return "2026年百科" entries. Move the year to
        #     the end (lower weight) or drop it if a recency word exists.
        #   - Colloquial filler ("看看", "帮我查一下", "的", "了") adds
        #     noise. Strip it.
        original_query = query
        query = self._optimize_query(query)

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
                    return self._rerank(results, query)
            except Exception as e:
                logger.warning("web_search [visitproject] failed: %s", e)

        # Strategy 1: SearXNG
        if searxng_url:
            try:
                results = self._search_searxng(query, max_results, searxng_url)
                if results:
                    logger.info("web_search '%s' [searxng]: %d results", query, len(results))
                    return self._rerank(results, query)
            except Exception as e:
                logger.warning("web_search [searxng] failed: %s", e)

        # Strategy 2: Tavily
        if tavily_key:
            try:
                results = self._search_tavily(query, max_results, tavily_key)
                if results:
                    logger.info("web_search '%s' [tavily]: %d results", query, len(results))
                    return self._rerank(results, query)
            except Exception as e:
                logger.warning("web_search [tavily] failed: %s", e)

        # Strategy 3+4: cheap/free engines first (Bing HTML works from
        # mainland China without VPN, <1s per request). Playwright Baidu
        # is high-quality but heavy — runs LAST and only if module is
        # actually importable (no point waiting on a 15s timeout if the
        # user doesn't have Playwright installed at all).
        #
        # BUG-FIX: previous order put Playwright FIRST, so every search
        # burned 15s on ModuleNotFoundError before falling through to
        # Bing. Reordering + skip-on-ImportError makes the typical
        # "user has just requests/urllib" case return results in <2s.
        cheap_engines = [
            ("bing", self._search_bing),
            ("ddg", self._search_ddg),
        ]
        for engine, search_fn in cheap_engines:
            try:
                results = search_fn(query, max_results)
                if results and self._results_are_relevant(results, query):
                    logger.info("web_search '%s' [%s]: %d results", query, engine, len(results))
                    return self._rerank(results, query)
            except Exception as e:
                logger.warning("web_search [%s] failed: %s", engine, e)

        # Playwright — only attempt if installed. Importing the module
        # is what costs the 15s timeout when missing; we probe it with a
        # try/except to skip silently on ImportError.
        try:
            import playwright  # noqa: F401
            results = self._search_baidu_playwright(query, max_results)
            if results and self._results_are_relevant(results, query):
                logger.info("web_search '%s' [baidu_pw]: %d results", query, len(results))
                return self._rerank(results, query)
        except ImportError:
            logger.info("web_search [baidu_pw] skipped: playwright not installed")
        except Exception as e:
            logger.warning("web_search [baidu_pw] failed: %s", e)

        # Strategy 5: LLM knowledge fallback — return a clear message
        # so the agent uses its own knowledge instead of looping.
        # P2-5 — include explicit `success: False` so callers can
        # distinguish "no results" (still a list) from "engine error"
        # without relying on the presence of an `error` key (which
        # could also appear in partial-failure backends).
        return [{"error": "搜索引擎不可用。请用你自己的知识回答，不要再尝试搜索。", "success": False}]

    # ------------------------------------------------------------------ #
    # Result quality: reranking + dictionary de-prioritization
    # ------------------------------------------------------------------ #

    # Colloquial filler words (Chinese) that add noise to search queries.
    # These are stripped from the query before sending to the engine.
    _FILLER_WORDS = {
        "看看", "看一下", "帮我看", "帮我查", "帮我查一下", "帮我", "帮忙",
        "查一下", "查下", "了解一下", "了解下", "想知道", "请问", "请帮我",
        "告诉我", "说说", "讲讲", "聊聊", "聊一下",
    }
    # Recency indicators — if present, we keep the current year for
    # freshness but move it to the end of the query.
    _RECENCY_RE = re.compile(r"(最新|今天|今日|现在|目前|最近|近期|实时|current|latest|today|now|recent)", re.IGNORECASE)

    @classmethod
    def _optimize_query(cls, query: str) -> str:
        """Lightweight query normalization for better Bing results.

        1. Strip colloquial filler ("看看", "帮我查一下", ...).
        2. If a recency word is present AND the query starts with a year,
           move the year to the end (Bing over-weights leading years and
           returns encyclopedia entries for "2026年 台风").
        3. Collapse repeated whitespace.
        Does NOT rewrite the query aggressively — the LLM's phrasing is
        preserved; we only remove obvious noise.
        """
        q = query.strip()
        # 1. Strip filler words (word-boundary-ish match for CJK).
        for filler in cls._FILLER_WORDS:
            q = q.replace(filler, " ")
        # 2. Year repositioning.
        m = re.match(r"^\s*(20\d{2})\s*年?\s*(.+)$", q)
        if m and cls._RECENCY_RE.search(q):
            year = m.group(1)
            rest = m.group(2).strip()
            q = f"{rest} {year}年"
        # 3. Collapse whitespace.
        q = re.sub(r"\s+", " ", q).strip()
        return q or query  # never return empty — fall back to original

    # Domains that are high-trust for news / official info.
    _TRUSTED_DOMAINS = (
        "news.cctv.com", "cctv.com", "gov.cn", "weather.com.cn",
        "nmc.cn", "typhoon.nmc.cn", "slt.zj.gov.cn",
        "xinhuanet.com", "people.com.cn", "chinanews.com",
    )
    # Domains / title patterns that signal dictionary / encyclopedia
    # entries — useful when the query IS a definition, but usually noise
    # for news / how-to / current-event queries.
    _DICT_DOMAINS = ("baike.baidu.com", "baike.so.com", "zdic.net", "cnki.net",
                     "iciba.com", "dict.cn", "youdao.com", "hujiang.com")
    _DICT_TITLE_RE = re.compile(
        r"(是什么意思|什么意思|汉语词语|百科|词典|翻译.*词典|"
        r"_百度百科|_百度知道|_搜狗百科|维基百科|"
        r"傻傻分不清楚|的翻译|的用法|的读音|音标|例句|"
        r"wordreference|cambridge|merriam)",
        re.IGNORECASE,
    )

    @classmethod
    def _is_dict_result(cls, item: dict) -> bool:
        """True if this result looks like a dictionary/encyclopedia entry."""
        title = item.get("title", "") or ""
        url = item.get("url", "") or ""
        if cls._DICT_TITLE_RE.search(title):
            return True
        return any(d in url for d in cls._DICT_DOMAINS)

    def _rerank(self, results: list[dict], query: str) -> list[dict]:
        """Lightweight result reranking for better perceived quality.

        Heuristics (each adds/subtracts a score):
          + trusted news/official domain  → +3
          + title contains a query keyword→ +2
          + snippet contains a recent date (YYYY年 or 20YY) → +1
          - dictionary / encyclopedia entry → -5 (deprioritize, not delete)
        Stable sort preserves original order among equal scores.
        """
        if not results:
            return results
        # Don't rerank if the query itself looks like a definition lookup
        # ("xxx是什么" / "xxx意思") — in that case dictionary results ARE
        # what the user wants.
        if re.search(r"(是什么|什么意思|意思|定义|含义)", query):
            return results

        query_lower = query.lower()
        # Extract CJK chars + latin tokens for keyword matching
        keywords: set[str] = set()
        for w in query_lower.replace("+", " ").split():
            if len(w) > 1:
                keywords.add(w)
            for ch in w:
                if "\u4e00" <= ch <= "\u9fff":
                    keywords.add(ch)
        # Drop common stop chars so they don't over-match
        keywords -= {"的", "了", "在", "是", "和", "与", "最", "新", "看"}

        date_re = re.compile(r"(20\d{2}年|20\d{2}-\d{1,2})")

        def score(item: dict) -> int:
            s = 0
            title = (item.get("title", "") or "").lower()
            url = (item.get("url", "") or "").lower()
            snippet = (item.get("snippet", "") or "").lower()
            text = f"{title} {url} {snippet}"
            if any(d in url for d in self._TRUSTED_DOMAINS):
                s += 3
            if any(k in text for k in keywords):
                s += 2
            if date_re.search(snippet):
                s += 1
            if self._is_dict_result(item):
                s -= 5
            return s

        # Stable sort by descending score (Python's sort is stable)
        return sorted(results, key=score, reverse=True)

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

    # Class-level singleton for the visitproject subprocess.
    _visitproject_client: Any = None
    _visitproject_lock = __import__('threading').Lock()
    _visitproject_env: dict[str, str] | None = None
    # BUG-FIX: circuit breaker. visitproject's MCP subprocess startup is
    # unreliable on some machines (15s timeout per attempt). Without a
    # breaker, every web_search call burned 15s retrying before falling
    # through to Bing. After 1 consecutive failure we mark the engine
    # "dead" for the rest of the process and skip it instantly. (Set to
    # 1 because visitproject either works reliably or is broken — there's
    # no value in retrying a 15s-timeout subprocess mid-conversation.)
    _visitproject_fail_count: int = 0
    _visitproject_dead: bool = False
    _VISITPROJECT_MAX_FAILURES = 1

    def _search_visitproject(self, query: str, max_results: int) -> list[dict[str, str]]:
        """Search via visitproject (agentic MCP server — best quality).

        Thread-safe singleton with crash recovery: if the subprocess
        dies or a call fails, the singleton is reset so the next call
        re-spawns a fresh subprocess. A 15s timeout keeps the agent
        loop responsive.
        """
        import atexit
        import os
        import threading
        from .mcp import MCPClient

        bin_path = os.environ.get("VISITPROJECT_BIN", "").strip()
        if not bin_path:
            return []

        cls = self.__class__
        # Circuit breaker: if visitproject has failed too many times, skip
        # it instantly for the rest of the process. Avoids re-burning 15s
        # on every web_search call when the subprocess is broken.
        if cls._visitproject_dead:
            return []

        # Build subprocess env once (cached on class).
        if cls._visitproject_env is None:
            sub_env = dict(os.environ)
            for k, v in os.environ.items():
                if k.startswith("VISITPROJECT_") and k != "VISITPROJECT_BIN":
                    sub_env[k[len("VISITPROJECT_"):]] = v
            cls._visitproject_env = sub_env

        # Thread-safe singleton creation.
        with cls._visitproject_lock:
            if cls._visitproject_client is None:
                try:
                    client = MCPClient(
                        command=["node", bin_path],
                        env=cls._visitproject_env,
                        timeout_s=15.0,
                    )
                    client.connect()
                    atexit.register(client.close)
                    cls._visitproject_client = client
                except Exception as e:
                    logger.warning("visitproject connect failed: %s", e)
                    cls._visitproject_fail_count += 1
                    if cls._visitproject_fail_count >= cls._VISITPROJECT_MAX_FAILURES:
                        cls._visitproject_dead = True
                        logger.warning(
                            "visitproject marked DEAD after %d failures; "
                            "skipping for rest of process",
                            cls._visitproject_fail_count,
                        )
                    return []

        # Call search — if it fails, reset singleton for next-call retry.
        try:
            result = cls._visitproject_client.call_tool("search", {
                "query": query,
                "max_results": max_results,
                "depth": os.environ.get("VISITPROJECT_DEPTH", "quick"),
            })
        except Exception as e:
            logger.warning("visitproject call failed, resetting singleton: %s", e)
            try:
                cls._visitproject_client.close()
            except Exception:
                pass
            cls._visitproject_client = None
            cls._visitproject_fail_count += 1
            if cls._visitproject_fail_count >= cls._VISITPROJECT_MAX_FAILURES:
                cls._visitproject_dead = True
                logger.warning(
                    "visitproject marked DEAD after %d failures; "
                    "skipping for rest of process",
                    cls._visitproject_fail_count,
                )
            return []

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
        to the query (not dictionary entries or unrelated content).

        BUG-FIX (P0): the previous version only checked whole "words"
        (whitespace-split chunks with len > 2). For Chinese queries like
        "台风的最新动态" that's a single chunk, so even when Bing returns
        titles like "实时台风消息" that ARE about typhoons, the filter saw
        "台风的最新动态" not present → returned False → Bing results got
        thrown away, falling through to DDG/playwright, and ultimately
        surfacing "搜索引擎不可用" to the user.

        Now we also extract individual Chinese characters from the query
        (CJK characters are treated as their own "words"). For "台风的
        最新动态" we extract ['台', '风', '的', '新', '态', '动'] and check
        for character overlap with titles/snippets. Mixed Chinese+English
        queries work too.
        """
        if not results:
            return False
        # If the first result's title is just a domain name, it's
        # likely the display-URL parsing bug, not a real result.
        first_title = results[0].get("title", "")
        if first_title.startswith("http") or "." in first_title.split()[0:1][0] if first_title.split() else False:
            return False
        # Build query tokens:
        #   - whitespace-separated chunks (handles English + CJK phrases)
        #   - each individual CJK character (handles queries like
        #     "台风的最新动态" where Bing returns titles with overlapping
        #     but non-identical characters like "实时台风消息")
        query_words: list[str] = []
        for w in query.replace("+", " ").split():
            w = w.strip().lower()
            if len(w) > 1:
                query_words.append(w)
            for ch in w:
                # CJK Unified Ideographs (basic block + extensions)
                if "\u4e00" <= ch <= "\u9fff":
                    query_words.append(ch)
        # Drop noise tokens (single Latin letters, digits-only, punctuation)
        query_words = [w for w in query_words if len(w) >= 1 and w not in {"的", "了", "在", "是", "和", "与"}]
        if not query_words:
            return True
        # At least one query word should appear in titles or snippets
        all_text = " ".join(r.get("title", "") + r.get("snippet", "") for r in results).lower()
        matches = sum(1 for w in query_words if w in all_text)
        return matches >= max(1, len(query_words) // 4)

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
            return {"error": "missing 'url' parameter", "success": False}

        if not url.startswith(("http://", "https://")):
            return {"error": f"URL must start with http:// or https:// (got: {url[:50]})", "success": False}

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

            # BUG-FIX: detect JS-rendered SPA shells. Sites like
            # typhoon.nmc.cn return a near-empty HTML skeleton whose real
            # content is injected by JavaScript at runtime. After our
            # tag-stripping the "text" is mostly whitespace + boilerplate.
            # If the meaningful content is too thin, tell the model clearly
            # so it falls back to search snippets instead of hallucinating
            # "I couldn't find data" from the noise.
            meaningful = re.sub(r"\s+", "", text)
            if content_type == "html" and len(meaningful) < 200:
                spa_hint = (
                    f"[本页内容过少 ({len(meaningful)} 字符)，可能是 JavaScript 动态渲染的 SPA 页面，"
                    f"无法直接抓取实时数据。请改用 web_search 查找该主题的摘要，"
                    f"或引导用户访问该页面获取实时信息。URL: {url}]"
                )
                logger.info("web_fetch '%s': SPA shell detected (%d meaningful chars)", url, len(meaningful))
                return {
                    "url": url,
                    "content": spa_hint,
                    "chars": len(spa_hint),
                    "truncated": False,
                    "content_type": "spa_shell",
                    "success": True,
                    "is_spa": True,
                }

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
                "success": True,
            }
        except Exception as e:
            logger.warning("web_fetch '%s' failed: %s", url, e)
            return {"error": f"{type(e).__name__}: {e}", "success": False}

    @staticmethod
    def _html_to_text(html: str) -> str:
        """Minimal HTML → text converter.

        Removes scripts, styles, tags. Collapses whitespace.
        Not a full parser — good enough for article reading.

        BUG-FIX: added extraction priority for <article>/<main>/<body>
        content regions, and aggressive removal of nav/header/footer/
        boilerplate so article text surfaces above site chrome.
        """
        # Remove script and style blocks (and their content)
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<noscript[^>]*>.*?</noscript>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)

        # Try to extract the main content region first — this avoids
        # nav menus / cookie banners / footer boilerplate dominating the
        # output. Priority: article > main > role=main > common content
        # container names (covers CCTV's content_area, WordPress .entry,
        # Medium, news templates).
        main_html = ""
        for pattern in (
            r"<article[^>]*>(.*?)</article>",
            r"<main[^>]*>(.*?)</main>",
            r'<[^>]+role=["\']main["\'][^>]*>(.*?)</',
            # id/class containing content-area / content_area / entry-content /
            # post-content / article-body — common across news sites
            r'<div[^>]+(?:id|class)=["\'][^"\']*(?:content_area|content-area|entry-content|post-content|article-body|cnt_bd|cont_txt)[^"\']*["\'][^>]*>(.*?)</div>\s*(?:<div[^>]+(?:id|class)=["\'][^"\']*(?:editor|share|comment|related)|$)',
            r'<div[^>]+(?:id|class)=["\'](?:content|main|article|post)[^"\']*["\'][^>]*>(.*?)</div>',
        ):
            m = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
            if m:
                main_html = m.group(1)
                # Sanity check: if the extracted region is suspiciously
                # short, it's probably a misfire (e.g. an empty content
                # div that gets filled by JS). Fall through to full-doc.
                if len(re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", main_html))) > 100:
                    break
                main_html = ""
        if main_html:
            # Strip nav/header/footer/aside from within the main region
            for tag in ("nav", "header", "footer", "aside", "form"):
                main_html = re.sub(
                    rf"<{tag}[^>]*>.*?</{tag}>", "", main_html,
                    flags=re.DOTALL | re.IGNORECASE,
                )
            html = main_html

        # Remove nav/header/footer from the whole doc too (helps when no
        # main region matched)
        for tag in ("nav", "header", "footer", "aside"):
            html = re.sub(rf"<{tag}[^>]*>.*?</{tag}>", "", html, flags=re.DOTALL | re.IGNORECASE)

        # Convert common block elements to newlines
        html = re.sub(r"<(?:p|div|br|h[1-6]|li|tr|td|th)[^>]*>", "\n", html, flags=re.IGNORECASE)

        # Strip all remaining tags
        text = re.sub(r"<[^>]+>", "", html)

        # Decode common HTML entities
        entities = {
            "&amp;": "&", "&lt;": "<", "&gt;": ">",
            "&quot;": '"', "&#39;": "'", "&nbsp;": " ",
            "&hellip;": "...", "&mdash;": "—", "&ndash;": "–",
            "&ensp;": " ", "&emsp;": " ", "&middot;": "·",
        }
        for entity, char in entities.items():
            text = text.replace(entity, char)
        # Numeric entities &#0183; etc.
        text = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))) if int(m.group(1)) < 0x10000 else "", text)

        # Collapse whitespace
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\r\n", "\n", text)
        text = re.sub(r"\n[ \t]+", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Drop lines that are only whitespace/punctuation noise (common
        # in news templates that have dozens of empty spacer rows)
        lines = [ln.strip() for ln in text.split("\n")]
        lines = [ln for ln in lines if ln and ln not in {">", "|", "·", "-"}]
        text = "\n".join(lines)

        return text.strip()



__all__ = ["WebSearchTool", "WebFetchTool"]
