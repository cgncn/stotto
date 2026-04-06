from __future__ import annotations
import stripe
from app.config import settings


def create_checkout_session(user_id: int, user_email: str) -> str:
    stripe.api_key = settings.stripe_secret_key
    session = stripe.checkout.Session.create(
        customer_email=user_email,
        line_items=[{"price": settings.stripe_price_id, "quantity": 1}],
        mode="subscription",
        success_url=settings.stripe_success_url,
        cancel_url=settings.stripe_cancel_url,
        metadata={"user_id": str(user_id)},
    )
    return session.url


def create_portal_session(customer_id: str) -> str:
    stripe.api_key = settings.stripe_secret_key
    session = stripe.billing_portal.Session.create(customer=customer_id)
    return session.url
