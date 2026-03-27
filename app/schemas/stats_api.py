"""Analytics & risk dashboard API schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class VerificationDayVolume(BaseModel):
    """Single day in the 7-day verification trend."""

    date: str = Field(..., description="ISO date YYYY-MM-DD")
    count: int = Field(..., ge=0)


class ModalityHealth(BaseModel):
    """Average pass-rate (%) per modality across latest verification per user."""

    document_pass_rate_pct: float = Field(..., ge=0, le=100)
    video_pass_rate_pct: float = Field(..., ge=0, le=100)
    audio_pass_rate_pct: float = Field(..., ge=0, le=100)


class DashboardStatsResponse(BaseModel):
    total_users: int = Field(..., ge=0)
    verified_prime_count: int = Field(
        ...,
        ge=0,
        description="Users whose latest combined trust score is strictly greater than 80.",
    )
    global_trust_score: float = Field(
        ...,
        ge=0,
        le=100,
        description="Mean combined score (0–100) over users with at least one identity submission.",
    )
    verification_volume_7d: list[VerificationDayVolume]
    modality_health: ModalityHealth


class RiskBucket(BaseModel):
    level: str = Field(..., description="critical | high | medium | low")
    count: int = Field(..., ge=0)


class SuspiciousPattern(BaseModel):
    pattern: str
    count: int = Field(..., ge=0)


class RiskStatsResponse(BaseModel):
    active_alerts: int = Field(
        ...,
        ge=0,
        description="Users with latest combined trust < 40 (investigation queue heuristic).",
    )
    risk_distribution: list[RiskBucket]
    suspicious_patterns: list[SuspiciousPattern]
