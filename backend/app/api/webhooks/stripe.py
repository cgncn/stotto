from __future__ import annotations
import stripe
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timezone
from app.api.deps import get_db
from app.db import models
from app.config import settings

router = APIRouter()


def _handle_checkout_completed(obj: dict, db: Session) -> None:
    user_id = int(obj.get("metadata", {}).get("user_id", 0))
    if not user_id:
        return
    user = db.query(models.User).get(user_id)
    if not user:
        return
    user.role = models.UserRole.SUBSCRIBER
    user.stripe_customer_id = obj.get("customer")
    user.stripe_subscription_id = obj.get("subscription")
    user.subscription_status = "active"


def _handle_subscription_updated(obj: dict, db: Session) -> None:
    sub_id = obj.get("id")
    user = db.query(models.User).filter_by(stripe_subscription_id=sub_id).first()
    if not user:
        return
    user.subscription_status = obj.get("status", "unknown")
    period_end = obj.get("current_period_end")
    if period_end:
        user.subscription_expires_at = datetime.fromtimestamp(period_end, tz=timezone.utc)


def _handle_subscription_deleted(obj: dict, db: Session) -> None:
    sub_id = obj.get("id")
    user = db.query(models.User).filter_by(stripe_subscription_id=sub_id).first()
    if not user:
        return
    user.role = models.UserRole.FREE
    user.stripe_subscription_id = None
    user.subscription_status = "cancelled"


def _handle_payment_failed(obj: dict, db: Session) -> None:
    # obj is invoice object
    sub_id = obj.get("subscription")
    if not sub_id:
        return
    user = db.query(models.User).filter_by(stripe_subscription_id=sub_id).first()
    if not user:
        return
    user.subscription_status = "past_due"


EVENT_HANDLERS = {
    "checkout.session.completed": _handle_checkout_completed,
    "customer.subscription.updated": _handle_subscription_updated,
    "customer.subscription.deleted": _handle_subscription_deleted,
    "invoice.payment_failed": _handle_payment_failed,
}


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None, alias="stripe-signature"),
    db: Session = Depends(get_db),
):
    payload = await request.body()

    if settings.stripe_webhook_secret:
        try:
            stripe.api_key = settings.stripe_secret_key
            event = stripe.Webhook.construct_event(
                payload, stripe_signature, settings.stripe_webhook_secret
            )
        except (stripe.error.SignatureVerificationError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Invalid signature") from exc
    else:
        # Dev mode: no secret configured, parse raw payload
        import json
        event = json.loads(payload)

    event_id = event.get("id", "")
    if event_id and db.query(models.SubscriptionLog).filter_by(stripe_event_id=event_id).first():
        return {"status": "already_processed"}

    event_type = event.get("type", "")
    handler = EVENT_HANDLERS.get(event_type)
    if handler:
        handler(event["data"]["object"], db)

    log = models.SubscriptionLog(
        stripe_event_id=event_id or f"unknown-{event_type}",
        event_type=event_type,
        payload_json=dict(event),
    )
    db.add(log)
    db.commit()
    return {"status": "ok"}
