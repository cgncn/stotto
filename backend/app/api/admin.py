from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.db import models
from app.api.deps import require_admin
from typing import Any
from app.schemas.admin import WeeklyImportRequest, ManualOverrideRequest

router = APIRouter()


@router.post("/weekly-import")
def trigger_weekly_import(
    body: WeeklyImportRequest,
    _: models.User = Depends(require_admin),
):
    """Trigger a weekly pool import via Celery.

    Accepts either:
      - fixture_external_ids: [123, 456, ...]   (simple list, no flags)
      - fixtures: [{external_id: 123, admin_flags: {thursday_european_away: true}}, ...]
    """
    from app.workers.tasks import task_weekly_import
    items = body.get_fixture_items()
    task = task_weekly_import.delay(
        week_code=body.week_code,
        fixtures_data=[{"external_id": it.external_id, "admin_flags": it.admin_flags} for it in items],
    )
    return {"detail": "İçe aktarma başlatıldı", "task_id": task.id}


@router.post("/recompute-week/{pool_id}")
def recompute_week(
    pool_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    from app.workers.tasks import task_baseline_scoring
    pool = db.query(models.WeeklyPool).get(pool_id)
    if not pool:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hafta bulunamadı")
    task = task_baseline_scoring.delay(pool_id)
    return {"detail": "Yeniden hesaplanıyor", "pool_id": pool_id, "task_id": task.id}


@router.post("/recompute-match/{match_id}")
def recompute_match(
    match_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Re-score a single pool match (runs the full feature + score pipeline for it)."""
    from app.features.engine import _compute_match_features
    from app.scoring.engine import _score_match

    pm = db.query(models.WeeklyPoolMatch).get(match_id)
    if not pm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Maç bulunamadı")
    if pm.is_locked:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Maç kilitli, yeniden hesaplanamaz")

    _compute_match_features(db, pm)
    db.flush()
    _score_match(db, pm)
    db.commit()
    return {"detail": "Maç yeniden hesaplandı", "match_id": match_id}


@router.post("/pools/{pool_id}/matches/{match_id}/flags")
def update_match_flags(
    pool_id: int,
    match_id: int,
    flags: dict[str, Any],
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """
    Update admin flags for a specific pool match after import.
    Supported flags:
      is_derby: bool               — mark/unmark as derby
      thursday_european_away: bool — away team played European fixture on Thursday
    """
    pm = db.query(models.WeeklyPoolMatch).filter_by(id=match_id, weekly_pool_id=pool_id).first()
    if not pm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Maç bulunamadı")
    if pm.is_locked:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Maç kilitli")

    if "is_derby" in flags:
        pm.is_derby = bool(flags.pop("is_derby"))

    if flags:
        pm.admin_flags = {**(pm.admin_flags or {}), **flags}

    db.commit()
    return {"detail": "Bayraklar güncellendi", "match_id": match_id, "is_derby": pm.is_derby, "admin_flags": pm.admin_flags}


@router.post("/manual-override")
def manual_override(
    body: ManualOverrideRequest,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    pm = db.query(models.WeeklyPoolMatch).get(body.weekly_pool_match_id)
    if not pm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Maç bulunamadı")
    if pm.is_locked:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Maç kilitli")

    previous = (
        db.query(models.MatchModelScore)
        .filter_by(weekly_pool_match_id=pm.id)
        .order_by(models.MatchModelScore.created_at.desc())
        .first()
    )

    override = models.MatchModelScore(
        weekly_pool_match_id=pm.id,
        model_version="override",
        p1=previous.p1 if previous else 0.33,
        px=previous.px if previous else 0.33,
        p2=previous.p2 if previous else 0.33,
        primary_pick=body.primary_pick,
        coverage_pick=body.coverage_pick,
        reason_codes=["MANUAL_OVERRIDE", body.reason],
    )
    db.add(override)

    change = models.ScoreChangeLog(
        weekly_pool_match_id=pm.id,
        old_primary_pick=previous.primary_pick if previous else None,
        new_primary_pick=body.primary_pick,
        old_coverage_pick=previous.coverage_pick if previous else None,
        new_coverage_pick=body.coverage_pick,
        change_reason_code="MANUAL_OVERRIDE",
        triggered_by=f"admin:{admin.email}",
    )
    db.add(change)
    db.commit()
    return {"detail": "Manuel geçersiz kılma uygulandı", "match_id": body.weekly_pool_match_id}
