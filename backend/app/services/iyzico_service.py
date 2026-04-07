from __future__ import annotations

import json
from typing import Optional

import iyzipay
from iyzipay.iyzipay_resource import Subscription as _BaseSubscription

from app.config import settings


class IyzicoError(Exception):
    """Raised when iyzico API returns a non-success response."""


class _ExtendedSubscription(_BaseSubscription):
    """Extends the SDK Subscription class with missing deactivate and orders methods."""

    def deactivate(self, request: dict, options: dict):
        ref = str(request.get("subscriptionReferenceCode"))
        url = self.url + "/subscriptions/" + ref + "/deactivate"
        return self.connect("POST", url, options, request)

    def orders(self, request: dict, options: dict):
        ref = str(request.get("subscriptionReferenceCode"))
        page = request.get("page", 0)
        count = request.get("count", 20)
        url = self.url + "/subscriptions/" + ref + "/orders?page=" + str(page) + "&count=" + str(count)
        return self.connect("GET", url, options)


def _options() -> dict:
    return {
        "base_url": settings.iyzico_base_url,
        "api_key": settings.iyzico_api_key,
        "secret_key": settings.iyzico_secret_key,
    }


def _parse(result) -> dict:
    """Decode an iyzipay HTTP response object to a dict."""
    return json.loads(result.read().decode("utf-8"))


def initialize_checkout(
    user_id: int,
    user_email: str,
    display_name: Optional[str],
) -> str:
    """Initialize a subscription checkout form.

    Returns the checkoutFormContent HTML string to be served to the browser.
    Sandbox uses identityNumber '11111111111' — production requires real TCKN.
    """
    name_parts = (display_name or user_email.split("@")[0]).split(" ", 1)
    first_name = name_parts[0]
    last_name = name_parts[1] if len(name_parts) > 1 else "Kullanici"

    request = {
        "locale": "tr",
        "conversationId": str(user_id),
        "callbackUrl": settings.iyzico_callback_url,
        "pricingPlanReferenceCode": settings.iyzico_subscription_plan_ref_code,
        "subscriptionInitialStatus": "ACTIVE",
        "customer": {
            "name": first_name,
            "surname": last_name,
            "email": user_email,
            "identityNumber": "11111111111",  # sandbox placeholder
            "billingAddress": {
                "contactName": display_name or user_email.split("@")[0],
                "city": "Istanbul",
                "country": "Turkey",
                "address": "Test Adres",
                "zipCode": "34000",
            },
        },
    }
    result = _parse(iyzipay.SubscriptionCheckoutForm().create(request, _options()))
    if result.get("status") != "success":
        raise IyzicoError(result.get("errorMessage", "Ödeme formu başlatılamadı"))
    return result["checkoutFormContent"]


def retrieve_checkout_result(token: str) -> dict:
    """Retrieve the checkout result for a given callback token.

    Returns dict containing subscriptionStatus, customerReferenceCode,
    subscriptionReferenceCode, conversationId, etc.
    """
    result = _parse(
        iyzipay.SubscriptionCheckoutForm().retrieve({"token": token}, _options())
    )
    if result.get("status") != "success":
        raise IyzicoError(result.get("errorMessage", "Ödeme sonucu alınamadı"))
    return result


def cancel_subscription(ref: str) -> bool:
    """Cancel an active subscription. Returns True on success."""
    result = _parse(
        iyzipay.Subscription().cancel({"subscriptionReferenceCode": ref}, _options())
    )
    return result.get("status") == "success"


def pause_subscription(ref: str) -> bool:
    """Pause (deactivate) a subscription. Returns True on success."""
    result = _parse(
        _ExtendedSubscription().deactivate({"subscriptionReferenceCode": ref}, _options())
    )
    return result.get("status") == "success"


def resume_subscription(ref: str) -> bool:
    """Resume (activate) a paused subscription. Returns True on success."""
    result = _parse(
        iyzipay.Subscription().activate({"referenceCode": ref}, _options())
    )
    return result.get("status") == "success"


def initialize_card_update(subscription_ref: str) -> str:
    """Initialize a card-update checkout form.

    Returns the checkoutFormContent HTML string.
    """
    request = {
        "locale": "tr",
        "conversationId": subscription_ref,
        "subscriptionReferenceCode": subscription_ref,
        "callbackUrl": settings.iyzico_callback_url,
    }
    result = _parse(
        iyzipay.SubscriptionCardUpdate().initialize(request, _options())
    )
    if result.get("status") != "success":
        raise IyzicoError(result.get("errorMessage", "Kart güncelleme formu başlatılamadı"))
    return result["checkoutFormContent"]


def get_payment_history(subscription_ref: str) -> list[dict]:
    """Return a list of payment order dicts for a subscription."""
    request = {
        "locale": "tr",
        "subscriptionReferenceCode": subscription_ref,
        "page": 0,
        "count": 20,
    }
    result = _parse(_ExtendedSubscription().orders(request, _options()))
    if result.get("status") != "success":
        raise IyzicoError(result.get("errorMessage", "Ödeme geçmişi alınamadı"))
    return result.get("data", {}).get("items", [])
