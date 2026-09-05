"""v1.6.0 — Tests for web search/fetch tools."""
from __future__ import annotations

import json
import pytest
from unittest.mock import patch, MagicMock

from madcop.tools.web import WebSearchTool, WebFetchTool, _http_get


# --------------------------------------------------------------------------- #
# WebSearchTool
# --------------------------------------------------------------------------- #


class TestWebSearchTool:
    def test_schema(self):
        tool = WebSearchTool()
        assert tool.name == "web_search"
        schema = tool.parameters_schema
        assert "query" in schema["properties"]
        assert "query" in schema["required"]

    def test_empty_query_returns_empty(self):
        tool = WebSearchTool()
        result = tool(query="")
        assert result == []

    def test_search_returns_results_with_mock(self):
        """Mock the HTTP call and verify parsing."""
        mock_html = """
        <a rel="nofollow" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpage" class='result-link'>Example Page</a>
        <td class='result-snippet'>This is a snippet about example content.</td>
        <a rel="nofollow" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Ftest.org" class='result-link'>Test Site</a>
        <td class='result-snippet'>Another snippet here.</td>
        """
        tool = WebSearchTool()
        with patch("madcop.tools.web._http_get", return_value=mock_html.encode()):
            results = tool(query="test query", max_results=5)

        assert len(results) == 2
        assert {item["title"] for item in results} == {"Example Page", "Test Site"}
        assert any("example.com" in item["url"] for item in results)
        assert any("snippet" in item["snippet"].lower() for item in results)

    def test_search_uses_youcom_when_key_set(self, monkeypatch):
        monkeypatch.setenv("YDC_API_KEY", "youcom-test-key")
        tool = WebSearchTool()
        captured: list[tuple[str, dict, dict | None]] = []

        def fake_post_json(url, payload, timeout=10, headers=None):
            captured.append((url, payload, headers))
            return json.dumps(
                {
                    "results": {
                        "web": [
                            {
                                "title": "You Result",
                                "url": "https://example.com",
                                "description": "You.com snippet",
                                "snippets": ["snippet one", "snippet two"],
                            }
                        ],
                        "news": [
                            {
                                "title": "News Result",
                                "url": "https://news.example.com",
                                "description": "News description",
                            }
                        ],
                    }
                }
            ).encode()

        with patch("madcop.tools.web._http_post_json", side_effect=fake_post_json), \
             patch("madcop.tools.web.WebSearchTool._search_bing",
                   side_effect=Exception("bing should not run")), \
             patch("madcop.tools.web.WebSearchTool._search_ddg",
                   side_effect=Exception("ddg should not run")), \
             patch("madcop.tools.web.WebSearchTool._search_baidu_playwright",
                   side_effect=Exception("baidu should not run")):
            results = tool(query="latest news", max_results=5)

        assert len(captured) == 1
        assert captured[0][0] == "https://ydc-index.io/v1/search"
        assert captured[0][2]["X-API-Key"] == "youcom-test-key"
        assert {item["title"] for item in results} == {"You Result", "News Result"}
        assert any(item["url"] == "https://example.com" for item in results)

    def test_search_falls_back_when_youcom_fails(self, monkeypatch):
        monkeypatch.setenv("YDC_API_KEY", "youcom-test-key")
        tool = WebSearchTool()

        with patch("madcop.tools.web._http_post_json", side_effect=Exception("youcom down")), \
             patch("madcop.tools.web.WebSearchTool._search_bing",
                   return_value=[{"title": "Fallback Please Result", "url": "https://bing.example.com", "snippet": "fallback please snippet"}]), \
             patch("madcop.tools.web.WebSearchTool._search_ddg",
                   side_effect=Exception("ddg should not run")), \
             patch("madcop.tools.web.WebSearchTool._search_baidu_playwright",
                   side_effect=Exception("baidu should not run")):
            results = tool(query="fallback please", max_results=5)

        assert len(results) == 1
        assert results[0]["title"] == "Fallback Please Result"

    def test_search_error_returns_error_dict(self):
        tool = WebSearchTool()
        # v3.12 — patch all engines so _http_get exception bubbles
        # through and triggers the LLM-knowledge fallback (which
        # returns the single {"error": "..."} dict).
        with patch("madcop.tools.web._http_get", side_effect=Exception("Network down")), \
             patch("madcop.tools.web.WebSearchTool._search_baidu_playwright",
                   side_effect=Exception("playwright not installed in test env")), \
             patch("madcop.tools.web.WebSearchTool._search_bing",
                   side_effect=Exception("bing not mocked in test env")):
            results = tool(query="test")
        assert len(results) == 1
        assert "error" in results[0]

    def test_max_results_respected(self):
        """Build 10 fake results, ask for 3."""
        blocks = ""
        for i in range(10):
            # v3.12 — the relevance check (added later) requires
            # at least one query word in titles or snippets. Embed
            # 'test' so the mock results pass the heuristic. Use
            # single quotes for class names to match DDG's actual
            # HTML format (the parser's regex looks for class='…').
            # We avoid f-strings here because in f"..." the escape
            # sequence \' renders as a literal backslash + apostrophe,
            # which breaks the regex match.
            blocks += (
                '<a rel="nofollow" href="//duckduckgo.com/l/?uddg=https://r'
                + str(i) + '.com" class=\'result-link\'>test result '
                + str(i) + '</a><td class=\'result-snippet\'>Snippet '
                + str(i) + ' about test</td>'
            )
        tool = WebSearchTool()
        # v3.12 — WebSearchTool now runs Baidu (Playwright) → Bing
        # → DDG in order. The test was originally written against
        # the DDG-only path, so force the upstream engines to raise
        # and fall through to the only strategy that uses
        # _http_get (DDG). This keeps the test fast and offline.
        with patch("madcop.tools.web._http_get", return_value=blocks.encode()), \
             patch("madcop.tools.web.WebSearchTool._search_baidu_playwright",
                   side_effect=Exception("playwright not installed in test env")), \
             patch("madcop.tools.web.WebSearchTool._search_bing",
                   side_effect=Exception("bing not mocked in test env")):
            results = tool(query="test", max_results=3)
        assert len(results) == 3

    def test_openai_schema(self):
        tool = WebSearchTool()
        schema = tool.to_openai_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "web_search"

    def test_visitproject_strategy_when_bin_env_set(self, monkeypatch):
        """If VISITPROJECT_BIN is set, WebSearchTool should route the
        query through visitproject (an MCP subprocess) instead of
        the bing/ddg path. Mock MCPClient so the test doesn't need
        the real binary."""
        import json as _json

        # Reset the class-level singleton so the test starts clean.
        WebSearchTool._visitproject_client = None

        monkeypatch.setenv("VISITPROJECT_BIN", "/fake/path/to/visitproject/dist/index.js")
        # Disable upstream engines so the test never hits the network.
        monkeypatch.delenv("SEARXNG_URL", raising=False)
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)

        # Stub MCPClient: every instance returns the same fake
        # search result list. Use a small fake response matching
        # visitproject's actual JSON shape.
        call_log = []
        class FakeClient:
            def __init__(self, *args, **kwargs): pass
            def connect(self): pass
            def close(self): pass
            def call_tool(self, name, arguments):
                call_log.append((name, arguments))
                assert name == "search"
                assert arguments["query"] == "real query"
                # visitproject's response shape: dict with content
                # list of {type: text, text: JSON-string}.
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": _json.dumps({
                                "results": [
                                    {"title": "Result 1",
                                     "url": "https://r1.com",
                                     "snippet": "snippet one"},
                                    {"title": "Result 2",
                                     "url": "https://r2.com",
                                     "snippet": "snippet two"},
                                ],
                            }),
                        }
                    ]
                }

        tool = WebSearchTool()
        # The _search_visitproject method imports MCPClient from
        # madcop.tools.mcp lazily; patching that module attribute
        # replaces it for the import.
        with patch("madcop.tools.mcp.MCPClient", FakeClient):
            results = tool(query="real query", max_results=5)

        # Verify MCPClient.call_tool was actually invoked.
        assert len(call_log) == 1
        # The visitproject response had 2 items; both should be
        # returned (and the upstream engines never called).
        assert len(results) == 2
        assert results[0]["title"] == "Result 1"
        assert results[1]["url"] == "https://r2.com"
        # Clean up the singleton so other tests start fresh.
        WebSearchTool._visitproject_client = None

    def test_visitproject_strategy_skipped_when_bin_unset(self, monkeypatch):
        """If VISITPROJECT_BIN is not set, the strategy must be
        skipped and the tool falls through to its normal pipeline."""
        WebSearchTool._visitproject_client = None
        monkeypatch.delenv("VISITPROJECT_BIN", raising=False)

        tool = WebSearchTool()
        # The upstream engines will all raise (because we mock them),
        # so the tool falls all the way to the LLM-knowledge fallback.
        with patch("madcop.tools.web.WebSearchTool._search_baidu_playwright",
                   side_effect=Exception("no playwright")), \
             patch("madcop.tools.web.WebSearchTool._search_bing",
                   side_effect=Exception("no bing")), \
             patch("madcop.tools.web.WebSearchTool._search_ddg",
                   side_effect=Exception("no ddg")):
            results = tool(query="anything")
        assert len(results) == 1
        assert "error" in results[0]
        WebSearchTool._visitproject_client = None


