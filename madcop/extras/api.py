"""v3.0 — MadCop-exclusive APIs: skills (CRUD) and usage stats."""
import json, time
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/agents", tags=["madcop-extra"])

_DATA = Path.home() / ".madcop" / "extras"
_DATA.mkdir(parents=True, exist_ok=True)

_SKILLS = _DATA / "skills.json"
_USAGE = _DATA / "usage.json"


def _load(p):
    if not p.exists(): return []
    try: return json.loads(p.read_text())
    except: return []

def _save(p, d):
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2))


# ── Skills (CRUD) — MadCop-exclusive ───────────────────────────────── #

class SkillCreate(BaseModel):
    name: str
    description: str = ""
    triggers: list[str] = []
    steps: list[dict] = []
    enabled: bool = True

@router.get("/skills")
async def list_skills():
    return _load(_SKILLS)

@router.post("/skills")
async def create_skill(body: SkillCreate):
    items = _load(_SKILLS)
    item = {
        "id": "sk" + str(int(time.time())),
        **body.model_dump(),
        "createdAt": int(time.time()),
    }
    items.insert(0, item)
    _save(_SKILLS, items)
    return item

@router.delete("/skills/{skill_id}")
async def delete_skill(skill_id: str):
    items = _load(_SKILLS)
    items = [i for i in items if i["id"] != skill_id]
    _save(_SKILLS, items)
    return {"ok": True}

@router.patch("/skills/{skill_id}")
async def update_skill(skill_id: str, body: dict):
    """Update a skill (name/description/triggers/steps/enabled). Used by
    the SkillBuilder toggle and inline edits."""
    items = _load(_SKILLS)
    for item in items:
        if item["id"] == skill_id:
            for key in ("name", "description", "triggers", "steps", "enabled"):
                if key in body:
                    item[key] = body[key]
            _save(_SKILLS, items)
            return item
    raise HTTPException(404, "Skill not found")


# ── Usage stats (record + query) ─────────────────────────────────── #

@router.post("/usage/record")
async def record_usage(body: dict):
    """Record a token usage event. Called by /api/chat handler."""
    items = _load(_USAGE)
    items.append({
        "ts": int(time.time()),
        "agent": body.get("agent", "general"),
        "model": body.get("model", "unknown"),
        "prompt": body.get("prompt", 0),
        "completion": body.get("completion", 0),
    })
    # Keep last 1000
    _save(_USAGE, items[-1000:])
    return {"ok": True}

@router.get("/usage/stats")
async def get_usage_stats():
    """Aggregated usage statistics."""
    items = _load(_USAGE)
    now = time.time()
    seven_days = [i for i in items if now - i["ts"] < 7 * 86400]
    thirty_days = [i for i in items if now - i["ts"] < 30 * 86400]

    def aggregate(rows):
        return {
            "totalTokens": sum(r["prompt"] + r["completion"] for r in rows),
            "promptTokens": sum(r["prompt"] for r in rows),
            "completionTokens": sum(r["completion"] for r in rows),
            "sessions": len(rows),
            "byAgent": _by_field(rows, "agent"),
            "byModel": _by_field(rows, "model"),
            "byDay": _by_day(rows),
        }

    def _by_field(rows, f):
        result = {}
        for r in rows:
            k = r.get(f, "unknown")
            result[k] = result.get(k, 0) + r["prompt"] + r["completion"]
        return sorted(result.items(), key=lambda x: -x[1])[:10]

    def _by_day(rows):
        result = {}
        for r in rows:
            d = time.strftime("%m-%d", time.localtime(r["ts"]))
            result[d] = result.get(d, 0) + r["prompt"] + r["completion"]
        return result

    return {
        "7d": aggregate(seven_days),
        "30d": aggregate(thirty_days),
        "total": aggregate(items),
    }
