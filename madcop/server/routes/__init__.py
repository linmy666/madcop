"""FastAPI routers split out of the monolithic app.py."""
from __future__ import annotations

from fastapi import FastAPI


def include_all_routers(app: FastAPI) -> None:
    from madcop.server.routes.memory_routes import router as memory_router
    from madcop.server.routes.skills_routes import router as skills_router
    from madcop.server.routes.settings_routes import router as settings_router

    app.include_router(settings_router)
    app.include_router(memory_router)
    app.include_router(skills_router)
