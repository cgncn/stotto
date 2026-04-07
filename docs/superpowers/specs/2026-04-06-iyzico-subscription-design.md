# iyzico Subscription System — Design Spec

**Date:** 2026-04-06
**Status:** Approved for implementation
**Replaces:** `docs/superpowers/specs/2026-04-06-stotto-auth-subscription-design.md` (Stripe sections only)

---

## Problem / Motivation

Stripe does not operate in Turkey. The existing Stripe-based subscription system must be replaced end-to-end with iyzico, a Turkish payment processor. The replacement must preserve all existing role/gating/coupon logic — only the payment provider layer changes.

Additionally, iyzico has no hosted billing portal, so a self-built subscription management section is added directly inside the existing `/hesap` account page.

---

## Scope

**Replaced entirely:**
- `backend/app/services/stripe_service.py` → `iyzico_service.py`
- `backend/app/api/webhooks/stripe.py` → `webhooks/iyzico.py`
- Stripe-specific config keys
- `stripe` pip package → `iyzipay`
- Frontend portal redirect button → inline subscription management section on `/hesap`

**DB rename (migration 003_):**
- `users.stripe_customer_id` → `users.iyzico_customer_ref`
- `users.stripe_subscription_id` → `users.iyzico_subscription_ref`
- `subscription_log.stripe_event_id` → `subscription_log.payment_event_ref`

**Preserved unchanged:**
- `UserRole` enum (FREE / SUBSCRIBER / ADMIN)
- `subscription_status`, `subscription_expires_at` columns
- `require_subscriber` / `get_optional_user` deps
- All feature gating (`scrub_for_free_tier`, `SubscriberGate`)
- `AuthContext`, all other frontend components and pages
- All coupon/settlement logic

---

## iyzico Checkout Flow

iyzico's redirect-based subscription checkout has three stages:

```
1. POST /subscriptions/checkout
   → iyzico_service.initialize_checkout(user)
   → SubscriptionCheckoutFormInitialize API call
   → return {"url": iyzico_hosted_page_url}

2. User completes payment on iyzico's hosted page

3. GET /webhooks/iyzico/callback?token=xxx
   ← iyzico redirects here after checkout or card update
   → retrieve_checkout_result(token) → SubscriptionCheckoutFormResult
   → if status == ACTIVE:
       user.iyzico_customer_ref = customerReferenceCode
       user.iyzico_subscription_ref = subscriptionReferenceCode
       user.role = SUBSCRIBER
       user.subscription_status = "active"
   → redirect to IYZICO_SUCCESS_URL or IYZICO_CANCEL_URL
```

**Subscriber object note:** `SubscriptionCheckoutFormInitialize` requires a `subscriber` dict with `identityNumber` (Turkish TCKN). Sandbox uses placeholder `"11111111111"` and a dummy address. Production requires collecting TCKN from the user — this is a follow-up task outside this spec's scope.

---

## IPN (Instant Payment Notification)

iyzico POSTs lifecycle events to `POST /webhooks/iyzico/ipn`:

| iyzico status | Action |
|---------------|--------|
| `ACTIVE` | `role=SUBSCRIBER`, `subscription_status="active"`, update `subscription_expires_at` |
| `UNPAID` | `subscription_status="past_due"` |
| `CANCELLED` | `role=FREE`, `subscription_status="cancelled"`, clear `iyzico_subscription_ref` |
| `EXPIRED` | `role=FREE`, `subscription_status="expired"`, clear `iyzico_subscription_ref` |

Idempotency: check `subscription_log.payment_event_ref` before processing. All events logged to `subscription_log`.

---

## Backend Components

### New file: `backend/app/services/iyzico_service.py`

| Function | iyzico API | Purpose |
|----------|-----------|---------|
| `initialize_checkout(user)` | `SubscriptionCheckoutFormInitialize` | Returns hosted checkout URL |
| `retrieve_checkout_result(token)` | `SubscriptionCheckoutFormResult` | Verifies payment after redirect |
| `cancel_subscription(ref)` | `SubscriptionCancel` | Cancels active subscription |
| `pause_subscription(ref)` | `SubscriptionDeActivate` | Pauses billing |
| `resume_subscription(ref)` | `SubscriptionActivate` | Resumes paused subscription |
| `initialize_card_update(user)` | `SubscriptionCardUpdate` form | Returns card-update URL |
| `get_payment_history(ref)` | `SubscriptionOrders` | List of past charges |

### Modified file: `backend/app/api/subscriptions.py`

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| POST | `/subscriptions/checkout` | get_current_user | Returns `{"url": ...}` |
| GET | `/subscriptions/status` | get_current_user | Unchanged |
| POST | `/subscriptions/cancel` | require_subscriber | Cancels + role→FREE |
| POST | `/subscriptions/pause` | require_subscriber | Pauses billing |
| POST | `/subscriptions/resume` | require_subscriber | Resumes billing |
| POST | `/subscriptions/update-card` | require_subscriber | Returns card-update URL |
| GET | `/subscriptions/history` | require_subscriber | Returns payment list |

