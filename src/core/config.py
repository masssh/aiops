"""Central configuration loaded from environment variables via pydantic-settings."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- LLM -------------------------------------------------------
    google_api_key: str = Field(default="", description="Google Gemini API key")
    gemini_model: str = Field(default="gemini-2.0-flash", description="Default Gemini model ID")

    # ---- Langfuse ---------------------------------------------------
    langfuse_host: str = Field(default="http://localhost:3000", description="Langfuse server URL")
    langfuse_public_key: str = Field(default="", description="Langfuse public key")
    langfuse_secret_key: str = Field(default="", description="Langfuse secret key")

    # ---- Logging ---------------------------------------------------
    log_level: str = Field(default="INFO", description="Global log level")
    log_file: str = Field(default="logs/aiops.log", description="Log file path (empty = disabled)")

    # ---- Debug -----------------------------------------------------
    debug_agent: str = Field(
        default="",
        description="Agent name to enable DEBUG logging for (e.g. 'github')",
    )

    @property
    def langfuse_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)


settings = Settings()
