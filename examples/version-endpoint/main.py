"""
Module: main
Role: FastAPI application with version endpoint
Source of Truth: FastAPI framework

Uses:
  - fastapi:FastAPI
  - fastapi:Depends
  - config:get_settings
  - config:Settings

Used by:
  - N/A (entry point)

Glossary: N/A (standalone example)
"""

from fastapi import Depends, FastAPI

from config import Settings, get_settings

app = FastAPI()


@app.get("/api/version")
async def version(settings: Settings = Depends(get_settings)) -> dict[str, str]:
    """
    Get application version information.

    Returns application name, version, and environment from configuration.
    Public endpoint, no authentication required.

    Args:
        settings: Application settings injected via dependency

    Returns:
        dict: Application metadata with keys "name", "version", "env"
    """
    return {
        "name": settings.name,
        "version": settings.version,
        "env": settings.env,
    }
