"""Aggregate analytics from users, identity submissions, and trust pipeline."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import IdentitySubmission, User
from app.schemas.stats_api import (
    DashboardStatsResponse,
    ModalityHealth,
    RiskBucket,
    RiskStatsResponse,
    SuspiciousPattern,
    VerificationDayVolume,
)
from app.services.trust_result_analysis import build_trust_result


def _latest_submission_per_user(db: Session) -> dict[UUID, IdentitySubmission]:
    """Most recent submission per user_id (one pass, ordered by created_at desc)."""
    rows = list(
        db.scalars(
            select(IdentitySubmission).order_by(
                IdentitySubmission.created_at.desc(),
            )
        ).all()
    )
    out: dict[UUID, IdentitySubmission] = {}
    for sub in rows:
        if sub.user_id not in out:
            out[sub.user_id] = sub
    return out


def _modality_pass_rate_pct(modality_breakdown) -> float:
    crit = modality_breakdown.criteria
    if not crit:
        return 0.0
    passes = sum(1 for c in crit if c.status == "pass")
    return round(100.0 * passes / len(crit), 2)


def _collect_trust_snapshots(db: Session) -> list[tuple[User, Any]]:
    """(user, TrustResultResponse) for each user with a latest submission; skips on error."""
    latest = _latest_submission_per_user(db)
    if not latest:
        return []
    user_ids: list[UUID] = list(latest.keys())
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(user_ids))).all()}
    out: list[tuple[User, Any]] = []
    for uid, sub in latest.items():
        user = users.get(uid)
        if user is None:
            continue
        try:
            tr = build_trust_result(sub, user)
            out.append((user, tr))
        except Exception:
            continue
    return out


def build_overview_stats(db: Session) -> DashboardStatsResponse:
    total_users = int(db.scalar(select(func.count(User.id))) or 0)

    snaps = _collect_trust_snapshots(db)
    if not snaps:
        empty_health = ModalityHealth(
            document_pass_rate_pct=0.0,
            video_pass_rate_pct=0.0,
            audio_pass_rate_pct=0.0,
        )
        vol = _verification_volume_7d(db)
        return DashboardStatsResponse(
            total_users=total_users,
            verified_prime_count=0,
            global_trust_score=0.0,
            verification_volume_7d=vol,
            modality_health=empty_health,
        )

    combined_scores = [tr.combined.combined_score for _, tr in snaps]
    prime = sum(1 for s in combined_scores if s > 80)
    global_avg = round(sum(combined_scores) / len(combined_scores), 2)

    doc_rates = [_modality_pass_rate_pct(tr.document) for _, tr in snaps]
    vid_rates = [_modality_pass_rate_pct(tr.video) for _, tr in snaps]
    aud_rates = [_modality_pass_rate_pct(tr.audio) for _, tr in snaps]

    modality_health = ModalityHealth(
        document_pass_rate_pct=round(sum(doc_rates) / len(doc_rates), 2),
        video_pass_rate_pct=round(sum(vid_rates) / len(vid_rates), 2),
        audio_pass_rate_pct=round(sum(aud_rates) / len(aud_rates), 2),
    )

    vol = _verification_volume_7d(db)

    return DashboardStatsResponse(
        total_users=total_users,
        verified_prime_count=prime,
        global_trust_score=global_avg,
        verification_volume_7d=vol,
        modality_health=modality_health,
    )


def _verification_volume_7d(db: Session) -> list[VerificationDayVolume]:
    today = datetime.utcnow().date()
    start = today - timedelta(days=6)
    slack = datetime.combine(start, datetime.min.time()) - timedelta(days=1)
    rows = list(
        db.scalars(select(IdentitySubmission).where(IdentitySubmission.created_at >= slack)).all()
    )
    counts: Counter[str] = Counter()
    for sub in rows:
        d = sub.created_at.date() if isinstance(sub.created_at, datetime) else sub.created_at
        if start <= d <= today:
            counts[d.isoformat()] += 1

    out: list[VerificationDayVolume] = []
    for i in range(7):
        d = (start + timedelta(days=i)).isoformat()
        out.append(VerificationDayVolume(date=d, count=counts.get(d, 0)))
    return out


def _risk_tier(combined: int) -> str:
    if combined <= 25:
        return "critical"
    if combined <= 40:
        return "high"
    if combined <= 65:
        return "medium"
    return "low"


def build_risk_stats(db: Session) -> RiskStatsResponse:
    snaps = _collect_trust_snapshots(db)
    if not snaps:
        return RiskStatsResponse(
            active_alerts=0,
            risk_distribution=[
                RiskBucket(level="critical", count=0),
                RiskBucket(level="high", count=0),
                RiskBucket(level="medium", count=0),
                RiskBucket(level="low", count=0),
            ],
            suspicious_patterns=[],
        )

    combined_list = [tr.combined.combined_score for _, tr in snaps]
    active_alerts = sum(1 for s in combined_list if s < 40)

    tier_counts: defaultdict[str, int] = defaultdict(int)
    for s in combined_list:
        tier_counts[_risk_tier(s)] += 1

    risk_distribution = [
        RiskBucket(level="critical", count=tier_counts["critical"]),
        RiskBucket(level="high", count=tier_counts["high"]),
        RiskBucket(level="medium", count=tier_counts["medium"]),
        RiskBucket(level="low", count=tier_counts["low"]),
    ]

    low_trust = sum(1 for s in combined_list if s < 40)
    doc_multi_fail = 0
    for _, tr in snaps:
        fails = sum(1 for c in tr.document.criteria if c.status == "fail")
        if fails >= 2:
            doc_multi_fail += 1

    rapid = _count_rapid_reupload_users(db)

    suspicious_patterns = [
        SuspiciousPattern(
            pattern="Low combined trust (latest score < 40)",
            count=low_trust,
        ),
        SuspiciousPattern(
            pattern="Document modality: 2+ failed checks on latest verification",
            count=doc_multi_fail,
        ),
        SuspiciousPattern(
            pattern="Multiple identity submissions within 24 hours (same user)",
            count=rapid,
        ),
    ]

    return RiskStatsResponse(
        active_alerts=active_alerts,
        risk_distribution=risk_distribution,
        suspicious_patterns=suspicious_patterns,
    )


def _count_rapid_reupload_users(db: Session) -> int:
    """Users with two submissions less than 24 hours apart (any pair)."""
    rows = list(
        db.scalars(
            select(IdentitySubmission).order_by(IdentitySubmission.user_id, IdentitySubmission.created_at)
        ).all()
    )
    by_user: defaultdict[UUID, list[datetime]] = defaultdict(list)
    for r in rows:
        by_user[r.user_id].append(r.created_at)

    rapid_users = 0
    for times in by_user.values():
        if len(times) < 2:
            continue
        ts = sorted(times)
        found = False
        for i in range(len(ts)):
            for j in range(i + 1, len(ts)):
                delta = ts[j] - ts[i]
                if delta.total_seconds() <= 86400:
                    found = True
                    break
            if found:
                break
        if found:
            rapid_users += 1
    return rapid_users
