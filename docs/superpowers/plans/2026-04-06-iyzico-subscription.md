# iyzico Subscription Migration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Stripe subscription system end-to-end with iyzico, add a self-built inline subscription management section to `/hesap`, and preserve all role/gating/coupon logic unchanged.

**Architecture:** DB columns renamed via Alembic 003_; new `iyzico_service.py` wraps the `iyzipay` SDK; `webhooks/iyzico.py` handles the redirect callback and IPN events; `subscriptions.py` grows cancel/pause/resume/history/update-card endpoints; the `/hesap` page gains an inline Abonelik section.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy / Alembic / iyzipay SDK; Next.js 14 / Tailwind CSS / TypeScript

---

## File Map

| Action | Path |
|--------|------|
| Create | `backend/alembic/versions/003_iyzico_columns.py` |
| Modify | `backend/app/db/models.py` |
| Modify | `backend/app/config.py` |
| Modify | `backend/requirements.txt` |
| Create | `backend/app/services/iyzico_service.py` |
| Create | `backend/tests/test_iyzico_service.py` |
| Create | `backend/app/api/webhooks/iyzico.py` |
| Create | `backend/tests/test_iyzico_webhook.py` |
| Modify | `backend/app/api/subscriptions.py` |
| Modify | `backend/app/main.py` |
| Delete | `backend/app/services/stripe_service.py` |
| Delete | `backend/app/api/webhooks/stripe.py` |
| Modify | `frontend/src/app/hesap/page.tsx` |
| Modify | `frontend/src/app/uye-ol/page.tsx` |

---

## Task 1: Alembic Migration 003_ — Rename Stripe columns to iyzico

**Files:**
- Create: `backend/alembic/versions/003_iyzico_columns.py`

- [ ] **Step 1: Write the migration file**

```python
# backend/alembic/versions/003_iyzico_columns.py
"""iyzico_columns

Revision ID: 003
Revises: 002
Create Date: 2026-04-06 00:00:00.000000
"""
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop old unique constraints before renaming
    op.drop_constraint("uq_users_stripe_customer_id", "users", type_="unique")
    op.drop_constraint("uq_users_stripe_subscription_id", "users", type_="unique")

    # Rename columns on users table
    op.alter_column("users", "stripe_customer_id", new_column_name="iyzico_customer_ref")
    op.alter_column("users", "stripe_subscription_id", new_column_name="iyzico_subscription_ref")

    # Re-create unique constraints with new names
    op.create_unique_constraint("uq_users_iyzico_customer_ref", "users", ["iyzico_customer_ref"])
    op.create_unique_constraint("uq_users_iyzico_subscription_ref", "users", ["iyzico_subscription_ref"])

    # Rename column on subscription_log table
    op.alter_column("subscription_log", "stripe_event_id", new_column_name="payment_event_ref")


def downgrade() -> None:
    op.alter_column("subscription_log", "payment_event_ref", new_column_name="stripe_event_id")

    op.drop_constraint("uq_users_iyzico_subscription_ref", "users", type_="unique")
    op.drop_constraint("uq_users_iyzico_customer_ref", "users", type_="unique")

    op.alter_column("users", "iyzico_subscription_ref", new_column_name="stripe_subscription_id")
    op.alter_column("users", "iyzico_customer_ref", new_column_name="stripe_customer_id")

    op.create_unique_constraint("uq_users_stripe_customer_id", "users", ["stripe_customer_id"])
    op.create_unique_constraint("uq_users_stripe_subscription_id", "users", ["stripe_subscription_id"])
```

- [ ] **Step 2: Apply migration**

```bash
cd backend && alembic upgrade head
```

Expected output ends with:
```
Running upgrade 002 -> 003, iyzico_columns
```

- [ ] **Step 3: Verify columns in DB**

```bash
cd backend && python -c "
from sqlalchemy import create_engine, inspect
from app.config import settings
engine = create_engine(settings.database_url)
cols = {c['name'] for c in inspect(engine).get_columns('users')}
assert 'iyzico_customer_ref' in cols, 'iyzico_customer_ref missing'
assert 'iyzico_subscription_ref' in cols, 'iyzico_subscription_ref missing'
assert 'stripe_customer_id' not in cols, 'stripe_customer_id still present'
log_cols = {c['name'] for c in inspect(engine).get_columns('subscription_log')}
assert 'payment_event_ref' in log_cols, 'payment_event_ref missing'
assert 'stripe_event_id' not in log_cols, 'stripe_event_id still present'
print('Migration 003 verified OK')
"
```

Expected: `Migration 003 verified OK`

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/003_iyzico_columns.py
git commit -m "feat: alembic migration 003 — rename stripe columns to iyzico"
```

---

## Task 2: Update models.py, config.py, requirements.txt

**Files:**
- Modify: `backend/app/db/models.py`
- Modify: `backend/app/config.py`
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Update User model columns in models.py**

In `backend/app/db/models.py`, replace these two lines inside the `User` class:
```python
    stripe_customer_id = Column(String(100))
    stripe_subscription_id = Column(String(100))
```
With:
```python
    iyzico_customer_ref = Column(String(100))
    iyzico_subscription_ref = Column(String(100))
```

- [ ] **Step 2: Update SubscriptionLog model in models.py**

In `backend/app/db/models.py`, replace this line inside `SubscriptionLog`:
```python
    stripe_event_id = Column(String(100), nullable=False, unique=True)
```
With:
```python
    payment_event_ref = Column(String(200), nullable=False, unique=True)
```

- [ ] **Step 3: Replace config.py Stripe settings with iyzico settings**

Replace the entire Stripe block in `backend/app/config.py`:
```python
    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_id: str = ""
    stripe_success_url: str = "http://localhost:3000/hesap?success=1"
    stripe_cancel_url: str = "http://localhost:3000/uye-ol?cancelled=1"
