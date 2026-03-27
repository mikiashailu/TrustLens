"""Liveness / readiness-style endpoints (no auth)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db

router = APIRouter(tags=["status"])

API_VERSION = "0.1.0"


@router.get("/health")
def health() -> dict[str, str]:
    """
    Liveness: process is up. Use for load balancers that only need to know the server responds.
    Does not check the database.
    """
    return {"status": "healthy"}


@router.get("/status")
def service_status(db: Session = Depends(get_db)) -> dict[str, str]:
    """
    Service status: app name, version, and database connectivity (readiness-style signal).
    Returns HTTP 200 with `status: "degraded"` if the DB ping fails (body still JSON for monitors).
    """
    database = "connected"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        database = "unavailable"

    overall = "ok" if database == "connected" else "degraded"
    return {
        "status": overall,
        "database": database,
        "app": settings.app_name,
        "version": API_VERSION,
    }
