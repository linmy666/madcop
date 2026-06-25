"""L7 — Skill CLI templates.

The "skill system" in madcop is intentionally minimal: a CLI that emits
boilerplate for adding new components. Three skills today:

- `new-rule`: scaffold a custom anomaly rule + its test
- `new-adapter`: scaffold a BaseAdapter + its test
- `new-cost`: scaffold a custom InterventionKind cost function + test

Why CLI templates instead of an LLM-driven scaffolder:
- Deterministic: same input → same output every time
- No API key required
- Forces the human to fill in TODO sections, which builds understanding
- Plays nicely with AI PM eval harnesses (the templates can be tested
  for validity, not just generated)

Usage:
    madcop skill new-rule my_check
    madcop skill new-adapter my_source
    madcop skill new-cost my_intervention
"""

from __future__ import annotations

from pathlib import Path


# --------------------------------------------------------------------------- #
# new-rule
# --------------------------------------------------------------------------- #

RULE_PY_TEMPLATE = '''"""Custom anomaly rule: {class_name}."""

from __future__ import annotations

from madcop.anomaly.detector import AnomalyFinding, BaseRule
from madcop.event import EventType, SourceSystem, UnifiedEvent


class {class_name}(BaseRule):
    """TODO: describe what this rule detects and why.

    Edit this docstring. 1-3 sentences that an operator can read.
    """
    rule_id = "{rule_id}"
    description = "TODO: one-line description"

    def evaluate(self, event: UnifiedEvent) -> AnomalyFinding | None:
        # TODO: filter on source_system / event_type you care about
        if event.source_system != SourceSystem.WMS:
            return None
        if event.event_type != EventType.TEMPERATURE_READING:
            return None

        # TODO: implement your detection logic.
        # Read event.value (numeric payload), event.attributes (dict),
        # event.subject_id, etc. Return None if no anomaly.
        return None
'''

RULE_TEST_TEMPLATE = '''"""Tests for {class_name}."""

from __future__ import annotations

from madcop.anomaly.rules import {class_name}
from madcop.event import EventType, SourceSystem, UnifiedEvent, make_event


def _make_event(value: float | None = None, **attrs):
    return make_event(
        timestamp="2026-06-15T10:00:00Z",
        source_system=SourceSystem.WMS,
        event_type=EventType.TEMPERATURE_READING,
        subject_id="TEST-1",
        value=value,
        attributes=attrs,
    )


def test_{snake_name}_exists() -> None:
    rule = {class_name}()
    assert rule.rule_id  # not empty


def test_{snake_name}_ignores_other_sources() -> None:
    rule = {class_name}()
    e = make_event(
        timestamp="2026-06-15T10:00:00Z",
        source_system=SourceSystem.OMS,
        event_type=EventType.ORDER_PLACED,
        subject_id="TEST-1",
    )
    assert rule.evaluate(e) is None


# TODO: add tests for the rule's specific detection logic.
'''


# --------------------------------------------------------------------------- #
# new-adapter
# --------------------------------------------------------------------------- #

ADAPTER_PY_TEMPLATE = '''"""Custom adapter: {class_name}.

Yields UnifiedEvent objects from your data source. See BaseAdapter for
the full contract.
"""

from __future__ import annotations

from collections.abc import Iterator

from madcop.adapters.base import BaseAdapter
from madcop.event import UnifiedEvent


class {class_name}(BaseAdapter):
    """TODO: describe what this adapter connects to (e.g. an internal OMS API,
    a CSV file, a Kafka topic).
    """
    source_system = "{source_system}"

    def execute(
        self,
        action: str,
        *,
        since: str | None = None,
        subject_id: str | None = None,
    ) -> Iterator[UnifiedEvent]:
        # TODO: connect to your data source and yield events. Use
        # madcop.event.make_event(...) to construct them so all validation
        # (UTC timestamp, severity, event_type/source_system consistency)
        # is applied.
        if False:
            yield  # noqa: keep this generator syntactically valid
'''