```
With:
```python
    # iyzico
    iyzico_api_key: str = ""
    iyzico_secret_key: str = ""
    iyzico_base_url: str = "https://sandbox-api.iyzipay.com"
    iyzico_subscription_plan_ref_code: str = ""
    iyzico_callback_url: str = "http://localhost:8000/webhooks/iyzico/callback"
    iyzico_success_url: str = "http://localhost:3000/hesap?success=1"
    iyzico_cancel_url: str = "http://localhost:3000/uye-ol?cancelled=1"
    backend_base_url: str = "http://localhost:8000"
```

- [ ] **Step 4: Replace stripe in requirements.txt**

In `backend/requirements.txt`, replace:
```
# Stripe
stripe>=7.0.0
```
With:
```
# iyzico
iyzipay>=2.0.0
```

- [ ] **Step 5: Install updated dependencies**

```bash
cd backend && pip install -r requirements.txt
```

Expected: `iyzipay` installs successfully.

- [ ] **Step 6: Run existing tests to confirm no regressions**

```bash
cd backend && pytest tests/ --ignore=tests/test_api_smoke.py -q
```

Expected: all 43 tests pass (test_api_smoke.py ignored since it needs the DB).

- [ ] **Step 7: Commit**

```bash
git add backend/app/db/models.py backend/app/config.py backend/requirements.txt
git commit -m "feat: rename stripe→iyzico columns in models and config; swap pip dependency"
```

---

## Task 3: Create iyzico_service.py (TDD)

**Files:**
- Create: `backend/app/services/iyzico_service.py`
- Create: `backend/tests/test_iyzico_service.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_iyzico_service.py
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

    with patch("iyzipay.SubscriptionCheckoutFormInitialize") as MockCls:
        MockCls.return_value.create.return_value = response
        result = initialize_checkout(user_id=1, user_email="test@example.com", display_name="Test User")

    assert result == fake_html


def test_initialize_checkout_raises_on_failure():
    from app.services.iyzico_service import initialize_checkout, IyzicoError

    response = _mock_iyzipay_response({"status": "failure", "errorMessage": "Plan not found"})

    with patch("iyzipay.SubscriptionCheckoutFormInitialize") as MockCls:
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

    with patch("iyzipay.SubscriptionCheckoutFormResult") as MockCls:
        MockCls.return_value.retrieve.return_value = response
        result = retrieve_checkout_result("token-abc")

    assert result["subscriptionReferenceCode"] == "sub-ref-001"
    assert result["conversationId"] == "42"


def test_retrieve_checkout_result_raises_on_failure():
    from app.services.iyzico_service import retrieve_checkout_result, IyzicoError

    response = _mock_iyzipay_response({"status": "failure", "errorMessage": "Token expired"})

    with patch("iyzipay.SubscriptionCheckoutFormResult") as MockCls:
        MockCls.return_value.retrieve.return_value = response
        with pytest.raises(IyzicoError, match="Token expired"):
            retrieve_checkout_result("bad-token")


# ── cancel_subscription ───────────────────────────────────────────────────────

def test_cancel_subscription_returns_true_on_success():
    from app.services.iyzico_service import cancel_subscription

    response = _mock_iyzipay_response({"status": "success"})

    with patch("iyzipay.SubscriptionCancel") as MockCls:
        MockCls.return_value.create.return_value = response
        assert cancel_subscription("sub-ref-001") is True


def test_cancel_subscription_returns_false_on_failure():
    from app.services.iyzico_service import cancel_subscription

    response = _mock_iyzipay_response({"status": "failure"})

    with patch("iyzipay.SubscriptionCancel") as MockCls:
        MockCls.return_value.create.return_value = response
        assert cancel_subscription("sub-ref-001") is False


# ── pause_subscription ────────────────────────────────────────────────────────

def test_pause_subscription_returns_true_on_success():
    from app.services.iyzico_service import pause_subscription

    response = _mock_iyzipay_response({"status": "success"})

    with patch("iyzipay.SubscriptionDeActivate") as MockCls:
        MockCls.return_value.update.return_value = response
        assert pause_subscription("sub-ref-001") is True


# ── resume_subscription ───────────────────────────────────────────────────────

def test_resume_subscription_returns_true_on_success():
    from app.services.iyzico_service import resume_subscription

    response = _mock_iyzipay_response({"status": "success"})

    with patch("iyzipay.SubscriptionActivate") as MockCls:
        MockCls.return_value.update.return_value = response
        assert resume_subscription("sub-ref-001") is True


# ── initialize_card_update ────────────────────────────────────────────────────

def test_initialize_card_update_returns_html():
    from app.services.iyzico_service import initialize_card_update

    fake_html = "<form>card update form</form>"
    response = _mock_iyzipay_response({"status": "success", "checkoutFormContent": fake_html})

    with patch("iyzipay.SubscriptionCardUpdateCheckoutFormInitialize") as MockCls:
        MockCls.return_value.create.return_value = response
        result = initialize_card_update("sub-ref-001")

    assert result == fake_html


def test_initialize_card_update_raises_on_failure():
    from app.services.iyzico_service import initialize_card_update, IyzicoError

    response = _mock_iyzipay_response({"status": "failure", "errorMessage": "Subscription not found"})

    with patch("iyzipay.SubscriptionCardUpdateCheckoutFormInitialize") as MockCls:
        MockCls.return_value.create.return_value = response
        with pytest.raises(IyzicoError, match="Subscription not found"):
            initialize_card_update("bad-ref")


# ── get_payment_history ───────────────────────────────────────────────────────

def test_get_payment_history_returns_items():
    from app.services.iyzico_service import get_payment_history

    items = [{"price": 49.90, "status": "PAID"}, {"price": 49.90, "status": "PAID"}]
    response = _mock_iyzipay_response({"status": "success", "data": {"items": items}})

    with patch("iyzipay.SubscriptionOrders") as MockCls:
        MockCls.return_value.retrieve.return_value = response
        result = get_payment_history("sub-ref-001")

    assert len(result) == 2
    assert result[0]["price"] == 49.90


