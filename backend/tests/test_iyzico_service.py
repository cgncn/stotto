"""Unit tests for iyzico_service — all iyzipay SDK calls are mocked."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

# ── Helper ────────────────────────────────────────────────────────────────────

def _mock_iyzipay_response(data: dict) -> MagicMock:
    """Return a mock that behaves like an iyzipay HTTP response object."""
    mock = MagicMock()
    mock.read.return_value = json.dumps(data).encode("utf-8")
    return mock


# ── initialize_checkout ───────────────────────────────────────────────────────

def test_initialize_checkout_returns_html():
    from app.services.iyzico_service import initialize_checkout

    fake_html = "<form>iyzico form</form>"
    response = _mock_iyzipay_response({"status": "success", "checkoutFormContent": fake_html})

    with patch("iyzipay.SubscriptionCheckoutForm") as MockCls:
        MockCls.return_value.create.return_value = response
        result = initialize_checkout(user_id=1, user_email="test@example.com", display_name="Test User")

    assert result == fake_html


def test_initialize_checkout_raises_on_failure():
    from app.services.iyzico_service import initialize_checkout, IyzicoError

    response = _mock_iyzipay_response({"status": "failure", "errorMessage": "Plan not found"})

    with patch("iyzipay.SubscriptionCheckoutForm") as MockCls:
        MockCls.return_value.create.return_value = response
        with pytest.raises(IyzicoError, match="Plan not found"):
            initialize_checkout(user_id=1, user_email="a@b.com", display_name=None)


# ── retrieve_checkout_result ──────────────────────────────────────────────────

def test_retrieve_checkout_result_returns_dict():
    from app.services.iyzico_service import retrieve_checkout_result

    payload = {
        "status": "success",
        "subscriptionStatus": "ACTIVE",
        "customerReferenceCode": "cust-ref-001",
        "subscriptionReferenceCode": "sub-ref-001",
        "conversationId": "42",
    }
    response = _mock_iyzipay_response(payload)

    with patch("iyzipay.SubscriptionCheckoutForm") as MockCls:
        MockCls.return_value.retrieve.return_value = response
        result = retrieve_checkout_result("token-abc")

    assert result["subscriptionReferenceCode"] == "sub-ref-001"
    assert result["conversationId"] == "42"


def test_retrieve_checkout_result_raises_on_failure():
    from app.services.iyzico_service import retrieve_checkout_result, IyzicoError

    response = _mock_iyzipay_response({"status": "failure", "errorMessage": "Token expired"})

    with patch("iyzipay.SubscriptionCheckoutForm") as MockCls:
        MockCls.return_value.retrieve.return_value = response
        with pytest.raises(IyzicoError, match="Token expired"):
            retrieve_checkout_result("bad-token")


# ── cancel_subscription ───────────────────────────────────────────────────────

def test_cancel_subscription_returns_true_on_success():
    from app.services.iyzico_service import cancel_subscription

    response = _mock_iyzipay_response({"status": "success"})

    with patch("iyzipay.Subscription") as MockCls:
        MockCls.return_value.cancel.return_value = response
        assert cancel_subscription("sub-ref-001") is True


def test_cancel_subscription_returns_false_on_failure():
    from app.services.iyzico_service import cancel_subscription

    response = _mock_iyzipay_response({"status": "failure"})

    with patch("iyzipay.Subscription") as MockCls:
        MockCls.return_value.cancel.return_value = response
        assert cancel_subscription("sub-ref-001") is False


# ── pause_subscription ────────────────────────────────────────────────────────

def test_pause_subscription_returns_true_on_success():
    from app.services.iyzico_service import pause_subscription

    response = _mock_iyzipay_response({"status": "success"})

    with patch("iyzipay.Subscription") as MockCls:
        MockCls.return_value.deactivate.return_value = response
        assert pause_subscription("sub-ref-001") is True


# ── resume_subscription ───────────────────────────────────────────────────────

def test_resume_subscription_returns_true_on_success():
    from app.services.iyzico_service import resume_subscription

    response = _mock_iyzipay_response({"status": "success"})

    with patch("iyzipay.Subscription") as MockCls:
        MockCls.return_value.activate.return_value = response
        assert resume_subscription("sub-ref-001") is True


# ── initialize_card_update ────────────────────────────────────────────────────

def test_initialize_card_update_returns_html():
    from app.services.iyzico_service import initialize_card_update

    fake_html = "<form>card update form</form>"
    response = _mock_iyzipay_response({"status": "success", "checkoutFormContent": fake_html})

    with patch("iyzipay.SubscriptionCardUpdate") as MockCls:
        MockCls.return_value.initialize.return_value = response
        result = initialize_card_update("sub-ref-001")

    assert result == fake_html


def test_initialize_card_update_raises_on_failure():
    from app.services.iyzico_service import initialize_card_update, IyzicoError

    response = _mock_iyzipay_response({"status": "failure", "errorMessage": "Subscription not found"})

    with patch("iyzipay.SubscriptionCardUpdate") as MockCls:
        MockCls.return_value.initialize.return_value = response
        with pytest.raises(IyzicoError, match="Subscription not found"):
            initialize_card_update("bad-ref")


# ── get_payment_history ───────────────────────────────────────────────────────

def test_get_payment_history_returns_items():
    from app.services.iyzico_service import get_payment_history

    items = [{"price": 49.90, "status": "PAID"}, {"price": 49.90, "status": "PAID"}]
    response = _mock_iyzipay_response({"status": "success", "data": {"items": items}})

    with patch("iyzipay.Subscription") as MockCls:
        MockCls.return_value.orders.return_value = response
        result = get_payment_history("sub-ref-001")

    assert len(result) == 2
    assert result[0]["price"] == 49.90


def test_get_payment_history_returns_empty_list_on_no_items():
    from app.services.iyzico_service import get_payment_history

    response = _mock_iyzipay_response({"status": "success", "data": {"items": []}})

    with patch("iyzipay.Subscription") as MockCls:
        MockCls.return_value.orders.return_value = response
        result = get_payment_history("sub-ref-001")

    assert result == []
