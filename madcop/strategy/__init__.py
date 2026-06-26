"""v0.6.0 strategy layer — multi-model orchestration, routing, cost tracking.

Public surface for the strategy layer. Importers should go through this barrel:

    from madcop.strategy import (
        ModelRouter, ModelTier, DifficultyScore,
        ProviderRegistry, ProviderSpec,
        CostTracker, RunCost,
        Scratchpad, ScratchpadState,
        ContextCompactor,
    )

Sub-modules:
- router.py: difficulty classifier + tier picker
- providers.py: OpenAI-compat provider registry
- cost.py: per-call + per-run cost tracking
- scratchpad.py: disk-backed agent state
- context_compactor.py: prompt-windowing + summarisation
"""
from __future__ import annotations

from .router import (
    ModelRouter,
    ModelTier,
    DifficultyScore,
    RoutingDecision,
    TaskSignals,
)
from .providers import (
    ProviderRegistry,
    ProviderSpec,
    register_default_providers,
)
from .cost import (
    CostTracker,
    RunCost,
    CallCost,
)
from .scratchpad import (
    Scratchpad,
    ScratchpadState,
    StepRecord,
)
from .wal import (
    WAL,
    Replay,
    StartRecord,
    WALStepRecord,
    FinishRecord,
)
from .context_compactor import (
    ContextCompactor,
    CompactionResult,
)

__all__ = [
    "ModelRouter", "ModelTier", "DifficultyScore", "RoutingDecision", "TaskSignals",
    "ProviderRegistry", "ProviderSpec", "register_default_providers",
    "CostTracker", "RunCost", "CallCost",
    "Scratchpad", "ScratchpadState", "StepRecord",
    "WAL", "Replay", "StartRecord", "WALStepRecord", "FinishRecord",
    "ContextCompactor", "CompactionResult",
]
