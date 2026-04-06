from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.db import models

router = APIRouter()


# ── Schemas ────────────────────────────────────────────────────────────────────

class UserProfileOut(BaseModel):
    id: int
    email: str
    display_name: Optional[str]
    role: str
    subscription_status: Optional[str]
    subscription_expires_at: Optional[str]


class PatchMeRequest(BaseModel):
    display_name: Optional[str] = None


class CouponCreateRequest(BaseModel):
    weekly_pool_id: int
    scenario_type: str
    picks_json: Dict[str, Any]
    column_count: Optional[int] = None


class CouponOut(BaseModel):
    id: int
    weekly_pool_id: int
    scenario_type: Optional[str]
    picks_json: Any
    column_count: Optional[int]
    submitted_at: str


class CouponWithPerformanceOut(BaseModel):
    id: int
    weekly_pool_id: int
    scenario_type: Optional[str]
    picks_json: Any
    column_count: Optional[int]
    submitted_at: str
    correct_count: Optional[int]
    total_picks: Optional[int]
    brier_score: Optional[float]
    settled_at: Optional[str]


class StatsOut(BaseModel):
    total_coupons: int
    avg_correct: Optional[float]
    avg_brier: Optional[float]


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserProfileOut)
def get_me(current_user: models.User = Depends(get_current_user)):
    expires = None
    if current_user.subscription_expires_at is not None:
        expires = current_user.subscription_expires_at.isoformat()
    return UserProfileOut(
        id=current_user.id,
        email=current_user.email,
        display_name=current_user.display_name,
        role=current_user.role,
        subscription_status=current_user.subscription_status,
        subscription_expires_at=expires,
    )


@router.patch("/me", response_model=UserProfileOut)
def patch_me(
    body: PatchMeRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.display_name is not None:
        current_user.display_name = body.display_name
    db.commit()
    db.refresh(current_user)
    expires = None
    if current_user.subscription_expires_at is not None:
        expires = current_user.subscription_expires_at.isoformat()
    return UserProfileOut(
        id=current_user.id,
        email=current_user.email,
        display_name=current_user.display_name,
        role=current_user.role,
        subscription_status=current_user.subscription_status,
        subscription_expires_at=expires,
    )


@router.post("/me/coupons", response_model=CouponOut, status_code=status.HTTP_201_CREATED)
def create_coupon(
    body: CouponCreateRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    coupon = models.UserCoupon(
        user_id=current_user.id,
        weekly_pool_id=body.weekly_pool_id,
        scenario_type=body.scenario_type,
        picks_json=body.picks_json,
        column_count=body.column_count,
    )
    db.add(coupon)
    try:
        db.commit()
        db.refresh(coupon)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bu hafta için bu senaryo zaten kaydedildi",
        )
    return CouponOut(
        id=coupon.id,
        weekly_pool_id=coupon.weekly_pool_id,
        scenario_type=coupon.scenario_type,
        picks_json=coupon.picks_json,
        column_count=coupon.column_count,
        submitted_at=coupon.submitted_at.isoformat(),
    )


@router.get("/me/coupons", response_model=List[CouponWithPerformanceOut])
def list_coupons(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    coupons = (
        db.query(models.UserCoupon)
        .filter_by(user_id=current_user.id)
        .order_by(models.UserCoupon.submitted_at.desc())
        .all()
    )
    result = []
    for c in coupons:
        perf = (
            db.query(models.UserCouponPerformance)
            .filter_by(user_coupon_id=c.id)
            .first()
        )
        result.append(CouponWithPerformanceOut(
            id=c.id,
            weekly_pool_id=c.weekly_pool_id,
            scenario_type=c.scenario_type,
            picks_json=c.picks_json,
            column_count=c.column_count,
            submitted_at=c.submitted_at.isoformat(),
            correct_count=perf.correct_count if perf else None,
            total_picks=perf.total_picks if perf else None,
            brier_score=perf.brier_score if perf else None,
            settled_at=perf.settled_at.isoformat() if perf else None,
        ))
    return result


@router.get("/me/stats", response_model=StatsOut)
def get_stats(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    total_coupons = (
        db.query(models.UserCoupon)
        .filter_by(user_id=current_user.id)
        .count()
    )
    perfs = (
        db.query(models.UserCouponPerformance)
        .filter_by(user_id=current_user.id)
        .all()
    )
    avg_correct = None
    avg_brier = None
    if perfs:
        correct_vals = [p.correct_count for p in perfs if p.correct_count is not None]
        brier_vals = [p.brier_score for p in perfs if p.brier_score is not None]
        if correct_vals:
            avg_correct = sum(correct_vals) / len(correct_vals)
        if brier_vals:
            avg_brier = sum(brier_vals) / len(brier_vals)
    return StatsOut(
        total_coupons=total_coupons,
        avg_correct=avg_correct,
        avg_brier=avg_brier,
    )
