from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.config import settings
from app.db import models
from app.services.iyzico_service import (
    IyzicoError,
    initialize_card_update,
    initialize_checkout,
    retrieve_checkout_result,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Internal helpers ──────────────────────────────────────────────────────────


def _user_from_jwt(token: str, db: Session) -> Optional[models.User]:
    """Decode a JWT and return the corresponding User, or None."""
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        user_id = int(payload.get("sub", 0))
        if not user_id:
            return None
        return db.query(models.User).filter(models.User.id == user_id).first()
    except (JWTError, ValueError):
        return None


def _apply_ipn_event(payload: dict, db: Session) -> None:
    """Apply an iyzico IPN lifecycle event to the DB. Idempotent."""
    sub_ref = payload.get("subscriptionReferenceCode")
    status = payload.get("subscriptionStatus")

    if not sub_ref or not status:
        return

    event_ref = f"{sub_ref}_{status}"

    # Idempotency: skip already-processed events
    if db.query(models.SubscriptionLog).filter_by(payment_event_ref=event_ref).first():
        return

    user = db.query(models.User).filter_by(iyzico_subscription_ref=sub_ref).first()

    if user:
        if status == "ACTIVE":
            user.role = models.UserRole.SUBSCRIBER
            user.subscription_status = "active"
            next_payment = payload.get("nextPaymentDate")
            if next_payment:
                try:
                    user.subscription_expires_at = datetime.fromisoformat(
                        next_payment
                    ).replace(tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    pass
        elif status == "UNPAID":
            user.subscription_status = "past_due"
        elif status == "CANCELLED":
            user.role = models.UserRole.FREE
            user.subscription_status = "cancelled"
            user.iyzico_subscription_ref = None
        elif status == "EXPIRED":
            user.role = models.UserRole.FREE
            user.subscription_status = "expired"
            user.iyzico_subscription_ref = None

    log = models.SubscriptionLog(
        payment_event_ref=event_ref,
        event_type=status,
        payload_json=payload,
        user_id=user.id if user else None,
    )
    db.add(log)
    db.commit()


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/checkout-form", response_class=HTMLResponse)
def checkout_form(
    jwt_token: str = Query(...),
    db: Session = Depends(get_db),
):
    """Serve iyzico checkout HTML page. JWT is verified server-side."""
    user = _user_from_jwt(jwt_token, db)
    if not user:
        raise HTTPException(status_code=401, detail="Geçersiz token")
    try:
        html_content = initialize_checkout(user.id, user.email, user.display_name)
    except IyzicoError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return HTMLResponse(content=html_content)


@router.get("/card-update-form", response_class=HTMLResponse)
def card_update_form(
    jwt_token: str = Query(...),
    db: Session = Depends(get_db),
):
    """Serve iyzico card-update HTML page. JWT is verified server-side."""
    user = _user_from_jwt(jwt_token, db)
    if not user:
        raise HTTPException(status_code=401, detail="Geçersiz token")
    if not user.iyzico_subscription_ref:
        raise HTTPException(status_code=400, detail="Aktif abonelik bulunamadı")
    try:
        html_content = initialize_card_update(user.iyzico_subscription_ref)
    except IyzicoError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return HTMLResponse(content=html_content)


@router.get("/callback")
def checkout_callback(
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    """iyzico redirects here after a checkout or card-update flow."""
    try:
        result = retrieve_checkout_result(token)
    except IyzicoError:
        return RedirectResponse(url=settings.iyzico_cancel_url)

    sub_status = result.get("subscriptionStatus")
    sub_ref = result.get("subscriptionReferenceCode")
    customer_ref = result.get("customerReferenceCode")
    conversation_id = result.get("conversationId")

    if sub_status == "ACTIVE" and sub_ref and conversation_id:
        try:
            user_id = int(conversation_id)
            user = db.query(models.User).filter(models.User.id == user_id).first()
            if user:
                user.role = models.UserRole.SUBSCRIBER
                user.iyzico_customer_ref = customer_ref
                user.iyzico_subscription_ref = sub_ref
                user.subscription_status = "active"
                db.commit()
        except Exception as exc:
            logger.error("Callback DB update failed: %s", exc)
            db.rollback()

    redirect_url = (
        settings.iyzico_success_url if sub_status == "ACTIVE" else settings.iyzico_cancel_url
    )
    return RedirectResponse(url=redirect_url)


@router.post("/ipn")
async def ipn_handler(
    request: Request,
    db: Session = Depends(get_db),
):
    """Receive iyzico IPN lifecycle events (ACTIVE, UNPAID, CANCELLED, EXPIRED)."""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Geçersiz payload")

    try:
        _apply_ipn_event(payload, db)
    except Exception as exc:
        logger.error("IPN processing error: %s", exc)
        db.rollback()
        raise HTTPException(status_code=500, detail="İşlem hatası")

    return {"status": "ok"}
