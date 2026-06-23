"""L2 — Anomaly detection.

The detector is a thin orchestrator over a list of `BaseRule` instances. Each
rule inspects the event stream and either fires or stays silent. The detector
collects fired rules and returns a list of `AnomalyFinding`s.

Design choices:

- Rules are **stateless** and **per-event**. A rule that needs a window
  (e.g. "breach sustained for >15 min") does its own windowing internally.
  This is simple and correct, at the cost of some redundant work. Optimize
  later if needed.
- A single event can fire multiple rules. We do not deduplicate. Different
  rules signal different concerns (a single breach can be both a temperature
  rule AND a sustained-duration rule).
- Rules have a `rule_id` so downstream consumers (the strategy router in W5,
  the weekly report in W7) can identify them in feedback logs.
- `severity` here is the **rule's** severity, distinct from the event's
  adapter-set severity. The orchestrator will eventually combine them; for
  W2, the rule severity is what we surface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from ..event import UnifiedEvent


@dataclass(frozen=True)
class AnomalyFinding:
    """A single rule's verdict on a single event (or window)."""
    rule_id: str
    subject_id: str
    timestamp: str                          # when the anomaly was observed
    severity: int                           # 1..5, set by the rule
    summary: str                            # one-line human description
    details: dict = field(default_factory=dict)


class BaseRule(ABC):
    """A single anomaly detection rule.

    Rules are constructed once and reused. They must be **idempotent**:
    calling `evaluate()` twice with the same event must yield the same result.
    """

    rule_id: str                            # set by subclass
    description: str                        # one-line human description

    @abstractmethod
    def evaluate(self, event: UnifiedEvent) -> AnomalyFinding | None:
        """Return an `AnomalyFinding` if this rule fires, else `None`."""
        raise NotImplementedError


class Detector:
    """Runs a set of rules over a stream of events.

    Usage:
        detector = Detector([ColdChainTemperature(threshold_c=-15.0)])
        findings = list(detector.run(events))
    """

    def __init__(self, rules: Sequence[BaseRule]):
        if not rules:
            raise ValueError("Detector requires at least one rule")
        self._rules = list(rules)

    @property
    def rules(self) -> Sequence[BaseRule]:
        return tuple(self._rules)

    def evaluate_event(self, event: UnifiedEvent) -> list[AnomalyFinding]:
        """Run all rules on a single event. Returns findings (may be empty)."""
        return [
            f for f in (r.evaluate(event) for r in self._rules)
            if f is not None
        ]

    def run(self, events: Iterable[UnifiedEvent]) -> Iterable[AnomalyFinding]:
        """Stream findings as we iterate events. Order: rule order per event,
        event order across the stream."""
        for ev in events:
            for f in self.evaluate_event(ev):
                yield f
