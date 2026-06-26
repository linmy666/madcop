"""v0.8.0 — Tests for the sub-agent config loader (YAML/TOML/JSON)."""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from madcop.agent.subagent.loader import (
    load_subagent_specs,
    validate_and_build,
)
from madcop.agent.subagent.spec import SubagentSpec


# ---------------------------------------------------------------------------
# YAML happy path
# ---------------------------------------------------------------------------


def test_load_yaml_file(tmp_path: Path):
    f = tmp_path / "code-reviewer.yaml"
    f.write_text(textwrap.dedent("""\
        name: code-reviewer
        description: Reviews pull requests for style
        system_prompt: |
          You are a careful code reviewer.
        tools: [read, bash, grep]
        max_turns: 30
        timeout_seconds: 600
    """))
    specs = load_subagent_specs(f)
    assert len(specs) == 1
    s = specs[0]
    assert s.name == "code-reviewer"
    assert "Reviews" in s.description
    assert "careful code reviewer" in s.system_prompt
    assert s.tools == ("read", "bash", "grep")
    assert s.max_turns == 30
    assert s.timeout_seconds == 600
    # default: task always blocked
    assert "task" in s.disallowed_tools


def test_load_yml_extension_also_recognised(tmp_path: Path):
    f = tmp_path / "researcher.yml"
    f.write_text(textwrap.dedent("""\
        name: researcher
        description: Web research helper
    """))
    specs = load_subagent_specs(f)
    assert len(specs) == 1
    assert specs[0].name == "researcher"


# ---------------------------------------------------------------------------
# TOML happy path
# ---------------------------------------------------------------------------


def test_load_toml_file(tmp_path: Path):
    f = tmp_path / "explorer.toml"
    f.write_text(textwrap.dedent("""\
        [[subagents]]
        name = "explorer"
        description = "Explores codebases"
        max_turns = 20
    """))
    specs = load_subagent_specs(f)
    assert len(specs) == 1
    assert specs[0].name == "explorer"
    assert specs[0].max_turns == 20


# ---------------------------------------------------------------------------
# JSON happy path
# ---------------------------------------------------------------------------


def test_load_json_file(tmp_path: Path):
    f = tmp_path / "tester.json"
    f.write_text(json.dumps([{
        "name": "tester",
        "description": "Writes and runs tests",
        "skills": ["pytest"],
    }]))
    specs = load_subagent_specs(f)
    assert len(specs) == 1
    assert specs[0].name == "tester"
    assert specs[0].skills == ("pytest",)


# ---------------------------------------------------------------------------
# Wrapped form: {subagents: [...]}
# ---------------------------------------------------------------------------


def test_wrapped_form_with_subagents_key(tmp_path: Path):
    f = tmp_path / "bundle.yaml"
    f.write_text(textwrap.dedent("""\
        subagents:
          - name: a
            description: first
          - name: b
            description: second
    """))
    specs = load_subagent_specs(f)
    assert [s.name for s in specs] == ["a", "b"]


# ---------------------------------------------------------------------------
# Directory loading
# ---------------------------------------------------------------------------


def test_load_from_directory_with_default_basenames(tmp_path: Path):
    (tmp_path / "madcop-subagents.yaml").write_text(textwrap.dedent("""\
        - name: from-default
          description: loaded via default basename
    """))
    specs = load_subagent_specs(tmp_path)
    assert len(specs) == 1
    assert specs[0].name == "from-default"


def test_load_from_directory_scans_individual_files(tmp_path: Path):
    # No default basename — loader should fall back to per-file scan.
    (tmp_path / "alpha.yaml").write_text("name: alpha\ndescription: A\n")
    (tmp_path / "beta.yaml").write_text("name: beta\ndescription: B\n")
    (tmp_path / "gamma.json").write_text(json.dumps([
        {"name": "gamma", "description": "G"},
    ]))
    # An unrelated file should be ignored
    (tmp_path / "README.md").write_text("# nope\n")

    specs = load_subagent_specs(tmp_path)
    names = sorted(s.name for s in specs)
    assert names == ["alpha", "beta", "gamma"]


def test_load_from_empty_directory_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="no subagent config files"):
        load_subagent_specs(tmp_path)


