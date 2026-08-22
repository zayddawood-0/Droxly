from fastapi import FastAPI
from sqlalchemy import text

from app.core.database import engine

# Phase 1's own expected output (specs/roadmap.md): "empty health-check
# endpoint on FastAPI." No feature routers exist yet — those land with the
# phases that own them (auth, documents, ...).
app = FastAPI(title="Doxly API")


@app.get("/health")
async def health() -> dict[str, str]:
    """
    DB connectivity + basic liveness, no auth required, no sensitive data
    returned (specs/deployment.md §3) — polled by the platform orchestrator
    to route traffic only to ready replicas.
    """
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return {"status": "ok"}
