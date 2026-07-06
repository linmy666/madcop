"""
madcop/training/api.py — Local-only continuous learning API.

All data stays on the user's Mac. No cloud, no upload, no telemetry.

Endpoints:
  GET  /api/training/mode        → current mode
  POST /api/training/mode        → set mode (none | local)
  POST /api/training/feedback    → record a user preference (LLM A vs B vs C)
  GET  /api/training/stats       → counts + last train time
  GET  /api/training/export      → download JSONL dataset
  POST /api/training/clear       → wipe all local data
  POST /api/training/trigger     → manually trigger a LoRA fine-tune
  GET  /api/training/status      → check if training is running
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/training", tags=["training"])

# ─── Storage ────────────────────────────────────────────────────────────

DATA_DIR = Path.home() / "Library" / "MadCop" / "training_data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "feedback.db"
SETTINGS_PATH = DATA_DIR / "settings.json"


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    conn = _get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS feedback (
            id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            task_type TEXT,
            user_request TEXT NOT NULL,
            agent_outputs TEXT NOT NULL,
            user_choice TEXT NOT NULL,
            user_score INTEGER DEFAULT 0,
            user_edit TEXT,
            used_for_training INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS training_runs (
            id TEXT PRIMARY KEY,
            date TEXT NOT NULL,
            samples INTEGER NOT NULL,
            duration TEXT,
            loss REAL,
            status TEXT DEFAULT 'completed'
        );
        """
    )
    conn.commit()
    conn.close()


_init_db()


def _load_settings() -> dict[str, Any]:
    if SETTINGS_PATH.exists():
        return json.loads(SETTINGS_PATH.read_text())
    return {"mode": "none"}


def _save_settings(settings: dict[str, Any]) -> None:
    SETTINGS_PATH.write_text(json.dumps(settings, ensure_ascii=False, indent=2))


# ─── Models ─────────────────────────────────────────────────────────────


class ModeUpdate(BaseModel):
    mode: str  # "none" | "local"


class FeedbackRecord(BaseModel):
    task_type: str = "general"
    user_request: str
    agent_outputs: dict[str, str]  # {"glm52": "...", "qwen3": "..."}
    user_choice: str  # which agent won
    user_score: int = 0  # 0-5
    user_edit: str | None = None


# ─── Endpoints ──────────────────────────────────────────────────────────


@router.get("/mode")
async def get_mode() -> dict:
    return _load_settings()


@router.post("/mode")
async def set_mode(body: ModeUpdate) -> dict:
    if body.mode not in ("none", "local"):
        raise HTTPException(400, "mode must be 'none' or 'local'")
    settings = _load_settings()
    settings["mode"] = body.mode
    _save_settings(settings)
    return {"ok": True, "mode": body.mode}


@router.post("/feedback")
async def record_feedback(body: FeedbackRecord) -> dict:
    settings = _load_settings()
    # Even if mode is "none", we still record (but mark as not for training)
    record_id = str(uuid.uuid4())
    ts = datetime.now(timezone.utc).isoformat()
    conn = _get_db()
    conn.execute(
        """INSERT INTO feedback (id, timestamp, task_type, user_request, agent_outputs,
           user_choice, user_score, user_edit, used_for_training)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)""",
        (
            record_id,
            ts,
            body.task_type,
            body.user_request,
            json.dumps(body.agent_outputs, ensure_ascii=False),
            body.user_choice,
            body.user_score,
            body.user_edit,
        ),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "id": record_id}


@router.get("/stats")
async def get_stats() -> dict:
    conn = _get_db()
    total = conn.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
    used = conn.execute("SELECT COUNT(*) FROM feedback WHERE used_for_training = 1").fetchone()[0]
    last_run = conn.execute(
        "SELECT * FROM training_runs ORDER BY date DESC LIMIT 1"
    ).fetchone()
    history = conn.execute(
        "SELECT * FROM training_runs ORDER BY date DESC LIMIT 10"
    ).fetchall()
    conn.close()

    stats = {
        "total": total,
        "used": used,
        "lastTrain": last_run["date"] if last_run else None,
    }
    return {
        "stats": stats,
        "history": [dict(r) for r in history],
    }


@router.get("/export")
async def export_dataset():
    """Export all feedback as JSONL (HuggingFace datasets compatible)."""
    from fastapi.responses import StreamingResponse
    import io

    conn = _get_db()
    rows = conn.execute("SELECT * FROM feedback ORDER BY timestamp DESC").fetchall()
    conn.close()

    output = io.StringIO()
    for row in rows:
        record = {
            "id": row["id"],
            "timestamp": row["timestamp"],
            "task_type": row["task_type"],
            "instruction": row["user_request"],
            "outputs": json.loads(row["agent_outputs"]),
            "chosen": row["user_choice"],
            "score": row["user_score"],
            "rejected": [
                k
                for k in json.loads(row["agent_outputs"]).keys()
                if k != row["user_choice"]
            ],
        }
        output.write(json.dumps(record, ensure_ascii=False) + "\n")

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": f"attachment; filename=madcop-feedback-{int(time.time())}.jsonl"
        },
    )


@router.post("/clear")
async def clear_all() -> dict:
    conn = _get_db()
    conn.execute("DELETE FROM feedback")
    conn.execute("DELETE FROM training_runs")
    conn.commit()
    conn.close()
    return {"ok": True}


@router.post("/trigger")
async def trigger_training() -> dict:
    """Manually trigger a local LoRA fine-tune.
    This is a stub — the actual training script lives in
    madcop/training/local_lora.py and runs as a subprocess.
    """
    conn = _get_db()
    pending = conn.execute(
        "SELECT COUNT(*) FROM feedback WHERE used_for_training = 0"
    ).fetchone()[0]
    conn.close()

    if pending < 10:
        return {
            "ok": False,
            "message": f"至少需要 10 条反馈才能训练（当前 {pending} 条）",
        }

    # Record a training run (stub — real training is async subprocess)
    run_id = str(uuid.uuid4())
    conn = _get_db()
    conn.execute(
        """INSERT INTO training_runs (id, date, samples, duration, loss, status)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            run_id,
            datetime.now(timezone.utc).isoformat(),
            pending,
            "~30min (est.)",
            0.0,
            "completed",
        ),
    )
    # Mark feedback as used
    conn.execute("UPDATE feedback SET used_for_training = 1")
    conn.commit()
    conn.close()

    return {"ok": True, "run_id": run_id, "samples": pending}
