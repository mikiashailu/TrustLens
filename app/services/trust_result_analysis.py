"""Per-modality trust breakdown from stored uploads (heuristics; swap for real ML)."""

from __future__ import annotations

from pathlib import Path

from app.db.models import IdentitySubmission, User
from app.services import document_ocr
from app.schemas.trust_api import (
    UNCERTAIN_SCORE_DEFAULT,
    CombinedTrustBreakdown,
    ModalityTrustBreakdown,
    RequirementCheck,
    TrustResultResponse,
)
from app.services.identity_files import absolute_under_uploads
from app.services.media_probe import probe_audio, probe_video


def _safe_path(rel: str | None) -> Path | None:
    if not rel:
        return None
    try:
        p = absolute_under_uploads(rel)
        return p if p.is_file() else None
    except Exception:
        return None


def _section_score(criteria: list[RequirementCheck]) -> int:
    if not criteria:
        return 0
    total = sum(c.score for c in criteria)
    return max(0, min(100, int(total / len(criteria) * 100)))


def _append_document_side_clarity(
    *,
    clarity_key: str,
    clarity_label: str,
    path: Path,
    size: int | None,
    criteria: list[RequirementCheck],
) -> None:
    ext = path.suffix.lower()
    if ext in (".jpg", ".jpeg", ".png"):
        try:
            from PIL import Image

            with Image.open(path) as im:
                w, h = im.size
                mp = (w * h) / 1_000_000
                long_edge = max(w, h)
                if mp >= 0.45:
                    clarity_score = min(1.0, mp / 1.8)
                    st = "pass"
                    detail = f"Image size {w}×{h} px (~{mp:.2f} MP)."
                elif mp >= 0.18 or long_edge >= 500:
                    clarity_score = max(UNCERTAIN_SCORE_DEFAULT, min(0.72, 0.35 + mp))
                    st = "uncertain"
                    detail = (
                        f"Image size {w}×{h} px (~{mp:.2f} MP). Readable but low resolution — "
                        "re-upload at least ~1200px on the long edge for more reliable OCR."
                    )
                else:
                    clarity_score = min(0.4, mp / 0.5)
                    st = "fail"
                    detail = f"Image very small ({w}×{h} px, ~{mp:.2f} MP); OCR will be unreliable."
                criteria.append(
                    RequirementCheck(
                        key=clarity_key,
                        label=clarity_label,
                        status=st,
                        score=clarity_score,
                        detail=detail,
                    )
                )
        except Exception as e:
            criteria.append(
                RequirementCheck(
                    key=clarity_key,
                    label=clarity_label,
                    status="uncertain",
                    score=UNCERTAIN_SCORE_DEFAULT,
                    detail=f"Could not read image: {e!s}",
                )
            )
    elif ext == ".pdf":
        clarity_score = min(1.0, (size or 0) / (800 * 1024))
        criteria.append(
            RequirementCheck(
                key=clarity_key,
                label=clarity_label,
                status="uncertain",
                score=max(UNCERTAIN_SCORE_DEFAULT, clarity_score),
                detail="PDF stored; clarity not fully analyzed without text render pipeline.",
            )
        )
    else:
        criteria.append(
            RequirementCheck(
                key=clarity_key,
                label=clarity_label,
                status="uncertain",
                score=UNCERTAIN_SCORE_DEFAULT,
                detail=f"Extension {ext}: limited server-side clarity check.",
            )
        )


