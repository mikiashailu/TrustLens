import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# Default 0–1 score when status is "uncertain" (no server-side ML yet)
UNCERTAIN_SCORE_DEFAULT = 0.5


class MediaPaths(BaseModel):
    """Relative storage paths under the upload root (same as DB columns)."""

    document_front_path: str | None = None
    document_back_path: str | None = None
    video_path: str | None = None
    sound_path: str | None = None


class IdentityPathsResponse(BaseModel):
    """Latest identity submission for the user (`user_id` query param — no submission_id in URL)."""

    user_id: uuid.UUID
    submission_id: uuid.UUID
    media: MediaPaths


class IdentitySubmissionMetaResponse(BaseModel):
    """Metadata after upload (POST /identity)."""

    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    document_front_content_type: str | None = None
    document_back_content_type: str | None = None
    video_content_type: str | None
    sound_content_type: str | None = None
    document_front_size_bytes: int | None = None
    document_back_size_bytes: int | None = None
    video_size_bytes: int | None
    sound_size_bytes: int | None = None
    eligible: bool
    eligibility_reasons: list[str]
    trust_score: int | None
    risk_level: str | None
    trust_reasons: list[str]


class RequirementCheck(BaseModel):
    key: str
    label: str
    status: Literal["pass", "fail", "uncertain"]
    score: float = Field(..., ge=0, le=1, description="Always set; uncertain uses a default prior (e.g. 0.5)")
    detail: str


class ModalityTrustBreakdown(BaseModel):
    modality: Literal["document", "video", "audio"]
    criteria: list[RequirementCheck]
    section_score: int = Field(..., ge=0, le=100)


class CombinedTrustBreakdown(BaseModel):
    document_score: int = Field(..., ge=0, le=100)
    video_score: int = Field(..., ge=0, le=100)
    audio_score: int = Field(..., ge=0, le=100)
    combined_score: int = Field(
        ...,
        ge=0,
        le=100,
        description="Overall score from the three modality section scores (rounded mean)",
    )


class TrustResultResponse(BaseModel):
    submission_id: uuid.UUID
    document: ModalityTrustBreakdown
    video: ModalityTrustBreakdown
    audio: ModalityTrustBreakdown
    combined: CombinedTrustBreakdown


class EligibilityMetrics(BaseModel):
    """Quick view of how balanced the three modality scores are."""

    modality_min_score: int = Field(..., ge=0, le=100)
    modality_max_score: int = Field(..., ge=0, le=100)
    modality_spread: int = Field(..., ge=0, le=100)
    weakest_modality: Literal["document", "video", "audio"]
    strongest_modality: Literal["document", "video", "audio"]


class EligibleResponse(BaseModel):
    submission_id: uuid.UUID
    document_score: int
    video_score: int
    audio_score: int
    combined_score: int = Field(..., ge=0, le=100)
    loan_tier: Literal["none", "1-5000", "5001-10000", "10001-150000"] = Field(
        ...,
        description="Principal band as a numeric range (no currency label)",
    )
    loan_offer: str = Field(..., description="Human-readable loan line for that band")
    eligible_for_loan: bool = Field(
        ...,
        description="False when combined_score ≤ 25",
    )
    eligible_for_device_financing: bool = Field(
        ...,
        description="True when combined_score ≥ 30",
    )
    device_financing_offer: str
    eligible_for_credit_card: bool = Field(
        ...,
        description="True when combined_score ≥ 50",
    )
    credit_card_offer: str
    metrics: EligibilityMetrics
