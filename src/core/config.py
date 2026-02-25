"""Central configuration loaded from environment variables via pydantic-settings."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- LLM provider ----------------------------------------------
    llm_provider: Literal["google", "openai"] = Field(
        default="google",
        description="LLM provider to use: 'google' (Gemini) or 'openai'",
    )

    # ---- Google Gemini ---------------------------------------------
    google_api_key: str = Field(default="", description="Google Gemini API key")
    gemini_model: str = Field(default="gemini-2.0-flash", description="Default Gemini model ID")

    # ---- OpenAI ----------------------------------------------------
    openai_api_key: str = Field(default="", description="OpenAI API key")
    openai_model: str = Field(default="gpt-4o-mini", description="Default OpenAI model ID")
    openai_base_url: str = Field(default="", description="OpenAI-compatible base URL (optional)")

    @model_validator(mode="after")
    def _validate_provider_keys(self) -> "Settings":
        if self.llm_provider == "google" and not self.google_api_key:
            raise ValueError(
                "GOOGLE_API_KEY is required when LLM_PROVIDER=google. "
                "Copy .env.example to .env and fill in your API key."
            )
        if self.llm_provider == "openai" and not self.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY is required when LLM_PROVIDER=openai. "
                "Copy .env.example to .env and fill in your API key."
            )
        return self

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

    @property
    def active_model(self) -> str:
        """Return the model ID for the active provider."""
        if self.llm_provider == "openai":
            return self.openai_model
        return self.gemini_model


settings = Settings()
