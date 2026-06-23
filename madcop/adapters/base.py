"""Adapter contract — the seam between the outside world and `UnifiedEvent`.

Every system (OMS / TMS / WMS / BMS / future) ships an adapter that implements
`BaseAdapter`. Two responsibilities, and only two:

1. **Pull** raw data from a system (HTTP, DB, file, etc.) and yield `UnifiedEvent`s.
2. **Push** actions back to the system (e.g. re-route shipment, mark exception).

We deliberately keep the adapter small. Logic that *reads* the event stream
lives in the anomaly engine. Logic that *acts* on decisions lives in the
strategy router. The adapter is just a translator.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator

from ..event import SourceSystem, UnifiedEvent


class BaseAdapter(ABC):
    """The contract every system adapter must satisfy.

    Adapters are stateful objects (they hold a connection, an API key, a
    file handle). They are constructed once per session and called repeatedly.
    """

    source_system: SourceSystem  # set by subclass

    @abstractmethod
    def fetch(self, *, since: str | None = None, subject_id: str | None = None) -> Iterator[UnifiedEvent]:
        """Yield events from the upstream system, optionally filtered.

        `since` is a UTC ISO 8601 string. If given, only events with
        `timestamp >= since` should be returned.

        `subject_id`, if given, restricts to events about a single business
        object (an order, a SKU, a shipment, a contract). Adapters that
        cannot filter server-side should filter in-memory after fetching.

        Yields events in **any order** — the LangGraph orchestrator sorts
        by timestamp.
        """
        raise NotImplementedError

    @abstractmethod
    def execute(self, action: "Action") -> dict:
        """Push an action back to the system. Returns the system's response.

        See `Action` for the schema. Adapters that cannot perform an action
        (e.g. WMS can't change a contract) should raise
        `UnsupportedActionError`.
        """
        raise NotImplementedError

    def health_check(self) -> bool:
        """Optional. Default: assume healthy. Override for real wire checks."""
        return True


class UnsupportedActionError(NotImplementedError):
    """Raised when an adapter is asked to perform an action outside its scope."""


from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class Action:
    """A command the strategy router wants executed against an adapter.

    The action is **adapter-agnostic**: the router does not know which system
    will run it. The router picks an adapter based on `target_system` and the
    adapter translates the rest.
    """

    target_system: SourceSystem
    action_type: str                          # free-form, adapter-defined vocabulary
    subject_id: str                           # what the action is about
    parameters: Mapping[str, Any]             # adapter-specific args
