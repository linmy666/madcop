"""
End-to-end test for Phase 4: plugin registration.

Verifies that:
  1. register_browser_plugins adds 3 plugins in one call.
  2. The schemas are valid OpenAI function-calling JSON (required
     field, type=object, etc.).
  3. Each plugin runs through the unified ToolExecutor pipeline
     (validate → HITL → timeout → format).
  4. The default registry exposes the new plugins to the engine.

Run:
  cd /Users/linruihan/PycharmProjects/madcop
  python3 -m pytest tests/test_plugins_browser.py -v
or
  python3 tests/test_plugins_browser.py
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from madcop.agent.tool_executor import (
    PluginRegistry,
    ToolExecutor,
    build_default_registry,
)
from madcop.agent.plugins_browser import register_browser_plugins


def _expect(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


# ─── tests ──────────────────────────────────────────────────────────────────


def test_register_browser_plugins_adds_three() -> None:
    reg = PluginRegistry()
    n = register_browser_plugins(reg)
    _expect(n == 3, f"expected 3 plugins registered, got {n}")
    names = set(reg.names())
    _expect(
        {"browser_navigate", "browser_screenshot", "computer_screenshot"}
        <= names,
        f"missing plugins: {names}",
    )
    print(f"  ✓ test_register_browser_plugins_adds_three (names={sorted(names)})")


def test_schemas_are_openai_function_shape() -> None:
    reg = PluginRegistry()
    register_browser_plugins(reg)
    schemas = reg.get_all_schemas()
    _expect(len(schemas) == 3, f"expected 3 schemas, got {len(schemas)}")
    for s in schemas:
        _expect(s["type"] == "function", f"missing type=function: {s}")
        fn = s["function"]
        _expect(fn["name"], f"missing name: {fn}")
        _expect(fn["description"], f"missing description: {fn}")
        params = fn["parameters"]
        _expect(params["type"] == "object", f"bad params: {params}")
        _expect("properties" in params, f"missing properties: {params}")
    print("  ✓ test_schemas_are_openai_function_shape")


def test_browser_navigate_runs_through_pipeline() -> None:
    reg = PluginRegistry()
    register_browser_plugins(reg)
    ex = ToolExecutor(reg)
    r = ex.execute("browser_navigate", {"url": "https://example.com"})
    print(f"  result={r!r}")
    _expect(not r.is_error, f"happy path should not error: {r!r}")
    _expect("https://example.com" in r.content, "url should appear in result")
    print("  ✓ test_browser_navigate_runs_through_pipeline")


def test_browser_navigate_missing_url_validation() -> None:
    reg = PluginRegistry()
    register_browser_plugins(reg)
    ex = ToolExecutor(reg)
    # browser_navigate has no entry in TOOL_SCHEMAS, so Pydantic
    # validation is permissive. The handler itself reports the
    # issue ("missing url") in its returned string — the unified
    # pipeline surfaces it as plain content, not as a structured
    # error. This is correct for unknown tools; in production the
    # stub gets replaced with a Playwright call that raises on
    # bad input, which the pipeline catches as ``[error] ...``.
    r = ex.execute("browser_navigate", {"url": ""})
    _expect(not r.is_error, f"missing-url stub should not raise: {r!r}")
    _expect(not r.is_validation_error, "no schema → no validation_error tag")
    _expect("missing url" in r.content, f"expected handler message: {r!r}")
    print("  ✓ test_browser_navigate_missing_url_validation")


def test_computer_screenshot_runs_through_pipeline() -> None:
    reg = PluginRegistry()
    register_browser_plugins(reg)
    ex = ToolExecutor(reg)
    r = ex.execute("computer_screenshot", {})
    _expect(not r.is_error, f"happy path failed: {r!r}")
    _expect("/madcop_screen.png" in r.content, f"unexpected path: {r.content!r}")
    print(f"  ✓ test_computer_screenshot_runs_through_pipeline -> {r.content!r}")


def test_default_registry_exposes_browser_plugins() -> None:
    """The full default registry (used by /api/v4/chat) should
    include the browser plugins after the build_default_registry
    wiring."""
    reg, _ex = build_default_registry(workspace_dir="/tmp")
    names = set(reg.names())
    expected = {"browser_navigate", "browser_screenshot", "computer_screenshot"}
    missing = expected - names
    _expect(
        not missing,
        f"default registry missing browser plugins: {missing}. "
        f"present plugins: {sorted(names)}",
    )
    # Confirm each schema is callable
    schemas = reg.get_all_schemas()
    for name in expected:
        schema_names = {s["function"]["name"] for s in schemas}
        _expect(name in schema_names, f"{name} missing from schemas")
    print(f"  ✓ test_default_registry_exposes_browser_plugins ({len(schemas)} total schemas)")


# ─── runner ─────────────────────────────────────────────────────────────────


def main() -> int:
    tests = [
        test_register_browser_plugins_adds_three,
        test_schemas_are_openai_function_shape,
        test_browser_navigate_runs_through_pipeline,
        test_browser_navigate_missing_url_validation,
        test_computer_screenshot_runs_through_pipeline,
        test_default_registry_exposes_browser_plugins,
    ]
    passed = 0
    failed = 0
    for t in tests:
        print(f"[{t.__name__}]")
        try:
            t()
            passed += 1
        except Exception:
            failed += 1
            traceback.print_exc()
    print(f"\n=== {passed} passed, {failed} failed ===")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())