# Multi-LLM Harness

MadCop talks to many "OpenAI-compatible" endpoints. They are **not** identical.
`madcop/llm/harness.py` encodes the differences so chat/agent code stays vendor-agnostic.

## What the harness adapts

| Concern | Examples |
|---|---|
| Max tokens field | `max_tokens` vs `max_completion_tokens` (o1/o3/gpt-5) |
| Temperature / top_p | Disabled on many reasoning models |
| Reasoning controls | `reasoning_effort`, DeepSeek `thinking`, MiniMax flags |
| Extra headers | Anthropic-compatible gateways (`anthropic-version`) |
| Parallel tools | Disabled for flaky GLM proxies |
| Context window hints | UI budget + compaction |

## How resolution works

```python
from madcop.llm.harness import resolve_harness

h = resolve_harness(
    model="o3-mini",
    api_format="openai_chat",      # from provider settings
    runtime_kind="",               # e.g. anthropic_compatible
    base_url="https://api.openai.com/v1",
    preset_id="openai",
)
```

Priority: **api_format / runtime_kind** → **model id regex** → **URL / preset** → default.

## Wiring

1. UI saves `api_format`, `auth_strategy`, `runtime_kind`, sampling on each provider.
2. `get_active_client_config()` returns those fields with the API key.
3. `OpenAICompatClient(...)` builds a harness and uses `harness.build_chat_kwargs()` for chat + stream.
4. Agent modes (quick/standard/deep) keep calling the same client interface.

## Adding a new vendor

1. Add a `ProviderHarness(...)` constant in `harness.py`.
2. Extend `resolve_harness()` detection (model / URL / preset).
3. Add a unit test in `tests/test_llm_harness.py`.
4. Optionally add a preset row in `settings.PROVIDER_PRESETS`.

## Operational tips

- Prefer setting **api_format** in Settings when a proxy is Anthropic-shaped.
- For o-series, leave temperature empty — harness drops it automatically.
- Per-model overrides live in `model_params` on the provider.
