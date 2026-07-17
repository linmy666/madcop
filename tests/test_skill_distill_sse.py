"""Skill distill helpers + SSE event shape (no live LLM)."""
from __future__ import annotations

from madcop.memory.skill_distill import (
    _looks_like_teaching_request,
    distill_skill_from_exchange,
    force_distill_skill,
)


def test_looks_like_teaching_zh():
    assert _looks_like_teaching_request("教我怎么部署 FastAPI") is not None
    assert _looks_like_teaching_request("你好") is None


def test_looks_like_teaching_en():
    assert _looks_like_teaching_request("how do I deploy a FastAPI app?") is not None


def test_force_distill_writes_skill(tmp_path, monkeypatch):
    from madcop.memory import skill_distill as sd
    monkeypatch.setattr(sd, "USER_SKILLS_DIR", tmp_path)
    name = force_distill_skill(
        "deploy fastapi",
        "how do I deploy FastAPI?",
        "Use uvicorn and a Dockerfile. " * 5,
    )
    assert name
    files = list(tmp_path.glob("*.md"))
    assert files


def test_distill_from_exchange_requires_teaching_shape(tmp_path, monkeypatch):
    from madcop.memory import skill_distill as sd
    monkeypatch.setattr(sd, "USER_SKILLS_DIR", tmp_path)
    assert distill_skill_from_exchange("hello", "a" * 100) is None
    name = distill_skill_from_exchange(
        "教我如何写 pytest 测试",
        "Use fixtures and assert. " * 10,
    )
    assert name
