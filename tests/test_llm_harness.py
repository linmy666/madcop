"""Tests for multi-LLM harness profiles."""

from __future__ import annotations

from madcop.llm.harness import ProviderHarness, infer_context_window, resolve_harness


def test_resolve_openai_reasoning_by_model():
    h = resolve_harness(model="o3-mini")
    assert h.max_tokens_field == "max_completion_tokens"
    assert h.supports_temperature is False
    assert h.reasoning_mode == "openai_effort"


def test_resolve_deepseek_by_url():
    h = resolve_harness(model="deepseek-chat", base_url="https://api.deepseek.com/v1")
    assert h.reasoning_mode == "deepseek_thinking"


def test_resolve_anthropic_by_format():
    h = resolve_harness(model="claude-sonnet-4", api_format="anthropic")
    assert h.name == "anthropic_compatible"
    assert "anthropic-version" in h.extra_headers


def test_resolve_minimax():
    h = resolve_harness(model="minimaxai/minimax-m2.7", preset_id="minimax")
    assert h.reasoning_mode == "minimax"


def test_build_chat_kwargs_drops_temperature_for_o1():
    h = resolve_harness(model="o1-preview")
    kw = h.build_chat_kwargs(
        model="o1-preview",
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.7,
        max_tokens=1024,
        tools=None,
        tool_choice=None,
        top_p=0.9,
        effort="high",
        stream=False,
    )
    assert "temperature" not in kw
    assert "top_p" not in kw
    assert kw["max_completion_tokens"] == 1024
    assert kw.get("extra_body", {}).get("reasoning_effort") == "high"


def test_build_chat_kwargs_standard_openai():
    h = resolve_harness(model="gpt-4o-mini")
    kw = h.build_chat_kwargs(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.2,
        max_tokens=512,
        tools=[{"type": "function", "function": {"name": "x"}}],
        tool_choice="auto",
        top_p=None,
        effort=None,
        stream=True,
    )
    assert kw["temperature"] == 0.2
    assert kw["max_tokens"] == 512
    assert kw["stream"] is True
    assert "tools" in kw


def test_infer_context_window():
    assert infer_context_window("gpt-4o") == 128_000
    assert infer_context_window("claude-sonnet-4") == 200_000
    assert infer_context_window("totally-unknown-xyz") == 128_000


def test_harness_extra_body_deepseek():
    h = resolve_harness(model="deepseek-r1")
    body = h._reasoning_extra_body("high", "deepseek-r1")
    assert body is not None
    assert "thinking" in body
