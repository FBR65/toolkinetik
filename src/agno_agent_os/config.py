"""Configuration settings for Agno Agent OS."""

from __future__ import annotations

import os
import secrets
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_agno_api_key() -> str:
    """Generate a random API key if not set in environment."""
    return os.environ.get("AGNO_API_KEY", "") or secrets.token_urlsafe(32)


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # OpenAI / LLM settings
    OPENAI_API_BASE: str = "http://localhost:11434/v1"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"

    # Agno settings
    AGNO_API_KEY: str = ""

    # Sandbox settings
    SANDBOX_IMAGE: str = "python:3.12-slim"

    # Paths
    SKILLS_DIR: str = "skills/"
    DB_PATH: str = "data/agno_agent_os.db"

    def model_post_init(self, __context: object) -> None:  # type: ignore[override]
        """Generate AGNO_API_KEY if still empty after env load."""
        if not self.AGNO_API_KEY:
            object.__setattr__(self, "AGNO_API_KEY", secrets.token_urlsafe(32))

    @property
    def skills_path(self) -> Path:
        return Path(self.SKILLS_DIR).resolve()

    @property
    def db_full_path(self) -> Path:
        return Path(self.DB_PATH).resolve()


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings singleton."""
    return Settings()