def test_get_payment_history_returns_empty_list_on_no_items():
    from app.services.iyzico_service import get_payment_history

    response = _mock_iyzipay_response({"status": "success", "data": {"items": []}})

    with patch("iyzipay.SubscriptionOrders") as MockCls:
        MockCls.return_value.retrieve.return_value = response
        result = get_payment_history("sub-ref-001")

    assert result == []
```

- [ ] **Step 2: Run tests to confirm they all fail**

```bash
cd backend && pytest tests/test_iyzico_service.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'app.services.iyzico_service'`

- [ ] **Step 3: Implement iyzico_service.py**

```python
# backend/app/services/iyzico_service.py
from __future__ import annotations

import json
from typing import Optional

import iyzipay

from app.config import settings


class IyzicoError(Exception):
    """Raised when iyzico API returns a non-success response."""


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
    result = _parse(iyzipay.SubscriptionCheckoutFormInitialize().create(request, _options()))
    if result.get("status") != "success":
        raise IyzicoError(result.get("errorMessage", "Ödeme formu başlatılamadı"))
    return result["checkoutFormContent"]


def retrieve_checkout_result(token: str) -> dict:
    """Retrieve the checkout result for a given callback token.

    Returns dict containing subscriptionStatus, customerReferenceCode,
    subscriptionReferenceCode, conversationId, etc.
    """
    result = _parse(
        iyzipay.SubscriptionCheckoutFormResult().retrieve({"token": token}, _options())
    )
    if result.get("status") != "success":
        raise IyzicoError(result.get("errorMessage", "Ödeme sonucu alınamadı"))
    return result


def cancel_subscription(ref: str) -> bool:
    """Cancel an active subscription. Returns True on success."""
    result = _parse(
        iyzipay.SubscriptionCancel().create({"subscriptionReferenceCode": ref}, _options())
    )
    return result.get("status") == "success"


def pause_subscription(ref: str) -> bool:
    """Pause (deactivate) a subscription. Returns True on success."""
    result = _parse(
        iyzipay.SubscriptionDeActivate().update({"subscriptionReferenceCode": ref}, _options())
    )
    return result.get("status") == "success"


