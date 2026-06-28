"""Tests for Flowtrace + Skill auto-sediment systems."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from madcop.agent.trace import (
    TraceNode,
    TraceStore,
    TraceStatus,
    get_trace_store,
    reset_trace_store,
)
from madcop.agent.skill_forge import (
    SkillMeta,
    SkillStore,
    auto_forge_from_conversation,
    get_skill_store,
    reset_skill_store,
)


@pytest.fixture
def trace_store(tmp_path: Path) -> TraceStore:
    s = TraceStore(path=tmp_path / "trace.db")
    yield s
    s.close()


@pytest.fixture
def skill_store(tmp_path: Path) -> SkillStore:
    s = SkillStore(path=tmp_path / "skills")
    yield s


# --------------------------------------------------------------------------- #
# TraceNode
# --------------------------------------------------------------------------- #

def test_trace_node_to_dict():
    n = TraceNode(
        id="abc",
        conversation_id="c1",
        node_type="llm_call",
        label="test",
        status=TraceStatus.DONE,
    )
    d = n.to_dict()
    assert d["id"] == "abc"
    assert d["node_type"] == "llm_call"
    assert d["status"] == "done"


# --------------------------------------------------------------------------- #
# TraceStore CRUD
# --------------------------------------------------------------------------- #

def test_add_and_get(trace_store: TraceStore):
    n = TraceNode(id="n1", conversation_id="c1", node_type="llm_call", label="first")
    trace_store.add(n)
    fetched = trace_store.get("n1")
    assert fetched is not None
    assert fetched.label == "first"
    assert fetched.status == "pending"


def test_mark_running_and_done(trace_store: TraceStore):
    n = TraceNode(id="n2", conversation_id="c1", node_type="tool_call")
    trace_store.add(n)
    trace_store.mark_running("n2")
    assert trace_store.get("n2").status == "running"
    trace_store.mark_done("n2", output="ok")
    assert trace_store.get("n2").status == "done"
    assert trace_store.get("n2").output == "ok"
    assert trace_store.get("n2").completed_at is not None


def test_mark_error(trace_store: TraceStore):
    n = TraceNode(id="n3", conversation_id="c1", node_type="tool_call")
    trace_store.add(n)
    trace_store.mark_error("n3", error="connection failed")
    node = trace_store.get("n3")
    assert node.status == "error"
    assert node.error == "connection failed"


def test_children(trace_store: TraceStore):
    parent = TraceNode(id="p", conversation_id="c1")
    c1 = TraceNode(id="c1", conversation_id="c1", parent_id="p")
    c2 = TraceNode(id="c2", conversation_id="c1", parent_id="p")
    grandchild = TraceNode(id="g1", conversation_id="c1", parent_id="c1")
    for n in [parent, c1, c2, grandchild]:
        trace_store.add(n)
    children = trace_store.get_children("p")
    assert {c.id for c in children} == {"c1", "c2"}
    gc = trace_store.get_children("c1")
    assert {g.id for g in gc} == {"g1"}


def test_conversation_trace(trace_store: TraceStore):
    for i in range(5):
        trace_store.add(TraceNode(id=f"n{i}", conversation_id="c1"))
    trace_store.add(TraceNode(id="x", conversation_id="c2"))
    nodes = trace_store.get_conversation_trace("c1")
    assert len(nodes) == 5


# --------------------------------------------------------------------------- #
# downstream_of / checkpoint / resume
# --------------------------------------------------------------------------- #

def test_downstream_of(trace_store: TraceStore):
    """Build a tree:
        a
       / \
      b   c
     /     \
    d       e
    Test: downstream_of(b) = [d]
    """
    a = TraceNode(id="a", conversation_id="c1")
    b = TraceNode(id="b", conversation_id="c1", parent_id="a")
    c = TraceNode(id="c", conversation_id="c1", parent_id="a")
    d = TraceNode(id="d", conversation_id="c1", parent_id="b")
    e = TraceNode(id="e", conversation_id="c1", parent_id="c")
    for n in [a, b, c, d, e]:
        trace_store.add(n)
    descendants = trace_store.downstream_of("b")
    assert {n.id for n in descendants} == {"d"}


def test_downstream_of_root(trace_store: TraceStore):
    """downstream_of(root) should return ALL descendants."""
    a = TraceNode(id="a", conversation_id="c1")
    b = TraceNode(id="b", conversation_id="c1", parent_id="a")
    c = TraceNode(id="c", conversation_id="c1", parent_id="b")
    for n in [a, b, c]:
        trace_store.add(n)
    descendants = trace_store.downstream_of("a")
    assert {n.id for n in descendants} == {"b", "c"}


def test_reset_downstream(trace_store: TraceStore):
    a = TraceNode(id="a", conversation_id="c1")
    b = TraceNode(id="b", conversation_id="c1", parent_id="a")
    c = TraceNode(id="c", conversation_id="c1", parent_id="b")
    for n in [a, b, c]:
        trace_store.add(n)
    superseded = trace_store.reset_downstream("a")
    assert set(superseded) == {"b", "c"}
    assert trace_store.get("b").status == "superseded"
    assert trace_store.get("c").status == "superseded"
    # a is unchanged
    assert trace_store.get("a").status == "pending"


def test_create_node_with_depth(trace_store: TraceStore):
    root = trace_store.create_node(conversation_id="c1")
    child = trace_store.create_node(conversation_id="c1", parent_id=root.id)
    grandchild = trace_store.create_node(conversation_id="c1", parent_id=child.id)
    assert root.depth == 0
    assert child.depth == 1
    assert grandchild.depth == 2


def test_create_node_with_input_data(trace_store: TraceStore):
    node = trace_store.create_node(
        conversation_id="c1",
        input_data={"foo": "bar", "list": [1, 2, 3]},
    )
    assert '"foo"' in node.input
    assert '"bar"' in node.input


# --------------------------------------------------------------------------- #
# SkillStore
# --------------------------------------------------------------------------- #

def test_skill_create_and_get(skill_store: SkillStore):
    path = skill_store.create_skill(
        name="How to test",
        description="A skill for testing",
        body="# How to test\n\n1. Write tests\n2. Run them\n",
        triggers=["test", "pytest"],
    )
    assert "how-to-test" in path.lower()
    s = skill_store.get_skill("How to test")
    assert s is not None
    assert s["description"] == "A skill for testing"
    assert "test" in s["triggers"]


def test_skill_yaml_format(skill_store: SkillStore):
    """SKILL.md has valid YAML frontmatter + body."""
    path = skill_store.create_skill(
        name="Format test",
        description="Test",
        body="Body content here",
    )
    text = (Path(path) / "SKILL.md").read_text()
    assert text.startswith("---\n")
    assert text.endswith("Body content here")
    assert "name: format-test" in text
    assert "source: manual" in text  # default source is manual
    assert "version: 1.0" in text


def test_skill_list(skill_store: SkillStore):
    skill_store.create_skill(name="Skill 1", description="d1", body="b1")
    skill_store.create_skill(name="Skill 2", description="d2", body="b2")
    skills = skill_store.list_skills()
    assert len(skills) == 2
    names = {s["name"] for s in skills}
    assert "skill-1" in names
    assert "skill-2" in names


def test_skill_search(skill_store: SkillStore):
    skill_store.create_skill(
        name="Python testing",
        description="how to write pytest",
        body="Use pytest",
        triggers=["pytest", "python"],
    )
    skill_store.create_skill(
        name="React testing",
        description="how to use react-testing-library",
        body="Use react testing library",
        triggers=["react"],
    )
    results = skill_store.search_skills("pytest")
    assert len(results) >= 1
    assert any("python-testing" in s["name"] for s in results)


def test_skill_delete(skill_store: SkillStore):
    path = skill_store.create_skill(name="to delete", description="d", body="b")
    assert Path(path).exists()
    assert skill_store.delete_skill("to delete") is True
    assert not Path(path).exists()
    assert skill_store.delete_skill("to delete") is False  # already gone


def test_skill_manual_source(skill_store: SkillStore):
    path = skill_store.create_skill(
        name="manual skill",
        description="d",
        body="b",
        source="manual",
    )
    text = (Path(path) / "SKILL.md").read_text()
    assert "source: manual" in text


# --------------------------------------------------------------------------- #
# Auto-create skill from conversation
# --------------------------------------------------------------------------- #

def test_auto_create_from_how_to(skill_store: SkillStore):
    """User asks a how-to question -> assistant gives steps -> auto create skill."""
    path = auto_forge_from_conversation(
        skill_store,
        user_message="如何写一个 Python 测试函数？",
        assistant_response="""1. 导入 pytest
