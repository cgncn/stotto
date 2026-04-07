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
