"""Trust breakdown and loan eligibility for a specific identity submission."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import IdentitySubmission, User
from app.db.session import get_db
from app.schemas.trust_api import EligibilityMetrics, EligibleResponse, TrustResultResponse
from app.services.trust_engine import evaluate_financial_eligibility
from app.services.trust_result_analysis import build_trust_result

router = APIRouter(tags=["trust"])


@router.post("/trust-result", response_model=TrustResultResponse)
def trust_result(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TrustResultResponse:
    """Latest identity submission for `user_id` (same resolution as `POST /eligible`)."""
    sub = db.scalars(
        select(IdentitySubmission)
        .where(IdentitySubmission.user_id == current_user.id)
        .order_by(IdentitySubmission.created_at.desc())
    ).first()
    if sub is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No identity upload yet. POST /identity first.",
        )
    return build_trust_result(sub, current_user)


@router.post("/eligible", response_model=EligibleResponse)
def eligible_for_user(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EligibleResponse:
    """Uses the latest identity submission for `user_id` (no body)."""
    sub = db.scalars(
        select(IdentitySubmission)
        .where(IdentitySubmission.user_id == current_user.id)
        .order_by(IdentitySubmission.created_at.desc())
    ).first()
    if sub is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No identity upload yet. POST /identity first.",
        )

    tr = build_trust_result(sub, current_user)
    c = tr.combined
    payload = evaluate_financial_eligibility(
        c.combined_score,
        c.document_score,
        c.video_score,
        c.audio_score,
    )

    return EligibleResponse(
        submission_id=sub.id,
        document_score=c.document_score,
        video_score=c.video_score,
        audio_score=c.audio_score,
        combined_score=int(payload["combined_score"]),
        loan_tier=payload["loan_tier"],  # type: ignore[arg-type]
        loan_offer=str(payload["loan_offer"]),
        eligible_for_loan=bool(payload["eligible_for_loan"]),
        eligible_for_device_financing=bool(payload["eligible_for_device_financing"]),
        device_financing_offer=str(payload["device_financing_offer"]),
        eligible_for_credit_card=bool(payload["eligible_for_credit_card"]),
        credit_card_offer=str(payload["credit_card_offer"]),
        metrics=EligibilityMetrics(
            modality_min_score=int(payload["modality_min_score"]),
            modality_max_score=int(payload["modality_max_score"]),
            modality_spread=int(payload["modality_spread"]),
            weakest_modality=payload["weakest_modality"],  # type: ignore[arg-type]
            strongest_modality=payload["strongest_modality"],  # type: ignore[arg-type]
        ),
    )