def _analyze_document_sides(
    front_path: Path | None,
    back_path: Path | None,
    front_size: int | None,
    back_size: int | None,
    user: User,
) -> ModalityTrustBreakdown:
    """Front + back ID uploads; OCR is merged so fields on either side contribute to name/phone/sex."""
    criteria: list[RequirementCheck] = []

    if front_path is None:
        criteria.append(
            RequirementCheck(
                key="document_front_present",
                label="ID front image/file present",
                status="fail",
                score=0.0,
                detail="No ID front file on disk.",
            )
        )
    else:
        criteria.append(
            RequirementCheck(
                key="document_front_present",
                label="ID front image/file present",
                status="pass",
                score=1.0,
                detail="Front file exists and is readable.",
            )
        )
        _append_document_side_clarity(
            clarity_key="id_document_front_clear",
            clarity_label="ID front clear (resolution heuristic)",
            path=front_path,
            size=front_size,
            criteria=criteria,
        )

    if back_path is None:
        criteria.append(
            RequirementCheck(
                key="document_back_present",
                label="ID back image/file present",
                status="fail",
                score=0.0,
                detail="No ID back file on disk.",
            )
        )
    else:
        criteria.append(
            RequirementCheck(
                key="document_back_present",
                label="ID back image/file present",
                status="pass",
                score=1.0,
                detail="Back file exists and is readable.",
            )
        )
        _append_document_side_clarity(
            clarity_key="id_document_back_clear",
            clarity_label="ID back clear (resolution heuristic)",
            path=back_path,
            size=back_size,
            criteria=criteria,
        )

    can_ocr = (front_path is not None or back_path is not None) and document_ocr.ocr_available()
    if not can_ocr:
        skip_detail = (
            "OCR skipped: Tesseract is not installed or not on PATH (see README)."
            if not document_ocr.ocr_available()
            else "No document paths to OCR."
        )
        for key, label in (
            ("id_name_matches_full_name", "Name on ID matches full name"),
            ("id_phone_matches_phone", "Phone on ID matches registered phone"),
            ("id_sex_matches_profile", "Sex on ID matches profile"),
            ("id_dob_matches_profile", "Date of birth on ID matches profile"),
            ("id_nationality_matches_profile", "Nationality on ID matches profile"),
        ):
            criteria.append(
                RequirementCheck(
                    key=key,
                    label=label,
                    status="uncertain",
                    score=UNCERTAIN_SCORE_DEFAULT,
                    detail=skip_detail,
                )
            )
    else:
        parts: list[str] = []
        if front_path is not None:
            t = document_ocr.extract_document_text(front_path)
            if t:
                parts.append(f"--- FRONT ---\n{t}")
        if back_path is not None:
            t = document_ocr.extract_document_text(back_path)
            if t:
                parts.append(f"--- BACK ---\n{t}")
        ocr_merged = "\n".join(parts)

        n_status, n_score, n_detail = document_ocr.match_name_on_document(ocr_merged, user.full_name)
        criteria.append(
            RequirementCheck(
                key="id_name_matches_full_name",
                label="Name on ID matches full name",
                status=n_status,
                score=n_score,
                detail=n_detail,
            )
        )
        p_status, p_score, p_detail = document_ocr.match_phone_on_document(ocr_merged, user.phone)
        criteria.append(
            RequirementCheck(
                key="id_phone_matches_phone",
                label="Phone on ID matches registered phone",
                status=p_status,
                score=p_score,
                detail=p_detail,
            )
        )
        g_status, g_score, g_detail = document_ocr.match_sex_on_document(ocr_merged, user.sex)
        criteria.append(
            RequirementCheck(
                key="id_sex_matches_profile",
                label="Sex on ID matches profile",
                status=g_status,
                score=g_score,
                detail=g_detail,
            )
        )
        dob_status, dob_score, dob_detail = document_ocr.match_dob_on_document(
            ocr_merged, user.date_of_birth
        )
        criteria.append(
            RequirementCheck(
                key="id_dob_matches_profile",
                label="Date of birth on ID matches profile",
                status=dob_status,
                score=dob_score,
                detail=dob_detail,
            )
        )
        nat_status, nat_score, nat_detail = document_ocr.match_nationality_on_document(
            ocr_merged, user.nationality
        )
        criteria.append(
            RequirementCheck(
                key="id_nationality_matches_profile",
                label="Nationality on ID matches profile",
                status=nat_status,
                score=nat_score,
                detail=nat_detail,
            )
        )

    return ModalityTrustBreakdown(
        modality="document",
        criteria=criteria,
        section_score=_section_score(criteria),
    )


