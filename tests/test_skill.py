"""Tests for the skill scaffolder."""

from __future__ import annotations

from pathlib import Path

import pytest

from madcop.skill import (
    render_new_adapter,
    render_new_cost,
    render_new_rule,
)
from madcop.skill.templates import (
    to_class_name,
    to_rule_id,
    to_source_system,
)


# --------------------------------------------------------------------------- #
# Naming helpers
# --------------------------------------------------------------------------- #

def test_to_class_name_snake() -> None:
    assert to_class_name("my_rule") == "MyRule"
    assert to_class_name("a") == "A"
    assert to_class_name("cold_chain_temp") == "ColdChainTemp"


def test_to_rule_id_converts_first_underscore_to_dot() -> None:
    assert to_rule_id("wms_temp_breach") == "wms.temp_breach"
    assert to_rule_id("singletoken") == "singletoken"
    assert to_rule_id("a_b_c") == "a.b_c"


def test_to_source_system_uses_last_token() -> None:
    assert to_source_system("my_oms_adapter") == "adapter"
    assert to_source_system("wms") == "wms"


# --------------------------------------------------------------------------- #
# render_new_rule
# --------------------------------------------------------------------------- #

def test_render_new_rule_creates_files(tmp_path: Path) -> None:
    rule_path, test_path = render_new_rule("my_check", tmp_path)
    assert rule_path.exists()
    assert test_path.exists()
    assert rule_path.name == "my_check.py"
    assert test_path.name == "test_my_check.py"


def test_render_new_rule_content_uses_class_name(tmp_path: Path) -> None:
    rule_path, _ = render_new_rule("my_check", tmp_path)
    content = rule_path.read_text()
    assert "class MyCheck" in content
    assert 'rule_id = "my.check"' in content


def test_render_new_rule_test_content(tmp_path: Path) -> None:
    _, test_path = render_new_rule("my_check", tmp_path)
    content = test_path.read_text()
    assert "MyCheck" in content
    assert "test_my_check_exists" in content
    assert "test_my_check_ignores_other_sources" in content


# --------------------------------------------------------------------------- #
# render_new_adapter
# --------------------------------------------------------------------------- #

def test_render_new_adapter_creates_files(tmp_path: Path) -> None:
    adapter_path, test_path = render_new_adapter("my_oms", tmp_path)
    assert adapter_path.exists()
    assert test_path.exists()


def test_render_new_adapter_content(tmp_path: Path) -> None:
    adapter_path, _ = render_new_adapter("my_oms", tmp_path)
    content = adapter_path.read_text()
    assert "class MyOms" in content
    assert 'source_system = "oms"' in content


# --------------------------------------------------------------------------- #
# render_new_cost
# --------------------------------------------------------------------------- #

def test_render_new_cost_creates_files(tmp_path: Path) -> None:
    cost_path, test_path = render_new_cost("my_cost", tmp_path)
    assert cost_path.exists()
    assert test_path.exists()


def test_render_new_cost_subclasses_counterfactual(tmp_path: Path) -> None:
    cost_path, _ = render_new_cost("my_cost", tmp_path)
    content = cost_path.read_text()
    assert "class MyCost" in content
    assert "CounterfactualEngine" in content


# --------------------------------------------------------------------------- #
# Edge cases
# --------------------------------------------------------------------------- #

def test_render_creates_nested_dirs(tmp_path: Path) -> None:
    """target_dir itself may not pre-exist; tests/ subdir should be created."""
    nested = tmp_path / "deep" / "dir"
    rule_path, test_path = render_new_rule("z", nested)
    assert rule_path.exists()
    assert test_path.exists()
    assert test_path.parent.name == "tests"