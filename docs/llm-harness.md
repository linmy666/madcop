# Multi-LLM Harness

MadCop talks to many LLM endpoints. They are **not** identical.
This stack adapts per vendor so chat and agent code stay vendor-agnostic.

## Modules

| File | Role |
|---|---|
| `harness.py` | Profiles (max_tokens field, temperature, reasoning body, headers) |
| `factory.py` | `build_client_from_config` / `merge_agent_routing` |
| `anthropic_client.py` | **Native** Anthropic Messages API (`/v1/messages`) |
| `client.py` | OpenAI-compatible SDK wrapper + retry on chat |
| `retry.py` | Exponential backoff on 429/5xx/timeout |
| `capabilities.py` | Heuristic capability cache + image block builders |
| `multimodal.py` | `user_message_with_images` helper |

## Resolution

```python
from madcop.llm.factory import build_client_from_config
from madcop.llm.harness import resolve_harness

# From settings (active provider)
client = build_client_from_config(cfg)

# Per deep-mode agent
from madcop.llm.factory import merge_agent_routing
agent_cfg = merge_agent_routing(cfg, routing, "planner")
agent_client = build_client_from_config(agent_cfg)
```

Priority for harness: **api_format / runtime_kind** → **model id** → **URL / preset** → default.

| Profile | When |
|---|---|
| `openai_reasoning` | o1 / o3 / gpt-5 |
| `deepseek` | model/url contains deepseek |
| `anthropic_compatible` | Claude over OpenAI-shaped proxy |
| **Native Anthropic** | `api_format=anthropic` + anthropic.com (or empty base) |
| `minimax` / `glm` / `qwen` | name heuristics |

## Anthropic

- Settings: **API format = anthropic**, base URL empty or `https://api.anthropic.com`
- Client uses `x-api-key` + `anthropic-version`, system prompt separated, tools as `input_schema`
- Streaming: SSE `content_block_delta` / `tool_use`

## Per-agent routing (deep mode)

`settings.agent_routing`:

```json
{
  "planner": { "model": "o3-mini", "temperature": 0.2 },
  "coder": { "model": "gpt-4o", "max_tokens": 8192 }
}
```

`build_engine()` applies overrides and builds per-agent clients via `merge_agent_routing`.

## Multimodal

```python
from madcop.llm.multimodal import user_message_with_images
msg = user_message_with_images(
    "describe",
    [{"data_url": "data:image/png;base64,..."}],
    api_format="openai_chat",  # or "anthropic"
)
```

## Capabilities cache

`detect_capabilities(model=..., base_url=..., api_format=...)` writes
`~/.madcop/provider_capabilities.json` (1 week TTL). Heuristic only (no token burn).

## Adding a vendor

1. Add `ProviderHarness` in `harness.py` if OpenAI-shaped.
2. Or add a native client + branch in `factory.py`.
3. Unit tests in `tests/test_llm_harness.py` / `tests/test_llm_factory_retry.py`.
4. Optional preset in `settings.PROVIDER_PRESETS`.

## Ops tips

- o-series: leave temperature empty — harness drops it.
- Anthropic official: set `api_format=anthropic`.
- Claude via OpenAI proxy: `openai_chat` + anthropic-compatible headers (auto by model/url).
