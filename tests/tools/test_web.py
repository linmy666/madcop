"""v1.6.0 — Tests for web search/fetch tools."""
from __future__ import annotations

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
        <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpage">
          Example Page
        </a>
        <a class="result__snippet" href="#">This is a snippet about example content.</a>
        <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Ftest.org">
          Test Site
        </a>
        <a class="result__snippet" href="#">Another snippet here.</a>
        """
        tool = WebSearchTool()
        with patch("madcop.tools.web._http_get", return_value=mock_html.encode()):
            results = tool(query="test query", max_results=5)

        assert len(results) == 2
        assert results[0]["title"] == "Example Page"
        assert "example.com" in results[0]["url"]
        assert "snippet" in results[0]["snippet"].lower()

    def test_search_error_returns_error_dict(self):
        tool = WebSearchTool()
        with patch("madcop.tools.web._http_get", side_effect=Exception("Network down")):
            results = tool(query="test")
        assert len(results) == 1
        assert "error" in results[0]

    def test_max_results_respected(self):
        """Build 10 fake results, ask for 3."""
        blocks = ""
        for i in range(10):
            blocks += f'''<a class="result__a" href="//duckduckgo.com/l/?uddg=https://r{i}.com">Result {i}</a><a class="result__snippet">Snippet {i}</a>'''
        tool = WebSearchTool()
        with patch("madcop.tools.web._http_get", return_value=blocks.encode()):
            results = tool(query="test", max_results=3)
        assert len(results) == 3

    def test_openai_schema(self):
        tool = WebSearchTool()
        schema = tool.to_openai_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "web_search"


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
        <body><h1>Hello World</h1><p>This is a test page.</p></body></html>
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
