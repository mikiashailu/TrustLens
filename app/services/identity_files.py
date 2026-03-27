"""Save and validate identity uploads (document, video, sound)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.config import settings

ALLOWED_DOC_EXT = {".pdf", ".jpg", ".jpeg", ".png"}
ALLOWED_VIDEO_EXT = {".mp4", ".webm", ".mov", ".mkv"}
ALLOWED_AUDIO_EXT = {".mp3", ".wav", ".m4a", ".ogg", ".aac"}

MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MiB per file


def _suffix(filename: str | None) -> str:
    if not filename:
        return ""
    return Path(filename).suffix.lower()


def validate_and_save(
    upload: UploadFile,
    dest: Path,
    allowed_ext: set[str],
    label: str,
) -> tuple[int, str]:
    ext = _suffix(upload.filename)
    if ext not in allowed_ext:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{label}: unsupported type ({ext or 'no extension'}). Allowed: {sorted(allowed_ext)}",
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    content_type = upload.content_type or "application/octet-stream"
    try:
        with dest.open("wb") as out:
            while True:
                chunk = upload.file.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > MAX_FILE_BYTES:
                    dest.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"{label}: file too large (max {MAX_FILE_BYTES // (1024 * 1024)} MB).",
                    )
                out.write(chunk)
    finally:
        upload.file.close()
    if written == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{label}: empty file.",
        )
    return written, content_type


def evaluate_submission(
    doc_front_ok: bool,
    doc_back_ok: bool,
    video_ok: bool,
    sound_ok: bool,
    doc_front_size: int,
    doc_back_size: int,
    video_size: int,
    sound_size: int,
) -> tuple[bool, list[str], int | None, str | None, list[str]]:
    """Simple rules until ML is wired; drives eligible + trust fields on the row."""
    reasons: list[str] = []
    doc_ok = doc_front_ok and doc_back_ok
    if doc_front_ok:
        reasons.append("ID front document received and accepted.")
    else:
        reasons.append("ID front document missing or invalid.")
    if doc_back_ok:
        reasons.append("ID back document received and accepted.")
    else:
        reasons.append("ID back document missing or invalid.")
    if video_ok:
        reasons.append("Video file received and accepted.")
    else:
        reasons.append("Video missing or invalid.")
    if sound_ok:
        reasons.append("Sound file received and accepted.")
    else:
        reasons.append("Sound missing or invalid.")

    eligible = doc_ok and video_ok and sound_ok
    if not eligible:
        return (
            False,
            reasons,
            None,
            None,
            ["Complete ID front, ID back, video, and sound uploads to compute trust."],
        )

    # Heuristic trust from sizes (placeholder for real model)
    doc_size = doc_front_size + doc_back_size
    total_mb = (doc_size + video_size + sound_size) / (1024 * 1024)
    base = 55
    if total_mb > 0.5:
        base += 10
    if video_size > 200_000:
        base += 8
    if sound_size > 50_000:
        base += 7
    trust_score = min(100, base)
    risk_level = "low" if trust_score >= 70 else "medium" if trust_score >= 45 else "high"
    trust_reasons = [
        f"Heuristic trust score from upload payload (total ~{total_mb:.2f} MB).",
        f"Risk level: {risk_level}.",
    ]
    return True, reasons, trust_score, risk_level, trust_reasons


def rel_path(user_id: uuid.UUID, submission_id: uuid.UUID, kind: str, ext: str) -> str:
    return f"{user_id}/{submission_id}/{kind}{ext}"


def absolute_under_uploads(rel: str) -> Path:
    if not rel or ".." in Path(rel).parts:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid path")
    base = settings.upload_dir.resolve()
    full = (base / rel).resolve()
    try:
        full.relative_to(base)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid path")
    return full


def dumps_reasons(items: list[str]) -> str:
    return json.dumps(items)


def loads_reasons(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []
