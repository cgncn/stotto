from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_subscriber
from app.api.auth import create_access_token
from app.config import settings
from app.db import models
from app.services import iyzico_service
from app.services.iyzico_service import IyzicoError

router = APIRouter()


@router.post("/checkout")
def start_checkout(current_user: models.User = Depends(get_current_user)):
    """Return a URL for the iyzico checkout form page hosted on the backend."""
    if not settings.iyzico_api_key:
        raise HTTPException(status_code=503, detail="iyzico yapılandırılmamış")
    jwt_token = create_access_token(current_user.id)
    url = f"{settings.backend_base_url}/webhooks/iyzico/checkout-form?jwt_token={jwt_token}"
    return {"url": url}


@router.get("/status")
def subscription_status(current_user: models.User = Depends(get_current_user)):
    return {
        "role": current_user.role,
        "subscription_status": current_user.subscription_status,
        "subscription_expires_at": (
            current_user.subscription_expires_at.isoformat()
            if current_user.subscription_expires_at
            else None
        ),
    }


@router.post("/cancel")
def cancel_sub(
    current_user: models.User = Depends(require_subscriber),
    db: Session = Depends(get_db),
):
    if not current_user.iyzico_subscription_ref:
        raise HTTPException(status_code=400, detail="Aktif abonelik bulunamadı")
    try:
        ok = iyzico_service.cancel_subscription(current_user.iyzico_subscription_ref)
    except IyzicoError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    if not ok:
        raise HTTPException(status_code=502, detail="Abonelik iptal edilemedi")
    current_user.role = models.UserRole.FREE
    current_user.subscription_status = "cancelled"
    current_user.iyzico_subscription_ref = None
    db.commit()
    return {"subscription_status": "cancelled"}


@router.post("/pause")
def pause_sub(
    current_user: models.User = Depends(require_subscriber),
    db: Session = Depends(get_db),
):
    if not current_user.iyzico_subscription_ref:
        raise HTTPException(status_code=400, detail="Aktif abonelik bulunamadı")
    try:
        ok = iyzico_service.pause_subscription(current_user.iyzico_subscription_ref)
    except IyzicoError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    if not ok:
        raise HTTPException(status_code=502, detail="Abonelik durdurulamadı")
    current_user.subscription_status = "paused"
    db.commit()
    return {"subscription_status": "paused"}


@router.post("/resume")
def resume_sub(
    current_user: models.User = Depends(require_subscriber),
    db: Session = Depends(get_db),
):
    if not current_user.iyzico_subscription_ref:
        raise HTTPException(status_code=400, detail="Aktif abonelik bulunamadı")
    try:
        ok = iyzico_service.resume_subscription(current_user.iyzico_subscription_ref)
    except IyzicoError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    if not ok:
        raise HTTPException(status_code=502, detail="Abonelik devam ettirilemedi")
    current_user.subscription_status = "active"
    db.commit()
    return {"subscription_status": "active"}


@router.post("/update-card")
def update_card(current_user: models.User = Depends(require_subscriber)):
    """Return a URL for the iyzico card-update form page hosted on the backend."""
    if not current_user.iyzico_subscription_ref:
        raise HTTPException(status_code=400, detail="Aktif abonelik bulunamadı")
    jwt_token = create_access_token(current_user.id)
    url = f"{settings.backend_base_url}/webhooks/iyzico/card-update-form?jwt_token={jwt_token}"
    return {"url": url}


@router.get("/history")
def payment_history(current_user: models.User = Depends(require_subscriber)):
    if not current_user.iyzico_subscription_ref:
        return {"items": []}
    try:
        items = iyzico_service.get_payment_history(current_user.iyzico_subscription_ref)
    except IyzicoError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"items": items}
