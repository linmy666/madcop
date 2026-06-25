"""L3 — Task difficulty classifier and model router.

Auto mode (default):
  Given a task, score its difficulty 0.0-1.0, then bucket into one of three tiers:
    - T1 Strong: planner, reflect, aggregate, replan, complex reasoning
    - T2 Fast:   execute, format, parse, summarise, tool calls
    - T3 Local:  rule check, JSON parse, schema validate, regex (no API call)

Manual mode (auto=false):
  The user-supplied `manual_routing` dict maps agent step names to tiers.

This module has zero I/O and zero LLM calls — it is pure classification logic.
The actual provider lookup happens in providers.py; this module just decides
"what tier does this task deserve?".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping


class ModelTier(str, Enum):
    """Three tiers. T3 means 'no LLM call, use local rule'."""

    T1_STRONG = "T1"  # plan / reflect / aggregate / replan
    T2_FAST = "T2"    # execute / tool call / format / parse
    T3_LOCAL = "T3"   # rule check / local parse (no API)


@dataclass(frozen=True)
class TaskSignals:
    """Structured features fed into the difficulty classifier.

    Each field is a boolean or numeric signal. Keep this flat — the classifier
    is intentionally a hand-tuned weighted sum, not a learned model. Hand-tuning
    makes it auditable and predictable.
    """

    # Structural
    requires_planning: bool = False         # "分析" / "设计" / "规划"
    open_ended_goal: bool = False           # "帮我想想" / "你觉得呢"
    multi_step: bool = False                # contains "然后" / "接着" / "之后"

    # Domain
    touches_supply_chain: bool = False     # WMS / OMS / TMS / CUSUM / 库存
    touches_finance: bool = False          # 财务 / 价格 / 成本 / ¥
    touches_code: bool = False             # code / 函数 / class

    # Context
    context_tokens: int = 0                # rough estimate

    # User priority
    user_emphasised_accuracy: bool = False # "重要" / "关键" / "must be accurate"
    simple_lookup: bool = False             # "查一下" / "是什么"

    # Free-form overrides from caller (e.g. agent step name)
    step: str = "execute"                   # default

    @property
    def has_supply_chain(self) -> bool:
        return self.touches_supply_chain


@dataclass(frozen=True)
class DifficultyScore:
    """The classifier's verdict on a task."""

    score: float                           # 0.0 - 1.0+
    contributing_signals: tuple[str, ...] = field(default_factory=tuple)
    tier: ModelTier = ModelTier.T2_FAST

    def is_high(self) -> bool:
        return self.tier == ModelTier.T1_STRONG

    def is_local(self) -> bool:
        return self.tier == ModelTier.T3_LOCAL


@dataclass(frozen=True)
class RoutingDecision:
    """The router's final answer: which tier + why."""

    tier: ModelTier
    score: float
    reason: str
    step: str = "execute"


# ---------------------------------------------------------------------------
# Classifier — weighted-sum. Sum of weights is ~1.0 in normal cases.
# ---------------------------------------------------------------------------

# Buckets (thresholds for final tier assignment)
T1_THRESHOLD = 0.70
T2_THRESHOLD = 0.40

# Weights for the auto-mode classifier
_WEIGHTS = {
    "requires_planning": 0.30,
    "open_ended_goal": 0.20,
    "multi_step": 0.15,
    "touches_supply_chain": 0.30,
    "touches_finance": 0.25,
    "touches_code": 0.15,
    "context_heavy": 0.20,             # applied if context_tokens > 10_000
    "user_emphasised_accuracy": 0.10,
    "simple_lookup": -0.30,            # negative signal: demote
}


def _score(signals: TaskSignals) -> tuple[float, list[str]]:
    score = 0.0
    contributing: list[str] = []

    if signals.requires_planning:
        score += _WEIGHTS["requires_planning"]
        contributing.append("requires_planning")
    if signals.open_ended_goal:
        score += _WEIGHTS["open_ended_goal"]
        contributing.append("open_ended_goal")
    if signals.multi_step:
        score += _WEIGHTS["multi_step"]
        contributing.append("multi_step")
    if signals.touches_supply_chain:
        score += _WEIGHTS["touches_supply_chain"]
        contributing.append("touches_supply_chain")
    if signals.touches_finance:
        score += _WEIGHTS["touches_finance"]
        contributing.append("touches_finance")
    if signals.touches_code:
        score += _WEIGHTS["touches_code"]
        contributing.append("touches_code")
    if signals.context_tokens > 10_000:
        score += _WEIGHTS["context_heavy"]
        contributing.append("context_heavy")
    if signals.user_emphasised_accuracy:
        score += _WEIGHTS["user_emphasised_accuracy"]
        contributing.append("user_emphasised_accuracy")
    if signals.simple_lookup:
        score += _WEIGHTS["simple_lookup"]  # negative
        contributing.append("simple_lookup")

    return score, contributing


