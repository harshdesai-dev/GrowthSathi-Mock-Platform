# Phase 3 payments and access operations

Sandbox only. Do not accept real payments. No Phase 4 exam interface exists.
See [ADR 0008](adr/0008-offers-payments-and-access.md) for transaction and state rules.

## Configure the sandbox

1. Install backend dependencies and run `python manage.py migrate`.
2. In the owner's Razorpay account select **Test Mode**, obtain its test key ID and
   secret, and configure automatic capture. Never supply live keys.
3. Set backend process variables `RAZORPAY_KEY_ID=rzp_test_...`,
   `RAZORPAY_KEY_SECRET` and a separately chosen `RAZORPAY_WEBHOOK_SECRET`.
   `.env.example` is a template; Django reads process environment, not `.env` itself.
4. Register an HTTPS webhook for `/api/v1/payments/webhook/` subscribing only to
   `payment.captured` and `payment.failed`. Set the same webhook secret there.
   Localhost is not publicly reachable: use a secured test deployment or an
   explicitly approved HTTPS tunnel. Do not expose owner Admin unnecessarily.
5. Frontend receives the public key from the backend checkout response. No
   `VITE_RAZORPAY_KEY_ID` is needed and **no secret belongs in any VITE variable**.
   The script loads only from `https://checkout.razorpay.com/v1/checkout.js` on demand.
6. Follow [exam administration](EXAM_ADMINISTRATION.md) to author and validate real
   papers, recheck latest official exam rules for each mock, and publish registration.
   The existing seed schemes are baselines, not a current official-rule attestation.
7. In owner Admin create inactive offers and their explicit mock items. Leave price
   blank for 2900 paise JEE/CET or 5000 combo; otherwise enter future integer prices.
   Set sales window, save items, then select **Activate validated offers**. Deactivate
   before edits. There is no automatic creation of fake sellable mocks or offers.

## API contract

All paths below are under `/api/v1/`. Responses use the existing error envelope.
Public serializers never return questions, options, answers, explanations, internal
review notes or secrets. UUID details return 404 for absent/private records.

| Method/path | Authentication | Purpose |
| --- | --- | --- |
| GET `mocks/`, `mocks/{id}/` | Public | Published mock metadata, no DRAFT papers |
| GET `offers/`, `offers/{id}/` | Public | Active visible offers, explicit contents, price and current availability |
| POST `orders/` | Student JWT + completed profile | Body exactly `{"offer_id":"UUID"}`; create/reuse order |
| GET `orders/{id}/` | Purchasing student's JWT | Snapshots, status and nullable checkout-safe fields |
| POST `payments/verify/` | Purchasing student's JWT | Local `order_id`, `razorpay_order_id`, `razorpay_payment_id`, `razorpay_signature` |
| POST `payments/webhook/` | Raw-body Razorpay HMAC | `X-Razorpay-Signature` and `X-Razorpay-Event-Id` |
| GET `access/` | Student JWT | Own historical/current grants and effective `has_access` |
| GET `mocks/{id}/access/` | Student JWT | Own effective access for one published mock |

Creation/reuse responds 200. CREATED with `checkout: null` means remote creation is
in flight/uncertain; refresh status, then ask the owner to reconcile. Remote failures
respond 503 without exposing provider error details. Failed signature/mismatch is 400.
The creation payload rejects extra amount, price or independently selected mock IDs.
PAID orders have no checkout data. Pending old-price/changed/closed offers also have
no checkout data. A gateway checkout already opened cannot be recalled locally;
captures are still recorded against the immutable original order.

## Student experience

`/mocks`, `/mocks/:mockId`, `/checkout/:offerId` and `/dashboard` provide the minimal
catalogue, details, purchase and access views. Checkout requires completed onboarding.
The checkout URL retains the local order UUID for reload/status refresh. Browser
success means **verify**, not **unlock**. Verification/network uncertainty stays
pending with a warning not to pay twice. Failure and modal cancellation are distinct
messages. Refresh reads backend state, allowing webhook reconciliation to recover
the screen. No actual attempt or start button exists.

