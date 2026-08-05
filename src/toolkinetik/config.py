"""Configuration settings for ToolKinetik."""

from __future__ import annotations

import os
import secrets
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _project_root() -> Path:
    """Return the project root directory, falling back to CWD.

    In development and Docker the project root is discoverable from
    ``__file__`` (``src/toolkinetik/config.py`` → 3 parents).  If the
    resolved path does not exist (e.g. package installed to site-packages),
    fall back to the current working directory so that ``data/`` created
    relative to CWD still works.
    """
    candidate = Path(__file__).resolve().parent.parent.parent
    return candidate if candidate.is_dir() else Path.cwd()


def _api_key_file() -> Path:
    """Return the path to the persisted API key file."""
    data_dir = _project_root() / "data"
    return data_dir / ".api_key"


def _is_dev_mode() -> bool:
    """Return True if TOOLKINETIK_DEV env var is set to a truthy value."""
    return os.environ.get("TOOLKINETIK_DEV", "").strip() in {"1", "true", "True", "TRUE", "yes"}


def _load_or_generate_api_key() -> str:
    """Load the API key from env or persisted file.

    In production (TOOLKINETIK_DEV not set): requires AGNO_API_KEY or
    TOOLKINETIK_API_KEY env var, or an existing persisted key file.
    Raises RuntimeError if none are available — never auto-generates.

    In dev mode (TOOLKINETIK_DEV=1): auto-generates and persists a new key
    if no env var or file is available.
    """
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

    # Production mode: refuse to auto-generate.
    if not _is_dev_mode():
        raise RuntimeError(
            "AGNO_API_KEY is required in production. "
            "Set it as an environment variable, or set TOOLKINETIK_DEV=1 "
            "to allow auto-generation for development."
        )

    # Dev mode: generate a new key and persist it.
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