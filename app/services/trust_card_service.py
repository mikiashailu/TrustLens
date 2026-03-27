"""Trust Card helpers — issue threshold and product catalog (demo, not PCI)."""

from __future__ import annotations

import secrets
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import IdentitySubmission, TrustCard, User
from app.schemas.trust_card import TrustCardProductOption, TrustCardResponse
from app.services.trust_result_analysis import build_trust_result

# Combined trust score must exceed this to issue or use the card
MIN_COMBINED_SCORE_FOR_CARD = 45


def _masked_pan(suffix: str) -> str:
    return f"•••• •••• •••• {suffix}"


def default_product_options() -> list[TrustCardProductOption]:
    return [
        TrustCardProductOption(
            key="loan",
            label="Loan",
            description="Use your trust profile toward a personal loan offer (tier from eligibility).",
        ),
        TrustCardProductOption(
            key="device_financing",
            label="Device financing",
            description="Finance a device using your verified trust score.",
        ),
        TrustCardProductOption(
            key="invoice_financing",
            label="Invoice financing",
            description="Access invoice / receivables-based financing (demo — underwriting not executed).",
        ),
    ]


def latest_submission(db: Session, user_id) -> IdentitySubmission | None:
    return db.scalars(
        select(IdentitySubmission)
        .where(IdentitySubmission.user_id == user_id)
        .order_by(IdentitySubmission.created_at.desc())
    ).first()


def live_combined_score(db: Session, user: User) -> tuple[int, IdentitySubmission] | None:
    sub = latest_submission(db, user.id)
    if sub is None:
        return None
    tr = build_trust_result(sub, user)
    return tr.combined.combined_score, sub


def assert_score_allows_card(combined: int) -> None:
    from fastapi import HTTPException, status

    if combined <= MIN_COMBINED_SCORE_FOR_CARD:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Trust Card requires combined trust score above {MIN_COMBINED_SCORE_FOR_CARD}. "
                f"Current score: {combined}."
            ),
        )


def to_response(row: TrustCard) -> TrustCardResponse:
    return TrustCardResponse(
        id=row.id,
        user_id=row.user_id,
        submission_id=row.submission_id,
        combined_score_at_issue=row.combined_score_at_issue,
        masked_number=_masked_pan(row.card_suffix),
        card_suffix=row.card_suffix,
        selected_product=row.selected_product,  # type: ignore[arg-type]
        available_products=default_product_options(),
        created_at=row.created_at,
    )


def issue_or_refresh_card(db: Session, user: User) -> TrustCardResponse:
    pair = live_combined_score(db, user)
    if pair is None:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No identity upload yet. POST /identity first.",
        )
    combined, sub = pair
    assert_score_allows_card(combined)

    row = db.scalars(select(TrustCard).where(TrustCard.user_id == user.id)).first()
    if row is None:
        suffix = f"{secrets.randbelow(10000):04d}"
        row = TrustCard(
            user_id=user.id,
            submission_id=sub.id,
            combined_score_at_issue=combined,
            card_suffix=suffix,
            selected_product=None,
        )
        db.add(row)
    else:
        row.submission_id = sub.id
        row.combined_score_at_issue = combined
        row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return to_response(row)