def resume_subscription(ref: str) -> bool:
    """Resume (activate) a paused subscription. Returns True on success."""
    result = _parse(
        iyzipay.SubscriptionActivate().update({"subscriptionReferenceCode": ref}, _options())
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
        iyzipay.SubscriptionCardUpdateCheckoutFormInitialize().create(request, _options())
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
    result = _parse(iyzipay.SubscriptionOrders().retrieve(request, _options()))
    if result.get("status") != "success":
        raise IyzicoError(result.get("errorMessage", "Ödeme geçmişi alınamadı"))
    return result.get("data", {}).get("items", [])
```

- [ ] **Step 4: Run tests to confirm they all pass**

```bash
cd backend && pytest tests/test_iyzico_service.py -v
```

Expected:
```
PASSED tests/test_iyzico_service.py::test_initialize_checkout_returns_html
PASSED tests/test_iyzico_service.py::test_initialize_checkout_raises_on_failure
PASSED tests/test_iyzico_service.py::test_retrieve_checkout_result_returns_dict
PASSED tests/test_iyzico_service.py::test_retrieve_checkout_result_raises_on_failure
PASSED tests/test_iyzico_service.py::test_cancel_subscription_returns_true_on_success
PASSED tests/test_iyzico_service.py::test_cancel_subscription_returns_false_on_failure
PASSED tests/test_iyzico_service.py::test_pause_subscription_returns_true_on_success
PASSED tests/test_iyzico_service.py::test_resume_subscription_returns_true_on_success
PASSED tests/test_iyzico_service.py::test_initialize_card_update_returns_html
PASSED tests/test_iyzico_service.py::test_initialize_card_update_raises_on_failure
PASSED tests/test_iyzico_service.py::test_get_payment_history_returns_items
PASSED tests/test_iyzico_service.py::test_get_payment_history_returns_empty_list_on_no_items
12 passed
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/iyzico_service.py backend/tests/test_iyzico_service.py
git commit -m "feat: add iyzico_service with full SDK wrapper and unit tests"
```

---

## Task 4: Create webhooks/iyzico.py (TDD for _apply_ipn_event)

**Files:**
- Create: `backend/app/api/webhooks/iyzico.py`
- Create: `backend/tests/test_iyzico_webhook.py`

- [ ] **Step 1: Write the failing tests for _apply_ipn_event**

```python
# backend/tests/test_iyzico_webhook.py
"""Tests for iyzico webhook IPN event handling."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db import models

# ── In-memory SQLite DB ───────────────────────────────────────────────────────

TEST_DB_URL = "sqlite:///./test_iyzico_webhook.db"
engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def subscriber_user(db):
    """A SUBSCRIBER user with an active iyzico subscription."""
    user = models.User(
        email="abone@test.com",
        hashed_password="hashed",
        role=models.UserRole.SUBSCRIBER,
        iyzico_subscription_ref="sub-ref-001",
        subscription_status="active",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ── _apply_ipn_event tests ────────────────────────────────────────────────────

def test_ipn_active_updates_status(db, subscriber_user):
    from app.api.webhooks.iyzico import _apply_ipn_event

    payload = {
        "subscriptionReferenceCode": "sub-ref-001",
        "subscriptionStatus": "ACTIVE",
    }
    _apply_ipn_event(payload, db)

    db.refresh(subscriber_user)
    assert subscriber_user.role == models.UserRole.SUBSCRIBER
    assert subscriber_user.subscription_status == "active"


def test_ipn_active_logs_event(db, subscriber_user):
    from app.api.webhooks.iyzico import _apply_ipn_event

    payload = {
        "subscriptionReferenceCode": "sub-ref-001",
        "subscriptionStatus": "ACTIVE",
    }
    _apply_ipn_event(payload, db)

    log = db.query(models.SubscriptionLog).filter_by(
        payment_event_ref="sub-ref-001_ACTIVE"
    ).first()
    assert log is not None
    assert log.event_type == "ACTIVE"


def test_ipn_unpaid_sets_past_due(db, subscriber_user):
    from app.api.webhooks.iyzico import _apply_ipn_event

    payload = {
        "subscriptionReferenceCode": "sub-ref-001",
        "subscriptionStatus": "UNPAID",
    }
    _apply_ipn_event(payload, db)

    db.refresh(subscriber_user)
    assert subscriber_user.subscription_status == "past_due"
    assert subscriber_user.role == models.UserRole.SUBSCRIBER  # role unchanged


def test_ipn_cancelled_revokes_subscriber(db, subscriber_user):
    from app.api.webhooks.iyzico import _apply_ipn_event

    payload = {
        "subscriptionReferenceCode": "sub-ref-001",
        "subscriptionStatus": "CANCELLED",
    }
    _apply_ipn_event(payload, db)

    db.refresh(subscriber_user)
    assert subscriber_user.role == models.UserRole.FREE
    assert subscriber_user.subscription_status == "cancelled"
    assert subscriber_user.iyzico_subscription_ref is None


def test_ipn_expired_revokes_subscriber(db, subscriber_user):
    from app.api.webhooks.iyzico import _apply_ipn_event

    payload = {
        "subscriptionReferenceCode": "sub-ref-001",
        "subscriptionStatus": "EXPIRED",
    }
    _apply_ipn_event(payload, db)

    db.refresh(subscriber_user)
    assert subscriber_user.role == models.UserRole.FREE
    assert subscriber_user.subscription_status == "expired"
    assert subscriber_user.iyzico_subscription_ref is None


def test_ipn_idempotent_skips_duplicate(db, subscriber_user):
    from app.api.webhooks.iyzico import _apply_ipn_event

    payload = {
        "subscriptionReferenceCode": "sub-ref-001",
        "subscriptionStatus": "CANCELLED",
    }
    # First call cancels
    _apply_ipn_event(payload, db)
    # Manually restore role to verify second call is a no-op
    subscriber_user.role = models.UserRole.SUBSCRIBER
    db.commit()

    # Second call should be skipped (idempotency)
    _apply_ipn_event(payload, db)
    db.refresh(subscriber_user)
    assert subscriber_user.role == models.UserRole.SUBSCRIBER  # unchanged by second call


def test_ipn_unknown_sub_ref_logs_without_user(db):
    from app.api.webhooks.iyzico import _apply_ipn_event

    payload = {
        "subscriptionReferenceCode": "unknown-ref",
        "subscriptionStatus": "CANCELLED",
    }
    # Should not raise even when user not found
    _apply_ipn_event(payload, db)

    log = db.query(models.SubscriptionLog).filter_by(
        payment_event_ref="unknown-ref_CANCELLED"
    ).first()
    assert log is not None
    assert log.user_id is None


def test_ipn_missing_fields_is_noop(db):
    from app.api.webhooks.iyzico import _apply_ipn_event

    # No subscriptionReferenceCode — should silently return
    _apply_ipn_event({"someOtherField": "value"}, db)
    assert db.query(models.SubscriptionLog).count() == 0
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend && pytest tests/test_iyzico_webhook.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'app.api.webhooks.iyzico'`

- [ ] **Step 3: Implement webhooks/iyzico.py**

```python
# backend/app/api/webhooks/iyzico.py
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
        except (ValueError, Exception) as exc:
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
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd backend && pytest tests/test_iyzico_webhook.py -v
```

Expected:
```
PASSED tests/test_iyzico_webhook.py::test_ipn_active_updates_status
PASSED tests/test_iyzico_webhook.py::test_ipn_active_logs_event
PASSED tests/test_iyzico_webhook.py::test_ipn_unpaid_sets_past_due
PASSED tests/test_iyzico_webhook.py::test_ipn_cancelled_revokes_subscriber
PASSED tests/test_iyzico_webhook.py::test_ipn_expired_revokes_subscriber
PASSED tests/test_iyzico_webhook.py::test_ipn_idempotent_skips_duplicate
PASSED tests/test_iyzico_webhook.py::test_ipn_unknown_sub_ref_logs_without_user
PASSED tests/test_iyzico_webhook.py::test_ipn_missing_fields_is_noop
8 passed
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/webhooks/iyzico.py backend/tests/test_iyzico_webhook.py
git commit -m "feat: add webhooks/iyzico.py with callback, IPN, checkout-form endpoints + tests"
```

---

## Task 5: Rewrite subscriptions.py

**Files:**
- Modify: `backend/app/api/subscriptions.py`

- [ ] **Step 1: Replace the entire file**

```python
# backend/app/api/subscriptions.py
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
```

- [ ] **Step 2: Run existing test suite to confirm nothing is broken**

```bash
cd backend && pytest tests/ --ignore=tests/test_api_smoke.py -q
```

Expected: all tests pass (iyzico_service + iyzico_webhook tests).

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/subscriptions.py
git commit -m "feat: rewrite subscriptions.py for iyzico — add cancel/pause/resume/history/update-card"
```

---

## Task 6: Update main.py + delete Stripe files

**Files:**
- Modify: `backend/app/main.py`
- Delete: `backend/app/services/stripe_service.py`
- Delete: `backend/app/api/webhooks/stripe.py`

- [ ] **Step 1: Update main.py — swap webhook router**

Replace the Stripe import and registration in `backend/app/main.py`:
```python
from app.api import pools, admin, auth, users, subscriptions
from app.api.webhooks import stripe as stripe_webhook
```
With:
```python
from app.api import pools, admin, auth, users, subscriptions
from app.api.webhooks import iyzico as iyzico_webhook
```

And replace:
```python
app.include_router(stripe_webhook.router, prefix="/webhooks", tags=["webhooks"])
```
With:
```python
app.include_router(iyzico_webhook.router, prefix="/webhooks/iyzico", tags=["webhooks"])
```

- [ ] **Step 2: Delete Stripe files**

```bash
rm backend/app/services/stripe_service.py
rm backend/app/api/webhooks/stripe.py
```

- [ ] **Step 3: Run full test suite**

```bash
cd backend && pytest tests/ --ignore=tests/test_api_smoke.py -q
```

Expected: all tests still pass. No import errors.

- [ ] **Step 4: Verify routes are registered correctly**

```bash
cd backend && python -c "
from app.main import app
routes = [r.path for r in app.routes]
assert any('/webhooks/iyzico/ipn' in r for r in routes), 'IPN route missing'
assert any('/webhooks/iyzico/callback' in r for r in routes), 'callback route missing'
assert any('/webhooks/iyzico/checkout-form' in r for r in routes), 'checkout-form route missing'
assert not any('/webhooks/stripe' in r for r in routes), 'stripe route still registered'
print('Routes verified OK')
"
```

Expected: `Routes verified OK`

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py
git rm backend/app/services/stripe_service.py backend/app/api/webhooks/stripe.py
git commit -m "feat: register iyzico webhook router; remove stripe_service and stripe webhook"
```

---

## Task 7: Update hesap/page.tsx — Inline subscription management section

**Files:**
- Modify: `frontend/src/app/hesap/page.tsx`

- [ ] **Step 1: Replace the entire file**

```tsx
// frontend/src/app/hesap/page.tsx
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { authedGet, authedPost } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

interface SavedCoupon {
  week_code: string;
  scenario_type: string;
  total_columns: number;
  correct_count: number | null;
  brier_score: number | null;
}

interface UserStats {
  total_coupons: number;
  avg_correct: number | null;
}

interface PaymentHistoryItem {
  startDate?: string;
  endDate?: string;
  price?: number;
  currencyCode?: string;
  paymentStatus?: string;
  [key: string]: unknown;
}

const ROLE_LABELS: Record<string, string> = {
  FREE: "ÜCRETSİZ",
  SUBSCRIBER: "ABONE",
  ADMIN: "ADMİN",
};

const ROLE_COLORS: Record<string, string> = {
  FREE: "bg-gray-100 text-gray-600",
  SUBSCRIBER: "bg-green-100 text-green-700",
  ADMIN: "bg-brand-100 text-brand-700",
};

const SUB_STATUS_LABELS: Record<string, string> = {
  active: "AKTİF",
  paused: "DURAKLATILDI",
  past_due: "ÖDEME GECİKMİŞ",
  cancelled: "İPTAL EDİLDİ",
  expired: "SÜRESİ DOLDU",
  inactive: "AKTİF DEĞİL",
};

const SUB_STATUS_COLORS: Record<string, string> = {
  active: "bg-green-100 text-green-700",
  paused: "bg-yellow-100 text-yellow-700",
  past_due: "bg-red-100 text-red-600",
  cancelled: "bg-gray-100 text-gray-500",
  expired: "bg-gray-100 text-gray-500",
  inactive: "bg-gray-100 text-gray-500",
};

function formatTurkishDate(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleDateString("tr-TR", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

export default function HesapPage() {
  const { user, token, logout, loading: authLoading } = useAuth();
  const router = useRouter();

  const [coupons, setCoupons] = useState<SavedCoupon[]>([]);
  const [stats, setStats] = useState<UserStats | null>(null);
  const [dataLoading, setDataLoading] = useState(true);

  // Subscription section state
  const [subStatus, setSubStatus] = useState<string | null>(null);
  const [paymentHistory, setPaymentHistory] = useState<PaymentHistoryItem[]>([]);
  const [subActionLoading, setSubActionLoading] = useState(false);
  const [cancelConfirm, setCancelConfirm] = useState(false);
  const [subError, setSubError] = useState<string | null>(null);

  const isSubscriber = user?.role === "SUBSCRIBER" || user?.role === "ADMIN";

  useEffect(() => {
    if (!authLoading && !token) {
      router.push("/auth/giris");
    }
  }, [authLoading, token, router]);

  // Sync local subStatus with user profile
  useEffect(() => {
    if (user?.subscription_status) {
      setSubStatus(user.subscription_status);
    }
  }, [user?.subscription_status]);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    async function fetchData() {
      setDataLoading(true);
      try {
        const requests: Promise<unknown>[] = [
          authedGet<SavedCoupon[]>("/users/me/coupons", token!),
          authedGet<UserStats>("/users/me/stats", token!),
        ];
        if (isSubscriber) {
          requests.push(
            authedGet<{ items: PaymentHistoryItem[] }>("/subscriptions/history", token!)
          );
        }
        const results = await Promise.allSettled(requests);
        if (cancelled) return;
        if (results[0].status === "fulfilled")
          setCoupons(results[0].value as SavedCoupon[]);
        if (results[1].status === "fulfilled")
          setStats(results[1].value as UserStats);
        if (results[2]?.status === "fulfilled") {
          const histRes = results[2].value as { items: PaymentHistoryItem[] };
          setPaymentHistory(histRes.items ?? []);
        }
      } finally {
        if (!cancelled) setDataLoading(false);
      }
    }
    fetchData();
    return () => {
      cancelled = true;
    };
  }, [token, isSubscriber]);

  async function handleLogout() {
    logout();
    router.push("/");
  }

  async function handlePauseResume() {
    if (!token) return;
    setSubError(null);
    setSubActionLoading(true);
    try {
      const isPaused = subStatus === "paused";
      const endpoint = isPaused ? "/subscriptions/resume" : "/subscriptions/pause";
      const res = await authedPost<{ subscription_status: string }>(endpoint, {}, token);
      setSubStatus(res.subscription_status);
    } catch {
      setSubError("İşlem gerçekleştirilemedi. Lütfen tekrar deneyin.");
    } finally {
      setSubActionLoading(false);
    }
  }

  async function handleCancel() {
    if (!token) return;
    setSubError(null);
    setSubActionLoading(true);
    try {
      await authedPost("/subscriptions/cancel", {}, token);
      logout();
      router.push("/?cancelled=1");
    } catch {
      setSubActionLoading(false);
      setSubError("Abonelik iptal edilemedi. Lütfen tekrar deneyin.");
    }
  }

  async function handleCardUpdate() {
    if (!token) return;
    setSubError(null);
    setSubActionLoading(true);
    try {
      const res = await authedPost<{ url: string }>("/subscriptions/update-card", {}, token);
      window.location.href = res.url;
    } catch {
      setSubActionLoading(false);
      setSubError("Kart güncelleme sayfasına yönlendirilemedi.");
    }
  }

  if (authLoading) {
    return (
      <div className="max-w-2xl mx-auto mt-10 space-y-4 animate-pulse">
        <div className="h-32 bg-gray-200 rounded-xl" />
        <div className="h-48 bg-gray-200 rounded-xl" />
      </div>
    );
  }

  if (!user) return null;

  const roleLabel = ROLE_LABELS[user.role] ?? user.role;
  const roleColor = ROLE_COLORS[user.role] ?? "bg-gray-100 text-gray-600";
  const subStatusLabel = SUB_STATUS_LABELS[subStatus ?? ""] ?? subStatus ?? "";
  const subStatusColor =
    SUB_STATUS_COLORS[subStatus ?? ""] ?? "bg-gray-100 text-gray-500";
  const isPaused = subStatus === "paused";

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* ── Profile card ─────────────────────────────────────────── */}
      <div className="bg-white rounded-xl shadow-md p-6">
        <div className="flex items-start justify-between mb-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-800">
              {user.display_name ?? user.email}
            </h1>
            {user.display_name && (
              <p className="text-sm text-gray-500 mt-0.5">{user.email}</p>
            )}
          </div>
          <span
            className={`text-xs font-semibold px-2.5 py-1 rounded-full ${roleColor}`}
          >
            {roleLabel}
          </span>
        </div>
        <div className="flex flex-wrap gap-3 mt-4">
          <button
            onClick={handleLogout}
            className="text-sm px-4 py-2 rounded-lg border border-gray-200 text-gray-600 hover:text-red-600 hover:border-red-300 transition-colors"
          >
            Çıkış Yap
          </button>
        </div>
      </div>

      {/* ── Abonelik section (subscribers only) ──────────────────── */}
      {isSubscriber ? (
        <div id="abonelik" className="bg-white rounded-xl shadow-md p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-700">Abonelik</h2>
            {subStatus && (
              <span
                className={`text-xs font-semibold px-2.5 py-1 rounded-full ${subStatusColor}`}
              >
                {subStatusLabel}
              </span>
            )}
          </div>

          {user.subscription_expires_at && (
            <p className="text-sm text-gray-600 mb-4">
              Yenileme:{" "}
              <span className="font-medium">
                {formatTurkishDate(user.subscription_expires_at)}
              </span>
            </p>
          )}

          {subError && (
            <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2 mb-3">
              {subError}
            </p>
          )}

          {/* Action buttons */}
          {!cancelConfirm ? (
            <div className="flex flex-wrap gap-3 mb-6">
              <button
                onClick={handleCardUpdate}
                disabled={subActionLoading}
                className="text-sm px-4 py-2 rounded-lg border border-gray-200 text-gray-700 hover:border-brand-400 hover:text-brand-700 disabled:opacity-50 transition-colors"
              >
                Kartı Güncelle
              </button>
              <button
                onClick={handlePauseResume}
                disabled={subActionLoading}
                className="text-sm px-4 py-2 rounded-lg border border-gray-200 text-gray-700 hover:border-yellow-400 hover:text-yellow-700 disabled:opacity-50 transition-colors"
              >
                {subActionLoading
                  ? "İşleniyor…"
                  : isPaused
                  ? "Devam Et"
                  : "Duraklat"}
              </button>
              <button
                onClick={() => setCancelConfirm(true)}
                disabled={subActionLoading}
                className="text-sm px-4 py-2 rounded-lg border border-gray-200 text-red-500 hover:border-red-300 hover:text-red-700 disabled:opacity-50 transition-colors"
              >
                İptal Et
              </button>
            </div>
          ) : (
            /* Cancel confirmation */
            <div className="flex flex-wrap items-center gap-3 mb-6 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
              <p className="text-sm text-red-700 font-medium">
                Aboneliğinizi iptal etmek istediğinizden emin misiniz?
              </p>
              <div className="flex gap-2">
                <button
                  onClick={handleCancel}
                  disabled={subActionLoading}
                  className="text-sm px-3 py-1.5 rounded-lg bg-red-600 text-white hover:bg-red-700 disabled:opacity-50 transition-colors"
                >
                  {subActionLoading ? "İşleniyor…" : "Evet, İptal Et"}
                </button>
                <button
                  onClick={() => setCancelConfirm(false)}
                  disabled={subActionLoading}
                  className="text-sm px-3 py-1.5 rounded-lg border border-gray-200 text-gray-600 hover:border-gray-400 transition-colors"
                >
                  Vazgeç
                </button>
              </div>
            </div>
          )}

          {/* Payment history */}
          <div>
            <h3 className="text-sm font-semibold text-gray-600 mb-3">
              Ödeme Geçmişi
            </h3>
            {paymentHistory.length === 0 ? (
              <p className="text-sm text-gray-400">Henüz ödeme geçmişi yok.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-100 text-left text-xs text-gray-500 uppercase tracking-wide">
                      <th className="pb-2 pr-4">Tarih</th>
                      <th className="pb-2 pr-4 text-right">Tutar</th>
                      <th className="pb-2 text-right">Durum</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {paymentHistory.map((item, idx) => (
                      <tr key={idx} className="hover:bg-gray-50">
                        <td className="py-2 pr-4 text-gray-700">
                          {item.startDate
                            ? formatTurkishDate(item.startDate)
                            : "—"}
                        </td>
                        <td className="py-2 pr-4 text-right text-gray-700">
                          {item.price != null
                            ? `${item.price} ${item.currencyCode ?? "TRY"}`
                            : "—"}
                        </td>
                        <td className="py-2 text-right text-gray-700">
                          {(item.paymentStatus as string) ?? "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      ) : (
        /* FREE user — upgrade prompt */
        <div className="bg-white rounded-xl shadow-md p-6 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-700 mb-1">Abonelik</h2>
            <p className="text-sm text-gray-500">
              Gelişmiş analizlere erişmek için abone olun.
            </p>
          </div>
          <Link
            href="/uye-ol"
            className="bg-brand-600 text-white text-sm px-4 py-2 rounded-lg hover:bg-brand-700 transition-colors whitespace-nowrap"
          >
            Abone Ol →
          </Link>
        </div>
      )}

      {/* ── Stats ────────────────────────────────────────────────── */}
      {stats && (
        <div className="bg-white rounded-xl shadow-md p-6">
          <h2 className="text-lg font-semibold text-gray-700 mb-3">
            İstatistikler
          </h2>
          <div className="flex gap-6">
            <div>
              <p className="text-2xl font-bold text-gray-800">
                {stats.total_coupons}
              </p>
              <p className="text-xs text-gray-500 mt-0.5">Toplam Kupon</p>
            </div>
            {stats.avg_correct != null && (
              <div>
                <p className="text-2xl font-bold text-gray-800">
                  {stats.avg_correct.toFixed(1)}
                </p>
                <p className="text-xs text-gray-500 mt-0.5">Ort. Doğru</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Saved coupons ─────────────────────────────────────────── */}
      <div className="bg-white rounded-xl shadow-md p-6">
        <h2 className="text-lg font-semibold text-gray-700 mb-4">
          Kayıtlı Kuponlar
        </h2>
        {dataLoading ? (
          <div className="animate-pulse space-y-2">
            <div className="h-8 bg-gray-100 rounded" />
            <div className="h-8 bg-gray-100 rounded" />
          </div>
        ) : coupons.length === 0 ? (
          <p className="text-sm text-gray-400">Henüz kaydedilmiş kupon yok.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 text-left text-xs text-gray-500 uppercase tracking-wide">
                  <th className="pb-2 pr-4">Hafta</th>
                  <th className="pb-2 pr-4">Senaryo</th>
                  <th className="pb-2 pr-4 text-right">Kolon</th>
                  <th className="pb-2 pr-4 text-right">Doğru</th>
                  <th className="pb-2 text-right">Brier</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {coupons.map((c) => (
                  <tr
                    key={`${c.week_code}-${c.scenario_type}`}
                    className="hover:bg-gray-50"
                  >
                    <td className="py-2 pr-4 text-gray-700">{c.week_code}</td>
                    <td className="py-2 pr-4 text-gray-700 capitalize">
                      {c.scenario_type}
                    </td>
                    <td className="py-2 pr-4 text-right text-gray-700">
                      {c.total_columns}
                    </td>
                    <td className="py-2 pr-4 text-right text-gray-700">
                      {c.correct_count ?? "—"}
                    </td>
                    <td className="py-2 text-right text-gray-700">
                      {c.brier_score != null
                        ? c.brier_score.toFixed(3)
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -E "hesap|error" | head -20
```

Expected: no output (no errors in hesap/page.tsx).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/hesap/page.tsx
git commit -m "feat: add inline subscription management section to hesap page"
```

---

## Task 8: Update uye-ol/page.tsx — iyzico checkout navigation

**Files:**
- Modify: `frontend/src/app/uye-ol/page.tsx`

- [ ] **Step 1: Replace the entire file**

```tsx
// frontend/src/app/uye-ol/page.tsx
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { authedPost } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

const FREE_FEATURES = [
  { label: "Haftalık maç listesi", available: true },
  { label: "Temel tahminler (1/X/2)", available: true },
  { label: "Birincil öneri", available: true },
  { label: "Radar grafik & takım analizleri", available: false },
  { label: "Bahis oranları hareketleri", available: false },
  { label: "Kupon senaryoları (güvenli/dengeli/agresif)", available: false },
  { label: "Kupon optimizasyonu", available: false },
  { label: "Kupon performans takibi", available: false },
];

const ABONE_FEATURES = FREE_FEATURES.map((f) => ({ ...f, available: true }));

function FeatureRow({ label, available }: { label: string; available: boolean }) {
  return (
    <li className="flex items-center gap-2 text-sm">
      {available ? (
        <span className="text-green-500 font-bold">✓</span>
      ) : (
        <span className="text-gray-300 font-bold">✗</span>
      )}
      <span className={available ? "text-gray-700" : "text-gray-400"}>
        {label}
      </span>
    </li>
  );
}

export default function UyeOlPage() {
  const { user, token, isSubscriber, loading: authLoading } = useAuth();
  const router = useRouter();
  const [checkoutLoading, setCheckoutLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    if (!authLoading && !token) {
      router.push("/auth/giris?next=/uye-ol");
    }
  }, [authLoading, token, router]);

  async function handleCheckout() {
    if (!token) {
      router.push("/auth/giris?next=/uye-ol");
      return;
    }
    setActionError(null);
    setCheckoutLoading(true);
    try {
      // Backend returns a URL pointing to the iyzico checkout-form endpoint.
      // We navigate the browser there (full-page navigation, not a fetch).
      const res = await authedPost<{ url: string }>("/subscriptions/checkout", {}, token);
      window.location.href = res.url;
    } catch {
      setCheckoutLoading(false);
      setActionError("Ödeme sayfasına yönlendirilemedi. Lütfen tekrar deneyin.");
    }
  }

  if (authLoading) {
    return (
      <div className="max-w-3xl mx-auto mt-10 space-y-4 animate-pulse">
        <div className="h-12 bg-gray-200 rounded-xl" />
        <div className="h-64 bg-gray-200 rounded-xl" />
      </div>
    );
  }

  if (!token) return null;

  return (
    <div className="max-w-3xl mx-auto">
      <div className="text-center mb-8">
        <h1 className="text-3xl font-bold text-gray-800">Üye Ol</h1>
        <p className="mt-2 text-gray-500">
          Gelişmiş analizlere ve kupon optimizasyonuna erişin.
        </p>
      </div>

      {/* Plan comparison */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
        {/* FREE */}
        <div className="bg-white rounded-xl shadow-md p-6 border border-gray-100">
          <div className="mb-4">
            <span className="inline-block text-xs font-semibold bg-gray-100 text-gray-500 px-2.5 py-1 rounded-full uppercase tracking-wide">
              Ücretsiz
            </span>
            <p className="mt-2 text-2xl font-bold text-gray-800">₺0</p>
            <p className="text-xs text-gray-400">sonsuza dek ücretsiz</p>
          </div>
          <ul className="space-y-2">
            {FREE_FEATURES.map((f) => (
              <FeatureRow key={f.label} {...f} />
            ))}
          </ul>
        </div>

        {/* ABONE */}
        <div className="bg-brand-900 rounded-xl shadow-md p-6 border border-brand-700 relative overflow-hidden">
          <div className="absolute top-3 right-3 bg-amber-400 text-amber-900 text-xs font-bold px-2 py-0.5 rounded-full">
            Önerilen
          </div>
          <div className="mb-4">
            <span className="inline-block text-xs font-semibold bg-brand-700 text-white px-2.5 py-1 rounded-full uppercase tracking-wide">
              Abone
            </span>
            <p className="mt-2 text-2xl font-bold text-white">Aylık Plan</p>
            <p className="text-xs text-brand-300">tüm özellikler dahil</p>
          </div>
          <ul className="space-y-2">
            {ABONE_FEATURES.map((f) => (
              <li key={f.label} className="flex items-center gap-2 text-sm">
                <span className="text-green-400 font-bold">✓</span>
                <span className="text-white">{f.label}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* CTA */}
      <div className="text-center">
        {actionError && (
          <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2 mb-4 inline-block">
            {actionError}
          </p>
        )}
        {isSubscriber ? (
          <div className="bg-green-50 border border-green-200 rounded-xl p-6">
            <p className="text-green-700 font-medium mb-3">
              Zaten aboneniz! Aboneliğinizi yönetmek için:
            </p>
            <Link
              href="/hesap#abonelik"
              className="bg-brand-600 text-white px-6 py-2.5 rounded-lg text-sm font-medium hover:bg-brand-700 transition-colors inline-block"
            >
              Hesabıma Git
            </Link>
          </div>
        ) : (
          <div>
            <button
              onClick={handleCheckout}
              disabled={checkoutLoading}
              className="bg-brand-600 text-white px-8 py-3 rounded-xl text-base font-semibold hover:bg-brand-700 disabled:opacity-50 transition-colors shadow-lg"
            >
              {checkoutLoading ? "Yönlendiriliyor…" : "Abone Ol"}
            </button>
            {!user && (
              <p className="mt-3 text-sm text-gray-400">
                Devam etmek için{" "}
                <Link
                  href="/auth/giris?next=/uye-ol"
                  className="text-brand-600 hover:underline"
                >
                  giriş yapmanız
                </Link>{" "}
                gerekiyor.
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -E "uye-ol|error" | head -20
```

Expected: no output (no errors).

- [ ] **Step 3: Run full backend test suite one final time**

```bash
cd backend && pytest tests/ --ignore=tests/test_api_smoke.py -q
```

Expected: all tests pass, including the 12 iyzico_service tests and 8 iyzico_webhook tests.

- [ ] **Step 4: Final commit**

```bash
git add frontend/src/app/uye-ol/page.tsx
git commit -m "feat: update uye-ol page for iyzico — replace portal button with hesap link"
```

---

## Verification Checklist

After all 8 tasks are complete, verify the spec requirements:

1. `alembic upgrade head` — migration 003 applied cleanly ✓ (Task 1)
2. `pytest backend/tests/ --ignore=tests/test_api_smoke.py` — all tests pass ✓ (Tasks 3, 4)
3. `stripe_service.py` and `webhooks/stripe.py` deleted ✓ (Task 6)
4. `POST /subscriptions/checkout` returns URL pointing to `/webhooks/iyzico/checkout-form?jwt_token=…` ✓ (Task 5)
5. `GET /webhooks/iyzico/checkout-form?jwt_token=<valid>` → 200 with iyzico HTML (sandbox) ✓ (Task 4)
6. `GET /webhooks/iyzico/callback?token=<sandbox-token>` → role=SUBSCRIBER in DB, redirect to success URL ✓ (Task 4)
7. IPN POST with `CANCELLED` status → role=FREE in DB ✓ (Task 4)
8. `POST /subscriptions/pause` → subscription_status=paused ✓ (Task 5)
9. `POST /subscriptions/resume` → subscription_status=active ✓ (Task 5)
10. `POST /subscriptions/cancel` → role=FREE ✓ (Task 5)
11. `GET /subscriptions/history` → items list ✓ (Task 5)
12. `/hesap` subscription section renders for SUBSCRIBER with action buttons ✓ (Task 7)
13. Cancel confirmation modal works (Vazgeç dismisses, Evet İptal Et calls API) ✓ (Task 7)
14. `/uye-ol` subscriber CTA shows "Hesabıma Git" link to `/hesap#abonelik` ✓ (Task 8)