def _analyze_video(path: Path | None, size: int | None) -> ModalityTrustBreakdown:
    criteria: list[RequirementCheck] = []
    if path is None:
        criteria.append(
            RequirementCheck(
                key="file_present",
                label="Video file present",
                status="fail",
                score=0.0,
                detail="No video file on disk.",
            )
        )
        return ModalityTrustBreakdown(modality="video", criteria=criteria, section_score=0)

    sz = size or path.stat().st_size
    criteria.append(
        RequirementCheck(
            key="file_present",
            label="Video file present",
            status="pass",
            score=1.0,
            detail=f"Video size {sz // 1024} KB.",
        )
    )

    meta = probe_video(path)
    if meta and meta.get("width", 0) > 0:
        w, h = meta["width"], meta["height"]
        short_edge = min(w, h)
        if short_edge >= 720:
            res_score, res_st = 1.0, "pass"
            res_detail = f"Resolution {w}×{h} — meets ≥720p short-edge guideline for face review."
        elif short_edge >= 480:
            res_score, res_st = 0.72, "pass"
            res_detail = f"Resolution {w}×{h} — acceptable; prefer 720p+ short edge for face matching."
        else:
            res_score, res_st = max(0.25, short_edge / 480), "uncertain"
            res_detail = (
                f"Resolution {w}×{h} is below 480p short edge — re-record with a closer frame or higher camera quality."
            )
        criteria.append(
            RequirementCheck(
                key="video_resolution",
                label="Video resolution adequate for identity",
                status=res_st,
                score=res_score,
                detail=res_detail,
            )
        )
        dur = meta.get("duration")
        if dur is not None and dur > 0:
            if dur >= 6.0:
                d_score, d_st = 1.0, "pass"
                d_detail = f"Duration ~{dur:.1f}s — enough for liveness-style review."
            elif dur >= 3.5:
                d_score, d_st = 0.7, "pass"
                d_detail = f"Duration ~{dur:.1f}s — acceptable; 6s+ recommended if you add spoken prompts."
            else:
                d_score, d_st = max(0.2, dur / 3.5), "uncertain"
                d_detail = f"Duration ~{dur:.1f}s — too short for reliable motion/liveness; record at least ~5–8s."
            criteria.append(
                RequirementCheck(
                    key="video_duration",
                    label="Video length adequate",
                    status=d_st,
                    score=d_score,
                    detail=d_detail,
                )
            )
        else:
            criteria.append(
                RequirementCheck(
                    key="video_duration",
                    label="Video length adequate",
                    status="uncertain",
                    score=UNCERTAIN_SCORE_DEFAULT,
                    detail="Could not read duration from container; ensure the file is a normal MP4/WebM/MOV.",
                )
            )
    else:
        criteria.append(
            RequirementCheck(
                key="video_resolution",
                label="Video resolution adequate for identity",
                status="uncertain",
                score=UNCERTAIN_SCORE_DEFAULT,
                detail="OpenCV could not read this file — install opencv-python-headless or re-encode to H.264 MP4.",
            )
        )
        criteria.append(
            RequirementCheck(
                key="video_duration",
                label="Video length adequate",
                status="uncertain",
                score=UNCERTAIN_SCORE_DEFAULT,
                detail="Duration unknown without a readable video stream.",
            )
        )

    clear_score = min(1.0, sz / (2 * 1024 * 1024))
    criteria.append(
        RequirementCheck(
            key="video_container_richness",
            label="Video file size (bitrate proxy)",
            status="pass" if clear_score >= 0.35 else "uncertain",
            score=clear_score if clear_score >= 0.35 else max(UNCERTAIN_SCORE_DEFAULT, clear_score),
            detail="Larger files usually mean less aggressive compression; not a substitute for resolution/duration checks.",
        )
    )

    criteria.append(
        RequirementCheck(
            key="face_matches_id",
            label="Face on video matches ID photo",
            status="uncertain",
            score=UNCERTAIN_SCORE_DEFAULT,
            detail=(
                "Not scored on server yet. For reliable verification: single face, frontal, well-lit, no heavy filters, "
                "same person as ID photo; future: face embedding match vs document portrait."
            ),
        )
    )
    criteria.append(
        RequirementCheck(
            key="video_liveness_requirements",
            label="Liveness and motion (requirements)",
            status="uncertain",
            score=UNCERTAIN_SCORE_DEFAULT,
            detail=(
                "Not scored on server yet. Improve reliability with: follow random prompts (blink, turn head, smile), "
                "hold device steady, avoid pre-recorded playback; future: eye-gaze / depth or challenge-response SDK."
            ),
        )
    )

    return ModalityTrustBreakdown(
        modality="video",
        criteria=criteria,
        section_score=_section_score(criteria),
    )


