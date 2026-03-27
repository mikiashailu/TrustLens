"""POST /identity; GET /identity returns paths only (latest submission for user_id query param)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config import settings
from app.db.models import IdentitySubmission, User
from app.db.session import get_db
from app.schemas.trust_api import IdentityPathsResponse, IdentitySubmissionMetaResponse, MediaPaths
from app.services.identity_files import (
    ALLOWED_AUDIO_EXT,
    ALLOWED_DOC_EXT,
    ALLOWED_VIDEO_EXT,
    dumps_reasons,
    evaluate_submission,
    loads_reasons,
    rel_path,
    validate_and_save,
)

router = APIRouter(tags=["identity"])


def _to_meta(sub: IdentitySubmission) -> IdentitySubmissionMetaResponse:
    return IdentitySubmissionMetaResponse(
        id=sub.id,
        user_id=sub.user_id,
        created_at=sub.created_at,
        document_front_content_type=sub.document_front_content_type,
        document_back_content_type=sub.document_back_content_type,
        video_content_type=sub.video_content_type,
        sound_content_type=sub.audio_content_type,
        document_front_size_bytes=sub.document_front_size_bytes,
        document_back_size_bytes=sub.document_back_size_bytes,
        video_size_bytes=sub.video_size_bytes,
        sound_size_bytes=sub.audio_size_bytes,
        eligible=sub.eligible,
        eligibility_reasons=loads_reasons(sub.eligibility_reasons),
        trust_score=sub.trust_score,
        risk_level=sub.risk_level,
        trust_reasons=loads_reasons(sub.trust_reasons),
    )


@router.post("/identity", response_model=IdentitySubmissionMetaResponse)
def post_identity(
    document_front: UploadFile = File(..., description="ID front (pdf, jpg, png)"),
    document_back: UploadFile = File(..., description="ID back — address / extra fields often here (pdf, jpg, png)"),
    video: UploadFile = File(..., description="Video (mp4, webm, mov, mkv)"),
    sound: UploadFile = File(..., description="Sound / voice (mp3, wav, m4a, ogg, aac)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IdentitySubmissionMetaResponse:
    sub = IdentitySubmission()
    sub.user_id = current_user.id
    db.add(sub)
    db.flush()

    uid = current_user.id
    sid = sub.id

    df_ext = Path(document_front.filename or "").suffix.lower() or ".bin"
    db_ext = Path(document_back.filename or "").suffix.lower() or ".bin"
    vid_ext = Path(video.filename or "").suffix.lower() or ".bin"
    snd_ext = Path(sound.filename or "").suffix.lower() or ".bin"

    df_rel = rel_path(uid, sid, "document_front", df_ext)
    db_rel = rel_path(uid, sid, "document_back", db_ext)
    vid_rel = rel_path(uid, sid, "video", vid_ext)
    snd_rel = rel_path(uid, sid, "sound", snd_ext)

    df_abs = settings.upload_dir / df_rel
    db_abs = settings.upload_dir / db_rel
    vid_abs = settings.upload_dir / vid_rel
    snd_abs = settings.upload_dir / snd_rel

    doc_f_ok = doc_b_ok = vid_ok = snd_ok = False
    df_size = db_size = vid_size = snd_size = 0
    df_ct = db_ct = vid_ct = snd_ct = ""

    def _cleanup(*paths: Path) -> None:
        for p in paths:
            p.unlink(missing_ok=True)

    try:
        df_size, df_ct = validate_and_save(
            document_front, df_abs, ALLOWED_DOC_EXT, "ID front document"
        )
        doc_f_ok = True
    except HTTPException:
        db.rollback()
        raise
    try:
        db_size, db_ct = validate_and_save(document_back, db_abs, ALLOWED_DOC_EXT, "ID back document")
        doc_b_ok = True
    except HTTPException:
        db.rollback()
        _cleanup(df_abs)
        raise
    try:
        vid_size, vid_ct = validate_and_save(video, vid_abs, ALLOWED_VIDEO_EXT, "Video")
        vid_ok = True
    except HTTPException:
        db.rollback()
        _cleanup(df_abs, db_abs)
        raise
    try:
        snd_size, snd_ct = validate_and_save(sound, snd_abs, ALLOWED_AUDIO_EXT, "Sound")
        snd_ok = True
    except HTTPException:
        db.rollback()
        _cleanup(df_abs, db_abs, vid_abs)
        raise

    eligible, elig_reasons, trust_score, risk_level, trust_reasons = evaluate_submission(
        doc_f_ok,
        doc_b_ok,
        vid_ok,
        snd_ok,
        df_size,
        db_size,
        vid_size,
        snd_size,
    )

    sub.document_front_path = df_rel
    sub.document_back_path = db_rel
    sub.video_path = vid_rel
    sub.audio_path = snd_rel
    sub.document_front_content_type = df_ct
    sub.document_back_content_type = db_ct
    sub.video_content_type = vid_ct
    sub.audio_content_type = snd_ct
    sub.document_front_size_bytes = df_size
    sub.document_back_size_bytes = db_size
    sub.video_size_bytes = vid_size
    sub.audio_size_bytes = snd_size
    sub.eligible = eligible
    sub.eligibility_reasons = dumps_reasons(elig_reasons)
    sub.trust_score = trust_score
    sub.risk_level = risk_level
    sub.trust_reasons = dumps_reasons(trust_reasons)

    db.commit()
    db.refresh(sub)
    return _to_meta(sub)


@router.get("/identity", response_model=IdentityPathsResponse)
def get_identity_paths(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IdentityPathsResponse:
    """Latest submission for this user: user_id, submission_id, and relative media paths (no base64)."""
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
    return IdentityPathsResponse(
        user_id=sub.user_id,
        submission_id=sub.id,
        media=MediaPaths(
            document_front_path=sub.document_front_path,
            document_back_path=sub.document_back_path,
            video_path=sub.video_path,
            sound_path=sub.audio_path,
        ),
    )
