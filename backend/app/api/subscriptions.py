from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.api.deps import get_current_user, require_subscriber, get_db
from app.db import models
from app.services.stripe_service import create_checkout_session, create_portal_session
from app.config import settings

router = APIRouter()


@router.post("/checkout")
def start_checkout(current_user: models.User = Depends(get_current_user)):
    if not settings.stripe_secret_key:
        raise HTTPException(503, "Stripe yapılandırılmamış")
    url = create_checkout_session(current_user.id, current_user.email)
    return {"url": url}


@router.get("/status")
def subscription_status(current_user: models.User = Depends(get_current_user)):
    return {
        "role": current_user.role,
        "subscription_status": current_user.subscription_status,
        "subscription_expires_at": (
            current_user.subscription_expires_at.isoformat()
            if current_user.subscription_expires_at else None
        ),
    }


@router.post("/portal")
def billing_portal(current_user: models.User = Depends(require_subscriber)):
    if not current_user.stripe_customer_id:
        raise HTTPException(400, "Stripe müşteri kaydı bulunamadı")
    url = create_portal_session(current_user.stripe_customer_id)
    return {"url": url}
