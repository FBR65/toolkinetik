"""Configuration settings for ToolKinetik."""

from __future__ import annotations

import os
import secrets
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _api_key_file() -> Path:
    """Return the path to the persisted API key file."""
    return Path("data").resolve() / ".api_key"


def _load_or_generate_api_key() -> str:
    """Load the API key from the persisted file, or generate and persist a new one."""
    # Check environment first — explicit env var always wins.
    env_key = os.environ.get("AGNO_API_KEY", "") or os.environ.get("TOOLKINETIK_API_KEY", "")
    if env_key:
        return env_key

    key_file = _api_key_file()
    # Try to read the persisted key.
    try:
        if key_file.exists():
            saved = key_file.read_text().strip()
            if saved:
                # Ensure restrictive permissions on the existing file.
                try:
                    os.chmod(key_file, 0o600)
                except OSError:
                    pass
                return saved
    except OSError:
        pass

    # Generate a new key and persist it.
    new_key = secrets.token_urlsafe(32)
    try:
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key_file.write_text(new_key)
        try:
            os.chmod(key_file, 0o600)
        except OSError:
            pass
    except OSError:
        pass  # If we can't persist, still return the generated key for this session.
    return new_key


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

    # ToolKinetik settings
    AGNO_API_KEY: str = ""
    LLM_TIMEOUT: int = 60

    # Sandbox settings
    SANDBOX_IMAGE: str = "python:3.12-slim"
    SANDBOX_TEST_IMAGE: str = "toolkinetik-sandbox:latest"

    # API URL for CLI/UI to reach the core engine
    TOOLKINETIK_API_URL: str = "http://localhost:8000"

    # Paths
    SKILLS_DIR: str = "skills/"
    DB_PATH: str = "data/toolkinetik.db"

    def model_post_init(self, __context: object) -> None:  # type: ignore[override]
        """Generate/persist AGNO_API_KEY if still empty after env load."""
        if not self.AGNO_API_KEY:
            object.__setattr__(self, "AGNO_API_KEY", _load_or_generate_api_key())

    @property
    def skills_path(self) -> Path:
        return Path(self.SKILLS_DIR).resolve()

    @property
    def db_full_path(self) -> Path:
        return Path(self.DB_PATH).resolve()

    @property
    def api_base_url(self) -> str:
        """Base URL for reaching the core engine API."""
        return self.TOOLKINETIK_API_URL


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings singleton."""
    return Settings()