def _bucket(score: float) -> ModelTier:
    if score >= T1_THRESHOLD:
        return ModelTier.T1_STRONG
    if score >= T2_THRESHOLD:
        return ModelTier.T2_FAST
    return ModelTier.T3_LOCAL


def classify(signals: TaskSignals) -> DifficultyScore:
    """Pure function: turn TaskSignals into DifficultyScore."""
    score, contributing = _score(signals)
    return DifficultyScore(
        score=score,
        contributing_signals=tuple(contributing),
        tier=_bucket(score),
    )


# ---------------------------------------------------------------------------
# Manual mode — caller-supplied mapping
# ---------------------------------------------------------------------------

# Defaults used when the user does not override per-step
DEFAULT_STEP_TO_TIER: Mapping[str, ModelTier] = {
    # T1 — needs reasoning
    "plan":        ModelTier.T1_STRONG,
    "reflect":     ModelTier.T1_STRONG,
    "aggregate":   ModelTier.T1_STRONG,
    "replan":      ModelTier.T1_STRONG,
    "growth":      ModelTier.T1_STRONG,  # meta-pattern mining
    # T2 — tool-flavored
    "execute":     ModelTier.T2_FAST,
    "summarise":   ModelTier.T2_FAST,
    "format":      ModelTier.T2_FAST,
    "parse":       ModelTier.T2_FAST,
    "extract":     ModelTier.T2_FAST,
    "distill":     ModelTier.T2_FAST,
    # T3 — local, no API
    "verify":      ModelTier.T3_LOCAL,   # rule check first
    "schema_check": ModelTier.T3_LOCAL,
    "json_parse":  ModelTier.T3_LOCAL,
}


# ---------------------------------------------------------------------------
# Router — the public facade
# ---------------------------------------------------------------------------

class ModelRouter:
    """Decides which tier a given task/step should use.

    Two modes:
    - auto=True (default): classifier picks tier from TaskSignals
    - auto=False: user-supplied `manual_routing` dict is used (step → tier)
    """

    def __init__(
        self,
        auto: bool = True,
        manual_routing: Mapping[str, str | ModelTier] | None = None,
        cost_budget_per_run: float | None = None,
        context_budget_per_call: int = 30_000,
    ) -> None:
        self.auto = auto
        # Normalise manual_routing values to ModelTier
        self.manual_routing: dict[str, ModelTier] = {}
        if manual_routing:
            for step, tier in manual_routing.items():
                self.manual_routing[step] = self._coerce_tier(tier)
        self.cost_budget_per_run = cost_budget_per_run
        self.context_budget_per_call = context_budget_per_call

    @staticmethod
    def _coerce_tier(v: str | ModelTier) -> ModelTier:
        if isinstance(v, ModelTier):
            return v
        s = str(v).strip().upper()
        # Accept "T1" / "T1_STRONG" / "strong" / "plan"
        if s in ("T1", "T1_STRONG", "STRONG"):
            return ModelTier.T1_STRONG
        if s in ("T2", "T2_FAST", "FAST"):
            return ModelTier.T2_FAST
        if s in ("T3", "T3_LOCAL", "LOCAL", "RULE"):
            return ModelTier.T3_LOCAL
        raise ValueError(f"Unknown tier: {v!r}")

    def route(
        self,
        signals: TaskSignals | None = None,
        step: str | None = None,
    ) -> RoutingDecision:
        """Return a RoutingDecision. In auto mode, signals is required."""
        if not self.auto:
            step_name = step or (signals.step if signals else "execute")
            tier = self.manual_routing.get(
                step_name,
                DEFAULT_STEP_TO_TIER.get(step_name, ModelTier.T2_FAST),
            )
            return RoutingDecision(
                tier=tier,
                score=0.0,
                reason=f"manual: step={step_name} → {tier.value}",
                step=step_name,
            )

        # Auto mode
        if signals is None:
            raise ValueError("auto mode requires TaskSignals")
        ds = classify(signals)
        return RoutingDecision(
            tier=ds.tier,
            score=ds.score,
            reason=f"auto: score={ds.score:.2f} signals={list(ds.contributing_signals)}",
            step=signals.step,
        )

    # Convenience constructors -------------------------------------------------

    @classmethod
    def auto_default(cls) -> "ModelRouter":
        return cls(auto=True, cost_budget_per_run=0.50, context_budget_per_call=30_000)

    @classmethod
    def manual(
        cls,
        step_to_tier: Mapping[str, str | ModelTier],
    ) -> "ModelRouter":
        return cls(auto=False, manual_routing=dict(step_to_tier))


__all__ = [
    "ModelRouter",
    "ModelTier",
    "DifficultyScore",
    "RoutingDecision",
    "TaskSignals",
    "classify",
    "DEFAULT_STEP_TO_TIER",
]
