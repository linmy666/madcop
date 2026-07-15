"""Tests for ReAct engine + task router.

Run: cd /Users/linruihan/PycharmProjects/madcop && python -m pytest tests/test_agent_mode.py -v
"""

import sys
from pathlib import Path

# Ensure project root is on path
PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))


# ── Task Router Tests ──────────────────────────────────────────────── #

def test_router_quick_simple_question():
    """Short question without action verbs → quick."""
    from madcop.agent_network.task_router import route_task, QUICK
    result = route_task("什么是闭包")
    assert result.mode == QUICK, f"Expected quick, got {result.mode} ({result.reason})"

def test_router_quick_syntax():
    """Syntax question → quick."""
    from madcop.agent_network.task_router import route_task, QUICK
    result = route_task("Python 的 lambda 语法是什么")
    assert result.mode == QUICK, f"Expected quick, got {result.mode}"

def test_router_standard_bug_fix():
    """Bug fix → standard (ReAct)."""
    from madcop.agent_network.task_router import route_task, STANDARD
    result = route_task("帮我修复 auth.py 里的登录 bug")
    assert result.mode == STANDARD, f"Expected standard, got {result.mode}"

def test_router_standard_add_feature():
    """Add feature → standard."""
    from madcop.agent_network.task_router import route_task, STANDARD
    result = route_task("给用户模型添加 email 字段")
    assert result.mode == STANDARD, f"Expected standard, got {result.mode}"

def test_router_deep_refactor():
    """Refactor → deep."""
    from madcop.agent_network.task_router import route_task, DEEP
    result = route_task("重构整个认证模块，把 session 改成 JWT")
    assert result.mode == DEEP, f"Expected deep, got {result.mode}"

def test_router_deep_code_review():
    """Code review → deep."""
    from madcop.agent_network.task_router import route_task, DEEP
    result = route_task("帮我做一次代码审查")
    assert result.mode == DEEP, f"Expected deep, got {result.mode}"

def test_router_deep_fullstack():
    """Frontend + backend → deep."""
    from madcop.agent_network.task_router import route_task, DEEP
    result = route_task("实现前端页面和后端 API")
    assert result.mode == DEEP, f"Expected deep, got {result.mode}"

def test_router_file_reference_standard():
    """File path reference → standard."""
    from madcop.agent_network.task_router import route_task, STANDARD
    result = route_task("看一下 ./src/main.py 有什么问题")
    assert result.mode == STANDARD, f"Expected standard, got {result.mode}"

def test_router_mode_config():
    """Mode config returns correct effort + workflow."""
    from madcop.agent_network.task_router import get_mode_config
    cfg = get_mode_config("quick")
    assert cfg["effort"] == "low"
    assert cfg["workflow"] == "direct"
    
    cfg = get_mode_config("standard")
    assert cfg["effort"] == "medium"
    assert cfg["workflow"] == "react"
    
    cfg = get_mode_config("deep")
    assert cfg["effort"] == "high"
    assert cfg["workflow"] == "multi_agent"


# ── ReAct Engine Tests ─────────────────────────────────────────────── #

def test_react_parse_final_answer():
    """Parser correctly extracts FINAL_ANSWER."""
    from madcop.agent_network.react_engine import parse_react_response
    text = """Thought: I have enough info to answer.
Action: FINAL_ANSWER
Action Input: The answer is 42."""
    thought, action, inp = parse_react_response(text)
    assert "enough info" in thought
    assert action == "FINAL_ANSWER"
    assert "42" in inp

def test_react_parse_tool_call():
    """Parser correctly extracts a tool call."""
    from madcop.agent_network.react_engine import parse_react_response
    text = """Thought: I need to read the file first.
Action: read_file
Action Input: {"path": "src/main.py"}"""
    thought, action, inp = parse_react_response(text)
    assert "read the file" in thought
    assert action == "read_file"
    assert "main.py" in inp

def test_react_parse_fallback():
    """Parser handles non-structured text as final answer."""
    from madcop.agent_network.react_engine import parse_react_response
    text = "Just a plain answer without structure."
    thought, action, inp = parse_react_response(text)
    assert action == "FINAL_ANSWER"
    assert "plain answer" in inp

def test_react_engine_with_mock_final():
    """ReAct engine terminates on FINAL_ANSWER."""
    from madcop.agent_network.react_engine import ReActEngine, ReActResult
    from madcop.llm.client import MockClient
    
    mock = MockClient(scripted=[
        "Thought: This is simple.\nAction: FINAL_ANSWER\nAction Input: Done!"
    ])
    engine = ReActEngine(client=mock, tools=[], max_steps=5)
    result = engine.run("say hello")
    
    assert result.status == "completed"
    assert result.final_answer == "Done!"
    assert len(result.steps) == 1
    assert result.steps[0].action == "FINAL_ANSWER"

def test_react_engine_with_mock_tool_then_final():
    """ReAct engine executes one tool call then finishes."""
    from madcop.agent_network.react_engine import ReActEngine
    from madcop.llm.client import MockClient
    
    # Mock a custom tool executor
    def fake_executor(tool_name, action_input, work_dir):
        return f"[{tool_name} result: file content]"
    
    mock = MockClient(scripted=[
        # Step 1: request a tool call
        "Thought: I should read the file.\nAction: read_file\nAction Input: {\"path\": \"test.py\"}",
        # Step 2: final answer after seeing observation
        "Thought: Now I can answer.\nAction: FINAL_ANSWER\nAction Input: The file looks good.",
    ])
    engine = ReActEngine(
        client=mock, tools=[{"name": "read_file", "description": "read a file"}],
        tool_executor=fake_executor, max_steps=5,
    )
    result = engine.run("check test.py")
    
    assert result.status == "completed"
    assert result.final_answer == "The file looks good."
    assert len(result.steps) == 2
    assert result.steps[0].action == "read_file"
    assert result.steps[1].action == "FINAL_ANSWER"
    assert result.tool_calls == 1

def test_react_engine_max_steps():
    """ReAct engine stops at max_steps."""
    from madcop.agent_network.react_engine import ReActEngine
    from madcop.llm.client import MockClient
    
    # Always request tool calls, never finish
    mock = MockClient(default_response=(
        "Thought: Need more info.\nAction: read_file\nAction Input: {\"path\": \"x\"}"
    ))
    def fake_executor(name, inp, wd):
        return "content"
    
    engine = ReActEngine(
        client=mock, tools=[{"name": "read_file", "description": "read"}],
        tool_executor=fake_executor, max_steps=3,
    )
    result = engine.run("endless task")
    
    assert result.status == "max_steps"
    assert len(result.steps) <= 4  # 3 steps + possibly 1 final attempt