## Owner inspection and recovery

Admin offers editing/activation plus read-only Orders, OrderItems, Payments,
PaymentWebhookEvents, MockOfferItems and MockAccessGrants. Only the active owner
superuser/staff can inspect them. Payment signatures are not displayed. Look for
`review_required`, CREATED receipts and old PENDING orders regularly; no worker or
alerting scheduler is installed in Phase 3.

For a lost create response, locate the Razorpay order whose receipt equals the
local UUID with hyphens removed, verify its amount and currency, then:

```bash
python manage.py commerce_operation link-order LOCAL_ORDER_UUID --owner OWNER_EMAIL --reference order_PROVIDER_ID
```

This command fetches and validates the gateway order; it does not create one or move
money. Replay the webhook after linking, or retry authenticated browser verification.
Do not delete uncertain receipts or casually edit gateway IDs. If the provider confirms
there is no matching order, arrange exactly one through its supported owner workflow
with the original receipt/amount before linking; this is deliberately not an automatic retry.

For a full-order refund, first confirm one of these eligible reasons:

- `MOCK_CANCELLED`: GrowthSathi cancelled the mock.
- `DUPLICATE_VERIFIED_PAYMENT`: a duplicate payment was verified.
- `PLATFORM_FAILURE`: confirmed GrowthSathi failure prevented access.

No refund for no-show, late arrival, or student-side device/internet issues after exam
start. Investigate and perform the refund manually in Razorpay. Verify completed
refunds for **all captured money on that local order** and retain evidence. Only then:

```bash
python manage.py commerce_operation record-refund ORDER_UUID --owner OWNER_EMAIL --reason PLATFORM_FAILURE --reference VERIFIED_REFUND_OR_CASE_REFERENCE
python manage.py commerce_operation revoke-access GRANT_UUID --owner OWNER_EMAIL --reason "Verified incident reference and reason"
```

The first records the completed full-order refund, actor and timestamp. It does not
call Razorpay. Do not use it for an individual extra-payment refund or partial refund:
retain provider/accounting evidence and keep the covered order paid; granular refund
records/automation are deferred. Revocation records the owner and explanation.
Callback/webhook replay will not restore revoked/refunded grants. Partial-overlap
combos cost the full advertised amount; no prorated refund rule has been invented.

## Required manual test-mode smoke test

Automated tests mock network calls and exercise real SDK signatures. Without account
credentials they cannot prove provider configuration. Before any external sandbox trial:

1. Buy a JEE, CET and combo offer with Razorpay's documented test instruments; inspect
   backend charge, order snapshots, one/two grants and provider capture state.
2. Test failed payment and modal dismissal. Neither may create access by itself.
3. Verify a success twice; replay the signed webhook; send a callback and webhook
   together. Check a single Payment identity and one active grant per mock.
4. Interrupt browser verification and confirm the webhook grants access; reload and
   refresh the order status. Check invalid signatures and cross-student order IDs fail.
5. Temporarily make gateway lookup unavailable; check 503 and retry recovery with no
   processed webhook left behind. Exercise the uncertain-create receipt playbook.
6. Record a verified test refund/revocation and replay success; access must stay off.
7. Confirm no secret appears in network responses, browser storage, build assets or logs.

## Deployment blockers

`/privacy`, `/terms`, `/refund-policy` are unapproved draft placeholders, not legal
advice. Live keys are rejected in both server and client with no enable switch. Owner
legal copy, provider account approval, test-mode smoke evidence, production HTTPS,
monitoring, rate/abuse protection, backup/restore, load tests and operational ownership
are required before considering a separately approved live-mode change. Keep webhook
secret rotation/retry behavior in the deployment runbook; this version accepts one
configured secret and does not provide multi-secret rotation support.