def test_load_from_nonexistent_path_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_subagent_specs(tmp_path / "does-not-exist.yaml")


# ---------------------------------------------------------------------------
# Dedup + last-wins
# ---------------------------------------------------------------------------


def test_duplicate_name_later_wins(tmp_path: Path):
    f = tmp_path / "config.yaml"
    f.write_text(textwrap.dedent("""\
        - name: dup
          description: first
          max_turns: 10
        - name: dup
          description: later
          max_turns: 20
    """))
    specs = load_subagent_specs(f)
    assert len(specs) == 1
    s = specs[0]
    assert s.description == "later"
    assert s.max_turns == 20


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


def test_missing_name_raises(tmp_path: Path):
    f = tmp_path / "bad.yaml"
    f.write_text("description: nameless\n")
    with pytest.raises(ValueError, match="missing or invalid 'name'"):
        load_subagent_specs(f)


def test_invalid_tools_type_raises(tmp_path: Path):
    f = tmp_path / "bad.yaml"
    f.write_text("name: x\ndescription: y\ntools: read\n")  # not a list
    with pytest.raises(ValueError, match="'tools' must be a list"):
        load_subagent_specs(f)


def test_empty_string_in_tools_raises(tmp_path: Path):
    f = tmp_path / "bad.yaml"
    f.write_text("name: x\ndescription: y\ntools: ['', 'read']\n")
    with pytest.raises(ValueError, match="'tools\\[0\\]' must be a non-empty string"):
        load_subagent_specs(f)


def test_max_turns_zero_raises(tmp_path: Path):
    f = tmp_path / "bad.yaml"
    f.write_text("name: x\ndescription: y\nmax_turns: 0\n")
    with pytest.raises(ValueError, match="max_turns' must be > 0"):
        load_subagent_specs(f)


def test_timeout_is_bool_rejected(tmp_path: Path):
    f = tmp_path / "bad.yaml"
    f.write_text("name: x\ndescription: y\nmax_turns: true\n")
    with pytest.raises(ValueError, match="must be an int, got bool"):
        load_subagent_specs(f)


def test_task_always_in_disallowed_tools_even_if_user_omits(tmp_path: Path):
    """Defense in depth: user cannot accidentally allow recursive dispatch."""
    f = tmp_path / "config.yaml"
    f.write_text(textwrap.dedent("""\
        name: safe
        description: tries to be safe
        disallowed_tools: []  # user wants to allow everything
    """))
    specs = load_subagent_specs(f)
    assert "task" in specs[0].disallowed_tools


def test_task_remains_blocked_when_user_overrides(tmp_path: Path):
    """Even if user lists 'task' in allowed tools, our loader puts it back in deny-list."""
    f = tmp_path / "config.yaml"
    f.write_text(textwrap.dedent("""\
        name: sneaky
        description: tries to enable task
        tools: [task, read, bash]
    """))
    specs = load_subagent_specs(f)
    # effective_tools() removes 'task' (loader just preserves the spec;
    # the actual deny is enforced at effective_tools time)
    s = specs[0]
    assert s.tools is not None
    assert "task" in s.tools  # user asked for it
    # ... but effective_tools() will strip it:
    effective = s.effective_tools(parent_tools=("read", "bash", "task", "write"))
    assert "task" not in effective


# ---------------------------------------------------------------------------
# Unsupported extension
# ---------------------------------------------------------------------------


def test_unsupported_extension_raises(tmp_path: Path):
    f = tmp_path / "config.xml"
    f.write_text("<subagent/>")
    with pytest.raises(ValueError, match="unsupported subagent config extension"):
        load_subagent_specs(f)


# ---------------------------------------------------------------------------
# Direct validate_and_build
# ---------------------------------------------------------------------------


def test_validate_and_build_minimal():
    spec = validate_and_build({"name": "x", "description": "y"})
    assert isinstance(spec, SubagentSpec)
    assert spec.name == "x"
    assert spec.tools is None
    assert spec.skills is None
    assert spec.model == "inherit"
    assert spec.max_turns == 50  # default
    assert spec.timeout_seconds == 300  # default


def test_validate_and_build_non_dict_raises():
    with pytest.raises(ValueError, match="must be a dict"):
        validate_and_build("not a dict")
