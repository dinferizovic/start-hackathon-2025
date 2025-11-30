from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import workflow

settings = get_settings()

app = FastAPI(
    title="Negotiation Workflow Backend",
    version="0.1.0",
    description="Workflow orchestrator that talks to AskLio vendors and OpenAI",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}


app.include_router(workflow.router)
