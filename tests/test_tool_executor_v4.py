"""
End-to-end tests for v4 unified ToolExecutor.

Exercises the three failure paths the plan calls out:
  1. validation failure (Pydantic schema rejected)
  2. timeout (handler runs past DEFAULT_TIMEOUT_S)
  3. closed-loop error return (error surfaces as Observation prefix
     the LLM can branch on)

Plus a happy path to make sure normal execution still works.

Run with:
  cd /Users/linruihan/PycharmProjects/madcop
  python3 -m pytest tests/test_tool_executor_v4.py -v
or
  python3 tests/test_tool_executor_v4.py
"""

from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

# Make project root importable when run as a script
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from madcop.agent.tool_executor import (
    ToolExecutor,
    ToolPlugin,
    ToolResult,
    PluginRegistry,
    DEFAULT_TIMEOUT_S,
    _ToolTimeout,
)


# ─── helpers ────────────────────────────────────────────────────────────────


def _make_executor(handlers: dict | None = None, timeout_s: int = 2) -> ToolExecutor:
    """Build a minimal executor with the given handlers.

    handlers: {name: callable(**kwargs) -> str | dict}
    """
    reg = PluginRegistry()
    for name, fn in (handlers or {}).items():
        reg.register(
            ToolPlugin(
                name=name,
                handler=fn,
                schema={
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": f"test tool {name}",
                        "parameters": {"type": "object", "properties": {}},
                    },
                },
                danger="safe",
                timeout_s=timeout_s,
            )
        )
    return ToolExecutor(reg)


