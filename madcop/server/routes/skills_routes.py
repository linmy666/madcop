"""Skills list / distill / CRUD routes."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)
router = APIRouter(tags=["skills"])


@router.get("/api/skills")
async def list_skills(
    q: str = Query(default=""),
    source: str = Query(default=""),
    cwd: str = Query(default=""),
) -> dict[str, Any]:
    from madcop.memory.skill_distill import list_user_skills
    from madcop.agent.skill_forge import get_skill_store
    skills: list[dict[str, Any]] = []
    if not source or source == "user":
        for s in list_user_skills():
            if q and q.lower() not in (s["name"] + s.get("description", "")).lower():
                continue
            s["source"] = "user"
            skills.append(s)
    try:
        forge = get_skill_store()
        for s in forge.list_skills():
            if isinstance(s, dict):
                name = s.get("name", "")
                skills.append({
                    "name": name,
                    "displayName": s.get("displayName", name),
                    "description": s.get("description", ""),
                    "source": "user",
                    "userInvocable": True,
                    "version": s.get("version", "1.0"),
                    "contentLength": len(s.get("body", "")),
                    "hasDirectory": False,
                })
    except Exception as e:
        logger.debug("skills forge list: %s", e)
    if not source or source == "bundled":
        bundled = Path(__file__).resolve().parent.parent.parent.parent / "skills"
        if bundled.exists():
            for f in bundled.glob("*.md"):
                content = f.read_text(errors="ignore")
                title = f.stem
                if content.startswith("# "):
                    title = content.split("\n", 1)[0][2:].strip()
                if q and q.lower() not in (title + content).lower():
                    continue
                skills.append({
                    "name": f.stem, "displayName": title,
                    "description": content[:200], "source": "bundled",
                    "userInvocable": True, "contentLength": len(content),
                    "hasDirectory": False, "path": str(f),
                })
    return {"skills": skills, "total": len(skills)}


@router.get("/api/skills/detail")
async def get_skill_detail(
    name: str = Query(...),
    source: str = Query(default="user"),
    cwd: str = Query(default=""),
) -> dict[str, Any]:
    from madcop.memory.skill_distill import read_skill_detail
    detail = read_skill_detail(name, source)
    if detail:
        return {"detail": detail}
    raise HTTPException(404, f"Skill '{name}' not found")


@router.get("/api/skills/search")
async def search_skills(q: str = "") -> dict[str, Any]:
    from madcop.memory.skill_distill import list_user_skills
    skills = list_user_skills()
    if q:
        skills = [
            s for s in skills
            if q.lower() in s["name"].lower()
            or q.lower() in s.get("description", "").lower()
        ]
    return {"results": skills, "total": len(skills)}


@router.get("/api/skills/{name}")
async def get_skill(name: str) -> dict[str, Any]:
    from madcop.memory.skill_distill import read_skill_detail
    detail = read_skill_detail(name, "user")
    if detail:
        return detail
    from madcop.agent.skill_forge import get_skill_store
    skill = get_skill_store().get_skill(name)
    if skill:
        return {
            "meta": {
                "name": name,
                "displayName": skill.get("displayName", name),
                "description": skill.get("description", ""),
                "source": "user", "userInvocable": True,
                "contentLength": len(skill.get("body", "")),
                "hasDirectory": False,
            },
            "tree": [],
            "files": [{
                "path": str(Path.home() / ".madcop" / "skills" / f"{name}.md"),
                "content": skill.get("body", ""),
                "language": "markdown", "isEntry": True,
            }],
            "skillRoot": str(Path.home() / ".madcop" / "skills"),
        }
    raise HTTPException(404, f"Skill '{name}' not found")


@router.post("/api/skills")
async def create_skill(body: dict[str, Any]) -> dict[str, Any]:
    name = body.get("name", "unnamed")
    description = body.get("description", "")
    body_md = body.get("body", "")
    from madcop.memory.skill_distill import force_distill_skill
    topic = body.get("topic", name)
    skill_name = force_distill_skill(topic, description or topic, body_md)
    if not skill_name:
        target = Path.home() / ".madcop" / "skills" / f"{name}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"# {name}\n\n{description}\n\n{body_md}\n", encoding="utf-8")
        skill_name = target.stem
    return {
        "path": str(Path.home() / ".madcop" / "skills" / f"{skill_name}.md"),
        "created": True, "name": skill_name,
    }


@router.post("/api/skills/distill")
async def distill_skill_endpoint(body: dict[str, Any]) -> dict[str, Any]:
    from madcop.memory.skill_distill import force_distill_skill
    topic = body.get("topic", "")
    user_q = body.get("userQuery", topic)
    assistant_r = body.get("assistantResponse", "")
    if not user_q or not assistant_r:
        return {"ok": False, "error": "userQuery and assistantResponse required"}
    name = force_distill_skill(topic, user_q, assistant_r)
    if name:
        return {"ok": True, "skillName": name}
    return {"ok": False, "error": "could not distill"}


@router.delete("/api/skills/{name}")
async def delete_skill(name: str) -> dict[str, Any]:
    target = Path.home() / ".madcop" / "skills" / f"{name}.md"
    if not target.exists():
        raise HTTPException(404, f"Skill '{name}' not found")
    target.unlink()
    return {"deleted": True, "name": name}
