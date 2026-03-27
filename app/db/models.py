import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    sex: Mapped[str] = mapped_column("gender", String(32), nullable=False)
    occupation: Mapped[str] = mapped_column(String(255), nullable=False)
    business_type: Mapped[str] = mapped_column(String(255), nullable=False)
    monthly_income: Mapped[float] = mapped_column(Float, nullable=False)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    nationality: Mapped[str | None] = mapped_column(String(128), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    identity_submissions: Mapped[list["IdentitySubmission"]] = relationship(
        "IdentitySubmission", back_populates="user"
    )
    trust_card: Mapped["TrustCard | None"] = relationship(
        "TrustCard", back_populates="user", uselist=False
    )


class TrustCard(Base):
    """One demo card per user; issued when live combined trust score > 45."""

    __tablename__ = "trust_cards"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False, index=True
    )
    submission_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("identity_submissions.id"), nullable=True
    )
    combined_score_at_issue: Mapped[int] = mapped_column(Integer, nullable=False)
    card_suffix: Mapped[str] = mapped_column(String(8), nullable=False)
    selected_product: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="trust_card")


class IdentitySubmission(Base):
    __tablename__ = "identity_submissions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    document_front_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    document_back_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    video_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    audio_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    document_front_content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    document_back_content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    video_content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    audio_content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)

    document_front_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    document_back_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    video_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    audio_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    eligibility_reasons: Mapped[str] = mapped_column(Text, default="[]")  # JSON array string

    trust_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    trust_reasons: Mapped[str] = mapped_column(Text, default="[]")  # JSON array string

    user: Mapped["User"] = relationship("User", back_populates="identity_submissions")