# --------------------------------------------------------------------------- #
# WebFetchTool
# --------------------------------------------------------------------------- #


class TestWebFetchTool:
    def test_schema(self):
        tool = WebFetchTool()
        assert tool.name == "web_fetch"
        schema = tool.parameters_schema
        assert "url" in schema["required"]

    def test_missing_url(self):
        tool = WebFetchTool()
        result = tool()
        assert "error" in result

    def test_invalid_url(self):
        tool = WebFetchTool()
        result = tool(url="not-a-url")
        assert "error" in result
        assert "http" in result["error"].lower()

    def test_fetch_html_with_mock(self):
        mock_html = """
        <html><head><script>bad()</script><style>body{}</style></head>
        <body><h1>Hello World</h1>
        <p>This is a test page with enough content to avoid the SPA detector. It includes several sentences so the
        stripped text remains well above the fallback threshold.</p>
        <p>Another paragraph keeps the meaningful text above the fallback threshold, and a third sentence makes the
        example behave like a normal article instead of a JS shell.</p>
        <p>Final paragraph with extra words for good measure.</p></body></html>
        """
        tool = WebFetchTool()
        with patch("madcop.tools.web._http_get", return_value=mock_html.encode()):
            result = tool(url="https://example.com/page")
        assert result.get("url") == "https://example.com/page"
        assert "Hello World" in result["content"]
        assert "This is a test page" in result["content"]
        # Script and style should be stripped
        assert "bad()" not in result["content"]
        assert "body{}" not in result["content"]

    def test_fetch_truncation(self):
        long_text = "x" * 10000
        mock_html = f"<html><body>{long_text}</body></html>"
        tool = WebFetchTool()
        with patch("madcop.tools.web._http_get", return_value=mock_html.encode()):
            result = tool(url="https://example.com", max_chars=100)
        assert result["truncated"] is True
        assert len(result["content"]) <= 100

    def test_fetch_text_file(self):
        tool = WebFetchTool()
        with patch("madcop.tools.web._http_get", return_value=b"plain text content"):
            result = tool(url="https://example.com/file.txt")
        assert result["content"] == "plain text content"
        assert result["content_type"] == "text"

    def test_fetch_json_file(self):
        tool = WebFetchTool()
        with patch("madcop.tools.web._http_get", return_value=b'{"key": "value"}'):
            result = tool(url="https://example.com/data.json")
        assert "key" in result["content"]
        assert "value" in result["content"]

    def test_fetch_error(self):
        tool = WebFetchTool()
        with patch("madcop.tools.web._http_get", side_effect=Exception("404")):
            result = tool(url="https://example.com/missing")
        assert "error" in result

    def test_html_to_text_strips_tags(self):
        html = "<p>Hello</p><b>World</b><br/><div>Test</div>"
        text = WebFetchTool._html_to_text(html)
        assert "Hello" in text
        assert "World" in text
        assert "Test" in text
        assert "<p>" not in text

    def test_html_entity_decode(self):
        html = "<p>Tom &amp; Jerry &lt;cartoon&gt;</p>"
        text = WebFetchTool._html_to_text(html)
        assert "Tom & Jerry" in text
        assert "<cartoon>" in text
