"""Trust Card — issued when combined trust score > 45; pick loan / device / invoice financing (demo)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import TrustCard, User
from app.db.session import get_db
from app.schemas.trust_card import TrustCardResponse, TrustCardSelectRequest
from app.services import trust_card_service

router = APIRouter(prefix="/trust-card", tags=["trust-card"])


@router.post("/issue", response_model=TrustCardResponse)
def issue_trust_card(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TrustCardResponse:
    """Create or refresh your Trust Card when live combined score > 45 (same trust pipeline as /eligible)."""
    return trust_card_service.issue_or_refresh_card(db, current_user)


@router.get("", response_model=TrustCardResponse)
def get_trust_card(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TrustCardResponse:
    """Return the current Trust Card if it exists and live combined score is still > 45."""
    pair = trust_card_service.live_combined_score(db, current_user)
    if pair is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No identity upload yet. POST /identity first.",
        )
    combined, _sub = pair
    trust_card_service.assert_score_allows_card(combined)

    row = db.scalars(select(TrustCard).where(TrustCard.user_id == current_user.id)).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Trust Card yet. Call POST /trust-card/issue after your combined score is above 45.",
        )
    return trust_card_service.to_response(row)


@router.post("/select", response_model=TrustCardResponse)
def select_trust_card_product(
    payload: TrustCardSelectRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TrustCardResponse:
    """Choose loan, device_financing, or invoice_financing on your issued card."""
    pair = trust_card_service.live_combined_score(db, current_user)
    if pair is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No identity upload yet. POST /identity first.",
        )
    combined, _sub = pair
    trust_card_service.assert_score_allows_card(combined)

    row = db.scalars(select(TrustCard).where(TrustCard.user_id == current_user.id)).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Trust Card yet. Call POST /trust-card/issue first.",
        )

    row.selected_product = payload.product
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return trust_card_service.to_response(row)