def _analyze_audio(path: Path | None, size: int | None, user: User) -> ModalityTrustBreakdown:
    criteria: list[RequirementCheck] = []
    if path is None:
        criteria.append(
            RequirementCheck(
                key="file_present",
                label="Sound file present",
                status="fail",
                score=0.0,
                detail="No sound file on disk.",
            )
        )
        return ModalityTrustBreakdown(modality="audio", criteria=criteria, section_score=0)

    sz = size or path.stat().st_size
    criteria.append(
        RequirementCheck(
            key="file_present",
            label="Sound file present",
            status="pass",
            score=1.0,
            detail=f"Audio size {sz // 1024} KB.",
        )
    )

    am = probe_audio(path)
    if am and am.get("duration"):
        duration = float(am["duration"])
        br = am.get("bitrate")
        if duration >= 4.0:
            dur_score, dur_st = 1.0, "pass"
            dur_detail = f"Length ~{duration:.1f}s — sufficient for voice phrase / ASR."
        elif duration >= 2.0:
            dur_score, dur_st = 0.65, "pass"
            dur_detail = f"Length ~{duration:.1f}s — short; record 4–15s of clear speech for better checks."
        else:
            dur_score, dur_st = max(0.2, duration / 2.0), "uncertain"
            dur_detail = f"Length ~{duration:.1f}s — too short; speak your full name slowly for ~5s."
        if br is not None:
            if br >= 96_000:
                br_score, br_st = 1.0, "pass"
                br_detail = f"Encoding ~{br // 1000} kb/s — good for speech clarity."
            elif br >= 64_000:
                br_score, br_st = 0.75, "pass"
                br_detail = f"Encoding ~{br // 1000} kb/s — acceptable; prefer ≥96 kb/s if re-encoding."
            else:
                br_score, br_st = max(0.3, br / 96_000), "uncertain"
                br_detail = f"Encoding ~{br // 1000} kb/s — low; re-record with higher quality or less compression."
        else:
            br_score, br_st = UNCERTAIN_SCORE_DEFAULT, "uncertain"
            br_detail = "Encoding quality not reported for this format; WAV/MP3/M4A usually expose it via mutagen."
        comb_score = (dur_score + br_score) / 2.0
        comb_st = "uncertain" if (dur_st == "uncertain" or br_st == "uncertain") else "pass"
        criteria.append(
            RequirementCheck(
                key="audio_signal_quality",
                label="Voice recording quality (length & encoding)",
                status=comb_st,
                score=comb_score,
                detail=f"{dur_detail} {br_detail}",
            )
        )
    else:
        voice_clarity = min(1.0, sz / (64 * 1024))
        criteria.append(
            RequirementCheck(
                key="audio_signal_quality",
                label="Voice recording quality (length & encoding)",
                status="pass" if voice_clarity >= 0.25 else "uncertain",
                score=voice_clarity if voice_clarity >= 0.25 else max(UNCERTAIN_SCORE_DEFAULT, voice_clarity),
                detail=(
                    "Could not read media metadata (install mutagen / use MP3/M4A/OGG); "
                    "using file-size proxy only. Re-export at higher quality if possible."
                ),
            )
        )

    criteria.append(
        RequirementCheck(
            key="audio_recording_environment",
            label="Recording environment (requirements)",
            status="uncertain",
            score=UNCERTAIN_SCORE_DEFAULT,
            detail=(
                "For reliable voice checks: quiet room, phone ~15–20 cm from mouth, no music/TV, "
                "single speaker; reduces false rejects when ASR / speaker ID is enabled."
            ),
        )
    )

    criteria.append(
        RequirementCheck(
            key="voice_vs_sex",
            label="Voice compared to profile sex",
            status="uncertain",
            score=UNCERTAIN_SCORE_DEFAULT,
            detail=(
                f"Profile sex is {user.sex!r}; not classified on server. "
                "Future: pitch/timbre model with consent and locale-aware baselines."
            ),
        )
    )
    criteria.append(
        RequirementCheck(
            key="voice_name_match",
            label="Spoken name matches full name",
            status="uncertain",
            score=UNCERTAIN_SCORE_DEFAULT,
            detail=(
                f"Expected spoken name aligned with profile {user.full_name!r}. "
                "Future: on-device or server ASR + fuzzy match; until then, follow a fixed script in-app."
            ),
        )
    )

    return ModalityTrustBreakdown(
        modality="audio",
        criteria=criteria,
        section_score=_section_score(criteria),
    )


def build_trust_result(sub: IdentitySubmission, user: User) -> TrustResultResponse:
    doc_f = _safe_path(sub.document_front_path)
    doc_b_path = _safe_path(sub.document_back_path)
    vid_p = _safe_path(sub.video_path)
    snd_p = _safe_path(sub.audio_path)

    document_breakdown = _analyze_document_sides(
        doc_f,
        doc_b_path,
        sub.document_front_size_bytes,
        sub.document_back_size_bytes,
        user,
    )
    vid_b = _analyze_video(vid_p, sub.video_size_bytes)
    aud_b = _analyze_audio(snd_p, sub.audio_size_bytes, user)

    ds, vs, aus = document_breakdown.section_score, vid_b.section_score, aud_b.section_score
    combined = max(0, min(100, int(round((ds + vs + aus) / 3))))

    combined_block = CombinedTrustBreakdown(
        document_score=ds,
        video_score=vs,
        audio_score=aus,
        combined_score=combined,
    )

    return TrustResultResponse(
        submission_id=sub.id,
        document=document_breakdown,
        video=vid_b,
        audio=aud_b,
        combined=combined_block,
    )
