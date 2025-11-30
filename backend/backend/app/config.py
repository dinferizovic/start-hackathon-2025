from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, HttpUrl

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_ASKLIO_BASE = "https://negbot-backend-ajdxh9axb0ddb0e9.westeurope-01.azurewebsites.net/api"
DEFAULT_TEAM_ID = 444784
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


def _read_secret_file(filename: str) -> Optional[str]:
    path = ROOT_DIR / filename
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8").strip() or None


class Settings(BaseModel):
    environment: Literal["development", "production", "test"] = Field(default="development")
    asklio_base_url: HttpUrl = Field(default=DEFAULT_ASKLIO_BASE)
    asklio_team_id: int = Field(default=DEFAULT_TEAM_ID)
    openai_api_key: str = Field(default_factory=str)
    openai_model: str = Field(default=DEFAULT_OPENAI_MODEL)
    max_parallel_vendors: int = Field(default=8, description="How many vendors to contact in the first round")
    second_round_limit: int = Field(default=5, description="Top vendors that advance to round two")
    asklio_timeout_seconds: float = Field(default=30.0)
    openai_timeout_seconds: float = Field(default=30.0)

    @classmethod
    def load(cls) -> "Settings":
        openai_key = os.getenv("OPENAI_API_KEY") or _read_secret_file("OPENAI_APIKEY.txt")
        if not openai_key:
            raise RuntimeError(
                "OpenAI API key missing. Set OPENAI_API_KEY env var or add OPENAI_APIKEY.txt at repo root."
            )

        return cls(
            environment=os.getenv("ENVIRONMENT", "development"),
            asklio_base_url=os.getenv("ASKLIO_BASE_URL", DEFAULT_ASKLIO_BASE),
            asklio_team_id=int(os.getenv("ASKLIO_TEAM_ID", DEFAULT_TEAM_ID)),
            openai_api_key=openai_key,
            openai_model=os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
            max_parallel_vendors=int(os.getenv("MAX_PARALLEL_VENDORS", 8)),
            second_round_limit=int(os.getenv("SECOND_ROUND_LIMIT", 5)),
            asklio_timeout_seconds=float(os.getenv("ASKLIO_TIMEOUT_SECONDS", 30.0)),
            openai_timeout_seconds=float(os.getenv("OPENAI_TIMEOUT_SECONDS", 30.0)),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.load()
