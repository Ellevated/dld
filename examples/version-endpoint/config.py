"""
Module: config
Role: Application settings loaded from environment variables
Source of Truth: Pydantic BaseSettings

Uses:
  - pydantic_settings:BaseSettings
  - pydantic_settings:SettingsConfigDict

Used by:
  - main:app (future)

Glossary: N/A (standalone example)
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables with APP_ prefix."""

    name: str = "myapp"
    version: str = "1.0.0"
    env: str = "dev"

    model_config = SettingsConfigDict(env_prefix="APP_")


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Settings are loaded from environment variables once and cached
    for the lifetime of the application.

    Returns:
        Settings: Application settings
    """
    return Settings()
