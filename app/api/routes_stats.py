"""Dashboard analytics & risk stats (admin-style; same auth as other protected routes)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.schemas.stats_api import DashboardStatsResponse, RiskStatsResponse
from app.services.stats_service import build_overview_stats, build_risk_stats

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/overview", response_model=DashboardStatsResponse)
def stats_overview(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DashboardStatsResponse:
    """
    High-level KPIs for the admin dashboard.
    Requires `user_id` query param (demo auth). Production should restrict to admin roles.
    """
    return build_overview_stats(db)


@router.get("/risk", response_model=RiskStatsResponse)
def stats_risk(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RiskStatsResponse:
    """
    Risk monitoring aggregates. Heuristic counts — tune thresholds in `stats_service`.
    """
    return build_risk_stats(db)