ADAPTER_TEST_TEMPLATE = '''"""Tests for {class_name}."""

from __future__ import annotations

import pytest

from madcop.adapters.base import BaseAdapter
from madcop.adapters.{snake_name} import {class_name}


def test_{snake_name}_is_base_adapter() -> None:
    assert issubclass({class_name}, BaseAdapter)


def test_{snake_name}_declares_source_system() -> None:
    a = {class_name}()
    assert a.source_system  # not empty


def test_{snake_name}_execute_returns_iterator() -> None:
    a = {class_name}()
    # TODO: replace with an actual call once execute() is implemented.
    # gen = a.execute("read", since=None)
    # assert iter(gen) is not None
'''


# --------------------------------------------------------------------------- #
# new-cost
# --------------------------------------------------------------------------- #

COST_PY_TEMPLATE = '''"""Custom intervention cost: {class_name}.

Define how to compute the cost of {class_name} intervention for a given
finding + event window. See madcop.counterfactual for the Intervention
and CostModel contracts.
"""

from __future__ import annotations

from madcop.counterfactual.cost import (
    CostModel,
    CounterfactualEngine,
)


class {class_name}(CounterfactualEngine):
    """TODO: subclass CounterfactualEngine and override _intervention_cost()
    to add a new intervention kind. Register the kind in InterventionKind
    too (the enum lives in madcop.counterfactual.cost).
    """

    def __init__(self, cost_model: CostModel | None = None, **kwargs):
        super().__init__(cost_model=cost_model, **kwargs)
        # TODO: add any custom params here.
'''

COST_TEST_TEMPLATE = '''"""Tests for {class_name}."""

from __future__ import annotations

from madcop.counterfactual.cost import CostModel
from madcop.adapters.{snake_name} import {class_name}  # if reusing module


def test_{snake_name}_constructs() -> None:
    engine = {class_name}(CostModel())
    assert engine.cost.lost_margin_per_unit > 0


# TODO: add scenarios that exercise your custom intervention cost.
'''


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def to_class_name(snake: str) -> str:
    """my_rule -> MyRule"""
    parts = snake.split("_")
    return "".join(p.capitalize() for p in parts)


def to_rule_id(snake: str) -> str:
    """my_rule -> my.rule"""
    return snake.replace("_", ".", 1) if "_" in snake else snake


def to_source_system(snake: str) -> str:
    """my_oms -> oms"""
    parts = snake.lower().split("_")
    return parts[-1] if parts else snake.lower()


def render_new_rule(snake_name: str, target_dir: Path) -> tuple[Path, Path]:
    """Generate rule + test files. Returns (rule_path, test_path)."""
    class_name = to_class_name(snake_name)
    rule_id = to_rule_id(snake_name)
    target_dir.mkdir(parents=True, exist_ok=True)
    rule_path = target_dir / f"{snake_name}.py"
    test_path = target_dir / "tests" / f"test_{snake_name}.py"
    rule_path.write_text(RULE_PY_TEMPLATE.format(class_name=class_name, rule_id=rule_id))
    test_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.write_text(RULE_TEST_TEMPLATE.format(class_name=class_name, snake_name=snake_name))
    return rule_path, test_path


def render_new_adapter(snake_name: str, target_dir: Path) -> tuple[Path, Path]:
    class_name = to_class_name(snake_name)
    source_system = to_source_system(snake_name)
    target_dir.mkdir(parents=True, exist_ok=True)
    adapter_path = target_dir / f"{snake_name}.py"
    test_path = target_dir / "tests" / f"test_{snake_name}.py"
    adapter_path.write_text(
        ADAPTER_PY_TEMPLATE.format(class_name=class_name, source_system=source_system)
    )
    test_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.write_text(
        ADAPTER_TEST_TEMPLATE.format(class_name=class_name, snake_name=snake_name)
    )
    return adapter_path, test_path


def render_new_cost(snake_name: str, target_dir: Path) -> tuple[Path, Path]:
    class_name = to_class_name(snake_name)
    target_dir.mkdir(parents=True, exist_ok=True)
    cost_path = target_dir / f"{snake_name}.py"
    test_path = target_dir / "tests" / f"test_{snake_name}.py"
    cost_path.write_text(COST_PY_TEMPLATE.format(class_name=class_name, snake_name=snake_name))
    test_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.write_text(
        COST_TEST_TEMPLATE.format(class_name=class_name, snake_name=snake_name)
    )
    return cost_path, test_path