2. 写 def test_xxx(): pass
3. 运行 pytest

```python
import pytest
def test_example():
    assert 1 + 1 == 2
```
""",
    )
    assert path is not None
    skill = skill_store.get_skill("如何写一个 Python 测试函数？")
    assert skill is not None


def test_auto_create_skip_unrelated(skill_store: SkillStore):
    """User asks 'what time is it' -> no how-to pattern -> no skill."""
    path = auto_forge_from_conversation(
        skill_store,
        user_message="现在几点了？",
        assistant_response="现在是下午 3 点。",
    )
    assert path is None


def test_auto_create_no_duplicate(skill_store: SkillStore):
    """Same user message twice -> second time is skipped."""
    user_msg = "如何部署 Python 应用？"
    assistant = "1. 打包\n2. 上传\n3. 运行"
    p1 = auto_forge_from_conversation(skill_store, user_msg, assistant)
    p2 = auto_forge_from_conversation(skill_store, user_msg, assistant)
    assert p1 is not None
    assert p2 is None  # dedup


# ───────────────────────────────────────────────────────────────────
# Trace Studio — execute_resume_from + execute_get_trace
# ───────────────────────────────────────────────────────────────────

def test_execute_resume_from_supersedes_downstream(trace_store: TraceStore):
    from madcop.agent.trace import execute_resume_from
    a = trace_store.create_node(conversation_id="c1")
    b = trace_store.create_node(conversation_id="c1", parent_id=a.id)
    c = trace_store.create_node(conversation_id="c1", parent_id=b.id)
    result = execute_resume_from(a.id, store=trace_store)
    assert "Superseded" in result
    assert "2" in result
    assert trace_store.get(b.id).status == "superseded"
    assert trace_store.get(c.id).status == "superseded"


def test_execute_resume_from_no_downstream(trace_store: TraceStore):
    from madcop.agent.trace import execute_resume_from
    a = trace_store.create_node(conversation_id="c1")
    result = execute_resume_from(a.id, store=trace_store)
    assert "no downstream" in result.lower()


def test_execute_resume_from_not_found(trace_store: TraceStore):
    from madcop.agent.trace import execute_resume_from
    result = execute_resume_from("nonexistent", store=trace_store)
    assert "Error" in result


def test_execute_get_trace_returns_readable(trace_store: TraceStore):
    from madcop.agent.trace import execute_get_trace
    a = trace_store.create_node(conversation_id="c1", label="root")
    b = trace_store.create_node(conversation_id="c1", parent_id=a.id, label="child")
    trace_store.mark_done(a.id)
    result = execute_get_trace("c1", store=trace_store)
    assert "c1" in result
    assert "root" in result
    assert "child" in result
    assert "2 nodes" in result


def test_execute_get_trace_empty(trace_store: TraceStore):
    from madcop.agent.trace import execute_get_trace
    result = execute_get_trace("nonexistent", store=trace_store)
    assert "No trace" in result
