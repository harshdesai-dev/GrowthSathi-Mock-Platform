# ADR 0008: Explicit offers, verified payments and mock access

Status: Accepted for Phase 3, 2026-10-02. Implements the approved Phase 3 request;
extends ADRs 0002 and 0004 without changing their business rules.

## Boundary

`apps.commerce` owns seven models: MockOffer, MockOfferItem, Order, OrderItem,
Payment, PaymentWebhookEvent and MockAccessGrant. PostgreSQL is authoritative.
No attempts, question delivery, scoring, results, Redis or Celery are introduced.
Student-facing serializers are explicit allowlists, separate from authoring models.

## Offers and money

An inactive offer is editable in owner Admin. Activation validates its explicit
contents: JEE = one JEE_MAIN mock; CET = one MHT_CET_PCM mock; COMBO = exactly
one of each. Duplicate mock items are constrained in PostgreSQL. Deactivate before
changing price or contents; existing order snapshots never change. Blank initial
prices resolve to 2900/2900/5000 paise, respectively. Prices must be positive integers.

One service, `validate_saleability`, requires an active offer, an open half-open
sales interval `[start, end)`, active exam type/scheme, per-mock official-rule
attestation and a currently valid complete paper. Mock status must be
REGISTRATION_OPEN, SCHEDULED or LIVE and server time must precede `ends_at`.
Allowing LIVE sales does not promise a fresh full-duration exam: Phase 4 must
enforce the existing global deadline/late-arrival rules. DRAFT, CLOSED,
RESULTS_PUBLISHED, CANCELLED and ended mocks cannot be sold.

A student owning every included mock cannot repurchase the offer. Partial overlap
is permitted at the full advertised price; there is no inferred proration or new
discount. Initial combo is 5000 paise, not a dynamically inferred pair of dates.
Each order snapshots offer name, slug, type, charged amount and actual mock IDs.
Order-item allocation splits equally in integer paise; UUID ordering determines
which items receive a one-paisa remainder. Allocations always sum to the charge.
They are bookkeeping snapshots, not an automatic partial-refund policy.

## Order creation and uncertain remote outcomes

Acquire the student row, then offer row, then mock rows in UUID order. Check
saleability and create snapshots in a transaction. Reuse a PENDING order less than
30 minutes old if amount and contents still match. A CREATED order with no linked
gateway ID is always reused: it is either in flight or requires reconciliation.

Commit the CREATED receipt before requesting a Razorpay order, outside the DB
transaction. Use the UUID hex as the gateway receipt and disable partial payment.
Gateway calls have 15-second timeouts and no automatic create retry. Link the
verified response in a second transaction. A crash/timeout cannot roll back the
only evidence of an external order. The owner can fetch and link the exact gateway
order using `commerce_operation link-order`; amount, INR and receipt must match.
This is not a claim of exactly-once remote creation. Until linked, checkout stays
blocked. If no gateway order exists, the owner must investigate and arrange a
single matching gateway order through the provider's supported operations before
linking it; do not blindly retry or delete local receipts.

## Verification and state transitions

The browser success handler is an untrusted notification. The authenticated
verification endpoint first resolves an order belonging to that student. It then
uses the official Razorpay SDK to validate HMAC using the **stored** gateway order
ID. It fetches both payment and gateway order with server credentials. IDs, receipt,
amount, currency, captured flag, gateway order paid state and amount paid must match.
An AUTHORIZED payment is not sufficient for access.

Order transitions are centralized:

```text
CREATED -> PENDING -> PAID -> REFUNDED
              |        ^
              v        |
            FAILED ----+
```

FAILED can later become PAID when a valid capture is confirmed. Stale failures do
not downgrade captured payments or paid orders. Payment records have AUTHORIZED,
FAILED, CAPTURED and REFUNDED states. Gateway IDs are globally unique; terminal
payment states are not overwritten by delayed observations. PAID's `paid_at` is
assigned only once. A second verified capture is recorded and flagged for manual
duplicate-payment review, never an extra entitlement grant.

## Webhooks and concurrency

Webhook authentication uses the SDK HMAC over the unmodified raw UTF-8 body and the
separate webhook secret, not student JWT. Only payment.captured and payment.failed
are reconciled. Other signed events are recorded as IGNORED. Store unique event ID,
type, SHA-256 body hash and processing timestamps, not full payloads or banking data.
An event-ID/hash mismatch is rejected. A successful duplicate returns HTTP 200.

Fetch current gateway state instead of trusting event ordering. Then acquire the
student row and process the event and financial effects in one transaction. A
failure rolls back the event receipt so Razorpay can retry. Unknown gateway order
IDs return 503 for operator reconciliation, including the remote-create crash gap.
Callbacks and webhooks call the same `reconcile_payment` service. Both lock student
then order; grant creation also locks mocks in UUID order. DB uniqueness is the
last defense for payment ID, gateway order ID, event ID, order/mock items and the
conditional `(student, mock)` ACTIVE grant. No background worker is required.

## Access and refunds

Access is an explicit MockAccessGrant linked to a paid OrderItem, not an inference
from frontend state or order status. Repeated reconciliation of a paid/refunded
order does not regrant revoked access. Overlapping paid offers share one ACTIVE
grant. Refunding its source order transfers the grant to another still-paid
covering item when available; otherwise it becomes REFUNDED.

Capture after cancellation remains recorded as PAID (money really moved), but a
cancelled mock receives a REVOKED grant and the order is flagged for manual refund
review. Cancellation after a grant exists causes access APIs to report no access;
the grant remains auditable until the owner records revocation/refund. Future
attempt authorization must check both entitlement and mock lifecycle/deadlines.

No refund API is called. Owner-only commands record an already verified full-order
refund or explicit revocation with actor/time/reason/reference. Eligibility remains
exactly ADR 0004. Partial refunds or refunding only an extra payment on a paid order
require manual provider/accounting handling and future granular integration; never
mark the entire order REFUNDED for such a partial operation.

## Sandbox and remaining limits

Backend and frontend reject live keys. Legal routes are conspicuous draft
placeholders. No setting turns on live mode: a later approved change, owner legal
copy, provider onboarding and real integration smoke tests are required.
`RazorpayGateway` is replaceable for deterministic tests and eventual workers.
Public catalogue validation currently rechecks papers synchronously: benchmark
before scale; future cached attestations must have explicit invalidation, not weaken
the current purchase-time check. API abuse/rate limiting, production observability,
refund automation and gateway-secret rotation playbooks need deployment review.

Official references checked during implementation:

- [Razorpay Standard Checkout integration](https://razorpay.com/docs/payments/payment-gateway/web-integration/standard/integration-steps/)
- [Webhook validation and duplicate delivery](https://razorpay.com/docs/webhooks/validate-test/)
- [Official Python SDK](https://github.com/razorpay/razorpay-python)
