"""Trust Card — issued when combined trust score > 45; user picks a financing product (demo)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

CardProduct = Literal["loan", "device_financing", "invoice_financing"]


class TrustCardProductOption(BaseModel):
    key: CardProduct
    label: str
    description: str


class TrustCardResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    submission_id: uuid.UUID | None
    combined_score_at_issue: int = Field(..., ge=0, le=100)
    masked_number: str = Field(..., description="Display-only mock PAN")
    card_suffix: str
    selected_product: CardProduct | None
    available_products: list[TrustCardProductOption]
    created_at: datetime

    model_config = {"from_attributes": True}


class TrustCardSelectRequest(BaseModel):
    product: CardProduct