def _expect(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


# ─── tests ──────────────────────────────────────────────────────────────────


def test_happy_path() -> None:
    """Sync handler returns a string → ToolResult.content set, no flags."""
    def echo(x: str = "hi") -> str:
        return f"echo:{x}"

    ex = _make_executor({"echo": echo})
    r = ex.execute("echo", {"x": "hello"})
    _expect(r.content == "echo:hello", f"expected echo:hello, got {r.content!r}")
    _expect(not r.is_error, "happy path should not be error")
    _expect(not r.is_validation_error, "happy path should not be validation_error")
    _expect(not r.is_timeout, "happy path should not be timeout")
    print("  ✓ test_happy_path")


def test_validation_failure_closed_loop() -> None:
    """write_file with /etc/ path → validation_error tag in observation."""
    ex = _make_executor(
        {"write_file": lambda **_: "should not run"},
        timeout_s=2,
    )
    r = ex.execute(
        "write_file",
        {"path": "/etc/passwd", "content": "pwned"},
    )
    obs = r.to_observation()
    print(f"  observation={obs!r}")
    _expect(r.is_error, "should be is_error")
    _expect(r.is_validation_error, "should be is_validation_error")
    _expect("[validation_error]" in obs, f"missing tag in {obs!r}")
    _expect("write_file" in obs, "should name the tool so LLM can fix args")
    print("  ✓ test_validation_failure_closed_loop")


def test_validation_failure_sudo_blocked() -> None:
    """bash with sudo → validation_error."""
    ex = _make_executor({"bash": lambda **_: "ok"}, timeout_s=2)
    r = ex.execute("bash", {"command": "sudo rm -rf /"})
    _expect(r.is_validation_error, "sudo should trigger validation_error")
    _expect("[validation_error]" in r.to_observation(), "should have tag")
    print("  ✓ test_validation_failure_sudo_blocked")


def test_timeout_enforced() -> None:
    """Handler sleeps 10s with timeout=2s → is_timeout=True, observed."""
    def slow(**_):
        time.sleep(10)
        return "should not see this"

    ex = _make_executor({"slow_tool": slow}, timeout_s=2)
    t0 = time.time()
    r = ex.execute("slow_tool", {})
    elapsed = time.time() - t0
    print(f"  elapsed={elapsed:.2f}s result={r!r}")
    _expect(r.is_error, "should be error")
    _expect(r.is_timeout, "should be is_timeout")
    _expect("[timeout]" in r.to_observation(), "missing [timeout] tag")
    _expect(elapsed < 5, f"timeout should fire in ~2s, took {elapsed:.1f}s")
    print("  ✓ test_timeout_enforced")


def test_unknown_tool_error() -> None:
    """Non-registered tool → ToolResult.error with [error] tag, not validation."""
    ex = _make_executor({"echo": lambda x="hi": f"echo:{x}"})
    r = ex.execute("nonexistent_tool", {"foo": "bar"})
    _expect(r.is_error, "should be error")
    _expect(not r.is_validation_error, "unknown tool is not a validation failure")
    _expect("nonexistent_tool" in r.error, "error should name the tool")
    print("  ✓ test_unknown_tool_error")


def test_dangerous_tool_needs_confirmation() -> None:
    """bash is destructive → needs_confirmation flag, NOT validation_error."""
    ex = _make_executor({"bash": lambda **_: "ok"})
    r = ex.execute("bash", {"command": "ls -la"})
    _expect(r.needs_confirmation, "bash should require confirmation")
    _expect(r.is_error, "should be flagged as error so engine can branch")
    _expect(not r.is_validation_error, "confirmation is not a validation failure")
    _expect("[needs_confirmation]" in r.to_observation(), "missing confirmation tag")
    print("  ✓ test_dangerous_tool_needs_confirmation")


def test_handler_raises_generic_error() -> None:
    """Handler raises → is_error=True, is_timeout=False, [error] tag."""
    def boom(**_):
        raise RuntimeError("kaboom")

    ex = _make_executor({"boom": boom})
    r = ex.execute("boom", {})
    _expect(r.is_error, "should be error")
    _expect(not r.is_timeout, "should NOT be timeout")
    _expect(not r.is_validation_error, "should NOT be validation")
    _expect("kaboom" in r.error, f"error should propagate: {r.error!r}")
    print("  ✓ test_handler_raises_generic_error")


def test_result_dict_with_error_field() -> None:
    """Handler returns {'error': 'msg'} → result.error populated."""
    def partial_fail(**_):
        return {"error": "downstream api 502", "data": None}

    ex = _make_executor({"flaky": partial_fail})
    r = ex.execute("flaky", {})
    _expect(r.is_error, "embedded error should mark is_error")
    _expect("502" in r.error, f"expected error message, got {r.error!r}")
    print("  ✓ test_result_dict_with_error_field")


def test_async_handler() -> None:
    """Async coroutine handler should also work and respect timeout."""
    import asyncio

    async def fast_async(**_):
        await asyncio.sleep(0.05)
        return "async-ok"

    async def slow_async(**_):
        await asyncio.sleep(10)
        return "should not see this"

    reg = PluginRegistry()
    reg.register(
        ToolPlugin(
            name="fast_async",
            handler=fast_async,
            schema={"type": "function", "function": {"name": "fast_async"}},
            timeout_s=2,
        )
    )
    reg.register(
        ToolPlugin(
            name="slow_async",
            handler=slow_async,
            schema={"type": "function", "function": {"name": "slow_async"}},
            timeout_s=1,
        )
    )
    ex = ToolExecutor(reg)

    r1 = ex.execute("fast_async", {})
    _expect(r1.content == "async-ok", f"async happy path failed: {r1!r}")

    t0 = time.time()
    r2 = ex.execute("slow_async", {})
    elapsed = time.time() - t0
    _expect(r2.is_timeout, f"slow async should timeout: {r2!r}")
    _expect(elapsed < 3, f"async timeout should fire in ~1s, took {elapsed:.1f}s")
    print("  ✓ test_async_handler")


# ─── runner ─────────────────────────────────────────────────────────────────


def main() -> int:
    tests = [
        test_happy_path,
        test_validation_failure_closed_loop,
        test_validation_failure_sudo_blocked,
        test_timeout_enforced,
        test_unknown_tool_error,
        test_dangerous_tool_needs_confirmation,
        test_handler_raises_generic_error,
        test_result_dict_with_error_field,
        test_async_handler,
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
    print(f"\n=== {passed} passed, {failed} failed, DEFAULT_TIMEOUT_S={DEFAULT_TIMEOUT_S}s ===")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())