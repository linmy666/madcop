"""FastAPI routers split out of the monolithic app.py."""
from __future__ import annotations

from fastapi import FastAPI


def include_all_routers(app: FastAPI) -> None:
    from madcop.server.routes.memory_routes import router as memory_router
    from madcop.server.routes.skills_routes import router as skills_router
    from madcop.server.routes.settings_routes import router as settings_router
    from madcop.server.routes.meta_harness_routes import router as meta_harness_router

    app.include_router(settings_router)
    app.include_router(memory_router)
    app.include_router(skills_router)
    app.include_router(meta_harness_router)

    # Sprint 6 — Knowledge Canvas: brain graph API
    from madcop.server.routes.brain_graph import router as brain_graph_router
    app.include_router(brain_graph_router)

    # Sprint 5 — Proactive Observer: file/terminal nudge endpoint
    from madcop.server.routes.proactive_routes import router as proactive_router
    app.include_router(proactive_router)

    # Design workshop: hybrid PM prototype tool (NL generate + manual edit)
    from madcop.server.routes.design_routes import router as design_router
    app.include_router(design_router)
