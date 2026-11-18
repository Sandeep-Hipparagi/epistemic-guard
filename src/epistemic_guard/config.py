from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings for Epistemic Guard.

    Model-agnostic configuration supporting local inference endpoints (Ollama, vLLM, llama.cpp)
    as well as cloud providers adhering to the OpenAI-compatible specification.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Runtime Environment
    environment: str = Field(
        default="development",
        description="Deployment environment: 'development', 'testing', or 'production'.",
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level for engine output.",
    )

    # OpenAI-Compatible Endpoint Settings
    openai_base_url: str = Field(
        default="http://localhost:11434/v1",
        description="Base URL for OpenAI-compatible inference endpoints (Ollama, vLLM, etc.).",
    )
    openai_api_key: Optional[SecretStr] = Field(
        default=None,
        description="API key for LLM inference (may be a dummy token for local inference).",
    )
    openai_model_name: str = Field(
        default="llama3.2",
        description="Model identifier to use with the inference endpoint.",
    )
    request_timeout: float = Field(
        default=30.0,
        ge=1.0,
        description="Timeout in seconds for outbound network calls and LLM inference.",
    )
    temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="Sampling temperature for deterministic generation.",
    )

    # Provenance Auditing Configuration
    source_tiers_config_path: Path = Field(
        default=Path("config/source_tiers.yaml"),
        description="Path to the deterministic source tiers YAML configuration.",
    )
    strict_timestamp_enforcement: bool = Field(
        default=True,
        description="Flag claims lacking verifiable timestamps as high-risk recycled quotes.",
    )
    require_primary_evidence_for_breaking: bool = Field(
        default=True,
        description="Require audio, video, or named outlet before clearing viral breaking claims.",
    )

    # Search & Retrieval Configuration (Phase 2)
    search_provider: str = Field(
        default="duckduckgo",
        description="Active search provider: 'duckduckgo' (default, free), 'tavily', or 'mock'.",
    )
    search_api_key: Optional[SecretStr] = Field(
        default=None,
        description="Optional API key for authenticated search providers (e.g. Tavily).",
    )
    max_search_results: int = Field(
        default=8,
        ge=1,
        le=50,
        description="Maximum search results to retrieve per provenance query.",
    )
    temporal_drift_days_threshold: int = Field(
        default=30,
        ge=1,
        description="Threshold in days to flag claims presenting old material as breaking news.",
    )

    @property
    def is_local_endpoint(self) -> bool:
        """Return True if configured for local/private inference."""
        url = self.openai_base_url.lower()
        return any(host in url for host in ("localhost", "127.0.0.1", "0.0.0.0", ":11434", ":8000", ":8080"))

    def resolve_source_tiers_path(self) -> Path:
        """Resolve the source tiers configuration path reliably."""
        path = self.source_tiers_config_path
        if path.is_absolute() and path.exists():
            return path
        # Look relative to cwd first
        cwd_path = Path.cwd() / path
        if cwd_path.exists():
            return cwd_path
        # Look relative to project root (2 levels up from this file)
        package_root = Path(__file__).resolve().parent.parent.parent
        pkg_path = package_root / path
        if pkg_path.exists():
            return pkg_path
        return cwd_path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached application settings instance."""
    return Settings()