**Removed:** `POST /subscriptions/portal`

### New file: `backend/app/api/webhooks/iyzico.py`

- `GET /webhooks/iyzico/callback` — redirect handler (query param: `token`)
- `POST /webhooks/iyzico/ipn` — IPN event handler

### Modified file: `backend/app/config.py`

Remove all `stripe_*` fields. Add:
```python
iyzico_api_key: str = ""
iyzico_secret_key: str = ""
iyzico_base_url: str = "https://sandbox-api.iyzipay.com"
iyzico_subscription_plan_ref_code: str = ""   # pre-created plan in iyzico dashboard
iyzico_callback_url: str = "http://localhost:8000/webhooks/iyzico/callback"
iyzico_success_url: str = "http://localhost:3000/hesap?success=1"
iyzico_cancel_url: str = "http://localhost:3000/uye-ol?cancelled=1"
```

### Modified file: `backend/requirements.txt`

Remove `stripe>=7.0.0`. Add `iyzipay>=2.0.0`.

### Modified file: `backend/app/main.py`

Update webhook router registration from `stripe_webhook` to `iyzico_webhook`.

---

## Database Migration 003_

```sql
-- users table
ALTER TABLE users RENAME COLUMN stripe_customer_id TO iyzico_customer_ref;
ALTER TABLE users RENAME COLUMN stripe_subscription_id TO iyzico_subscription_ref;

-- subscription_log table
ALTER TABLE subscription_log RENAME COLUMN stripe_event_id TO payment_event_ref;
```

Rename unique constraint names accordingly.

---

## Frontend Changes

### Modified: `frontend/src/app/hesap/page.tsx`

Replace the existing "Aboneliği Yönet" portal button with a full **Abonelik** section rendered inline when the user is a subscriber. Layout:

```
┌────────────────────────────────────────────┐
│  Profil                                    │
│  Ad · E-posta · [Çıkış Yap]               │
├────────────────────────────────────────────┤
│  Abonelik                      AKTİF       │
│  Yenileme: 15 Mayıs 2026                   │
│  [Kartı Güncelle] [Duraklat] [İptal Et]    │
│                                            │
│  Ödeme Geçmişi                             │
│  Tarih · Tutar · Durum                     │
├────────────────────────────────────────────┤
│  Kuponlarım                                │
│  ...                                       │
└────────────────────────────────────────────┘
```

Behaviour:
- Subscription section only visible when `user.role === "SUBSCRIBER" || "ADMIN"`
- FREE users see "Abone Ol →" link to `/uye-ol` instead
- Pause button label toggles: "Duraklat" when active, "Devam Et" when paused
- Cancel shows an inline confirmation ("Emin misiniz? [Evet, İptal Et] [Vazgeç]") before calling API
- Card update calls `POST /subscriptions/update-card` → redirects to iyzico URL
- Payment history table: columns Tarih / Tutar / Durum (fetched from `GET /subscriptions/history`)

### Modified: `frontend/src/app/uye-ol/page.tsx`

Replace the "Aboneliği Yönet" portal redirect button with a direct link to `/hesap#abonelik`.

### No new pages required.

---

## `.env` additions

```
IYZICO_API_KEY=sandbox-...
IYZICO_SECRET_KEY=sandbox-...
IYZICO_BASE_URL=https://sandbox-api.iyzipay.com
IYZICO_SUBSCRIPTION_PLAN_REF_CODE=<from iyzico dashboard>
IYZICO_CALLBACK_URL=http://localhost:8000/webhooks/iyzico/callback
IYZICO_SUCCESS_URL=http://localhost:3000/hesap?success=1
IYZICO_CANCEL_URL=http://localhost:3000/uye-ol?cancelled=1
```

---

## Files Deleted

- `backend/app/services/stripe_service.py`
- `backend/app/api/webhooks/stripe.py`

---

## Verification Checklist

1. `pytest backend/tests/ --ignore=backend/tests/test_api_smoke.py` — all 43 tests pass
2. `alembic upgrade head` — migration 003_ applies cleanly
3. `POST /subscriptions/checkout` → iyzico sandbox checkout URL returned
4. Complete checkout with iyzico test card → callback fires → `role=SUBSCRIBER` in DB
5. `GET /subscriptions/history` → payment rows returned
6. `POST /subscriptions/pause` → `subscription_status="paused"` in DB
7. `POST /subscriptions/resume` → `subscription_status="active"` in DB
8. `POST /subscriptions/cancel` → `role=FREE` in DB
9. IPN event with `CANCELLED` → `role=FREE` in DB
10. `/hesap` subscription section renders for SUBSCRIBER, hides for FREE
11. Cancel confirmation modal works correctly
