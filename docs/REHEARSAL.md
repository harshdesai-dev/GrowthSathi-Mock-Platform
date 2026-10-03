# Required private rehearsal and evidence

Status: **UNVERIFIED / PENDING** on 2026-10-03. No staging deployment, real provider
credentials or physical-device session was supplied. Automated fixtures do not satisfy
this checklist. Live payments remain blocked, including by code, until a separately
approved live-mode change and owner-approved legal/payment readiness.

## Evidence sheet

For every step record operator/date, commit, frontend/backend deployment IDs, exact origins,
browser/device/OS, mock/offer/order/run IDs, expected/observed behavior and issue severity.
Use sanitized screenshots and request IDs; never save tokens, payment credentials or secrets.
Do not copy production student data into rehearsal. Keep evidence private and linked from
LAUNCH_CHECKLIST. Blank or pending evidence means the check has not passed.

## Provision a private environment

1. Owner provisions separate always-on staging backend, frontend and managed PostgreSQL
   using DEPLOYMENT. Select exact HTTPS domains and validate TLS/proxy/CORS/cookies.
2. Use an isolated staging project and controlled test accounts. Do not list rehearsal offers
   on the public production catalogue. There is no product-level private-mock feature;
   use staging access controls, while keeping the HMAC webhook endpoint provider-reachable.
3. Configure Google Web client and Razorpay TEST keys/separate webhook secret through the
   provider's secure settings. Never put test secrets in frontend build variables.
4. Bootstrap the owner, assign password through the non-echoing command, and rehearse Admin
   login, paper import/validation and result operations. Do not seed fake payments into this
   real provider rehearsal. Automated load fixtures belong in different disposable databases.

## Google: real ID-token login

Required: OAuth 2.0 **Web application** client ID. No Google client secret or OAuth code flow.
Set identical GOOGLE_CLIENT_ID and VITE_GOOGLE_CLIENT_ID. In Authorized JavaScript origins,
include `http://localhost:5173` for development (and `http://localhost` as required by Google
local setup) and the exact production/staging HTTPS frontend origins. This callback flow
does not require a redirect URI. If the consent project is in testing, allow the test accounts.

- [ ] On desktop Chrome and Android Chrome, `/auth` renders the official Google button.
- [ ] No origin/client-ID error; popup or supported FedCM login completes on the exact origin.
- [ ] CSRF bootstrap succeeds; Google ID token is POSTed with CSRF token; backend verifies it.
- [ ] New account reaches onboarding; name/email appear correctly, phone/class/target save.
- [ ] Returning account reaches dashboard without repeating completed onboarding.
- [ ] Refresh/reload preserves session; access JWT is only in memory; refresh cookie is
  Secure/HttpOnly/API-host-only/path `/api/v1/auth/`; SameSite matches the chosen architecture.
- [ ] Refresh rotates; replay of a previously rotated cookie returns 401.
- [ ] Logout clears cookie; replay of that revoked cookie returns 401. Perform replay only in
  a private local test console, do not paste tokens into logs/evidence/chat.
- [ ] Untrusted Origin and missing CSRF on login/refresh/logout return 403; inactive user is denied.
- [ ] Admin password session alone cannot authenticate the student APIs.

Expected success: all listed steps on actual configured origins, with no cookie rejection.
Mocked Google verification tests are separate evidence only.

## Razorpay TEST-mode capture and webhook

Required: TEST key ID/secret, distinct webhook secret, reachable HTTPS API origin, and owner
Dashboard access. **OWNER MANUAL CHECK**: select Test Mode and explicitly inspect capture settings.
Application expects automatic capture and grants access only for independently fetched CAPTURED
payment plus matching paid order/amount/currency/receipt. AUTHORIZED alone never unlocks a mock.
No application endpoint automatically captures an authorized payment. Repeat capture configuration
review in Live Mode only when legal/payment approval and a separately reviewed live change exist.

Webhook endpoint path is exactly `/api/v1/payments/webhook/`, including trailing slash.
The complete deployed URL must be recorded as `https://<actual-api-host>/api/v1/payments/webhook/`.
**Exact production hostname is UNASSIGNED**; no real URL can yet be verified. Subscribe to
`payment.captured` and `payment.failed`; configure the exact backend secret. Never disable HMAC
or protect this route with a browser-only access challenge. Verify HTTPS POST reaches Django
without a redirect. GET is not a webhook delivery test.

Use Razorpay's currently documented test instruments, never real payment credentials.
Separate test accounts avoid already-owned entitlement overlap during the three purchases.

| Purchase | Backend amount | Expected active grants |
| --- | ---: | --- |
| JEE | 2900 paise | Exactly the selected JEE mock |
| CET | 2900 paise | Exactly the selected CET mock |
| COMBO | 5000 paise | Exactly one selected JEE + one selected CET |

- [ ] Each purchase: frontend chooses offer -> server creates authoritative order -> TEST
  checkout -> test payment -> server signature/provider verification -> PAID -> correct grants.
- [ ] Confirm provider capture mode/state directly and record sanitized provider/local references.
- [ ] Inspect OrderItems and price snapshots; browser-modified amounts are rejected.
- [ ] Webhook has valid signature/event ID, records one processed event and returns 200.
- [ ] Cancel checkout: no access from dismissal, no invented successful payment.
- [ ] Failed payment: no grant. A later real capture may recover FAILED to PAID.
- [ ] Stop callback verification after successful payment; webhook alone reconciles PAID/access.
- [ ] Verify twice; replay same signed webhook; simultaneous callback + webhook: one Payment
  identity and at most one ACTIVE grant per student/mock. Already-paid lookup has no checkout.
- [ ] Reuse event ID with changed body or alter signature: rejected, no mutation.
- [ ] Missing signature: rejected. Record 400; never treat it as a successful provider smoke.
- [ ] Temporarily fail staging gateway lookup: 503, no processed event receipt committed;
  restore lookup and replay delivery -> 200 and correct access. Provider retries remain safe.
- [ ] Unlinked remote order -> 503; match receipt/amount/INR, link via owner command, then replay.
- [ ] Recover a missed event with owner `reconcile-payment`; repeat without duplicate grants.
- [ ] Another student cannot inspect/verify the order. Revoked/refunded access does not reappear
  after replay. Never mark an entire order refunded for only a partial/extra-payment refund.
- [ ] No backend secret/signature or payment instrument appears in browser assets or general logs.

Owner must inspect delivery history/retry behavior and set alerts. TEST and Live webhook/capture
settings are separate checks; TEST success is not Live approval. Legal pages `/privacy`, `/terms`,
`/refund-policy` are currently explicit unapproved drafts. **LIVE PAYMENTS = BLOCKED**.

## Full JEE and CET mock, real browser to deployed backend

Run both configured full-duration papers. Do not shorten a production scheme or alter server
time to claim rehearsal success. Use 3-5 controlled accounts, including a late starter, an
offline/recovering student and a blank/no-start control. TEST-purchase each required entitlement.

1. Owner authors/imports a complete paper, records actual official-rule review, independently
   checks key, validates it, opens registration, activates exact JEE/CET/combo offers and schedules.
2. Students complete real Google login/onboarding, TEST checkout and provider verification.
   Confirm purchased dashboard state, countdown, instructions and common IST schedule.
3. Before fixed start, start is denied. At start, student starts once. Double click/resume returns
   the same attempt. Late start retains the original end and current CET phase.
4. Answer MCQ/numerical questions, clear/change/mark for review, use palette and Save & Next.
   Compare accepted response versions in read-only Admin with the test script's expectations.
5. Refresh and reopen; time does not reset, acknowledged answers remain. Follow network matrix.
6. CET: PC only before global minute 90; at minute 90 PC locks and Mathematics becomes active.
   Attempt a stale PC request after the boundary: 409 and no response overwrite. Final submit
   is not available during PC. Late arrival during Math cannot unlock PC.
7. One student manually submits after flushing; duplicate submit is idempotent and later writes
   fail. Another remains open until global end; auto-submit retains all server-accepted responses.
8. Owner closes, reconciles twice, backs up, verifies key, calculates and inspects draft results.
   Before publication, report/review/leaderboard stay unavailable and no answer-key fields leak.
9. After earliest release, publish. Verify each independent score/count, ties, ranks,
   `100 * count(score <= own) / eligible_count` rounded to two decimals as **Mock Percentile**,
   surname masking and private report/review. Empty auto-submission/no-start exclusions apply.
10. Rehearse correction: withdraw published run with reason; confirm all subsequent student
    result/review/history/leaderboard reads are gated; correct a known key via audited form;
    verify, recalculate, inspect changed score/rank/percentile, republish atomically. Preserve old run.
11. Record every issue, owner/action, severity, retest evidence, then perform backup/restore and
    deployment rollback smoke. Do not publish a GO with incomplete steps.

## Network and device matrix

Required physical devices: Android Chrome and desktop Chrome. Record model/OS/browser version.
Add another actual mobile browser if available; simulated viewport widths do not count as devices.

- [ ] Touch/keyboard login, dashboard, TEST payment modal, countdown and exam navigation work.
- [ ] Numerical keyboard, negative/decimal values, focus, scroll and sticky controls are usable.
- [ ] Palette opens/closes and does not hide active questions or submission controls.
- [ ] Offline 30 seconds while editing, then reconnect well before phase end; latest queue syncs.
- [ ] Offline 5 minutes, same recovery; accepted response versions remain correct.
- [ ] Refresh during temporary failure; reopen browser/page with storage preserved, then reconnect.
- [ ] Expire access JWT during the exam (wait its actual five-minute lifetime); refresh and retry
  succeed without clearing the durable queue. Test a failed refresh and separate-tab re-login.
- [ ] Let a save succeed server-side but lose its acknowledgement; replay preserves the response.
- [ ] Near deadline: accepted saves stay accepted; device-only drafts arriving after the server
  phase/end boundary are rejected visibly. Do not claim offline drafts are guaranteed accepted.
- [ ] Brief staging backend restart: accepted response and original deadline survive, retries resume.
- [ ] Submit with pending saves: successful flush, retry/cancel, and explicit saved-only fallback.
- [ ] Report, masked leaderboard and answer review work with actual touch and keyboard.

Expected success: no valid **server-accepted** answer silently disappears or is overwritten by an
older replay. Record unsupported browser storage/private-mode behavior; never clear storage to
make a failed durability check appear successful.

## Staging load sanity (still pending)

Use a separate disposable managed database and synthetic-only accounts, with provider calls
excluded from the load generator. Do not load-test Google/Razorpay or a live student exam.
The existing `phase4_load.py` is a **local** one-process harness with a test-only clock; it must
not be pointed at a deployed target or described as a staging test. No override endpoint ships.

For deployed measurement, owner provisions an isolated copy using the actual Gunicorn/process,
proxy/TLS, database and media configuration. Seed controlled fixtures offline through a trusted
management shell, never a public seed endpoint. Use real server timing; generate up to 500
distinct JWT-authenticated students and retain synthetic paid-access provenance in evidence.
Run starts, initial paper fetch, normal saves and 30-second heartbeats, reconnect retry, duplicate
submit, and deadline behavior. Run result calculation separately after the exam. Require a
long-duration/three-hour soak in addition to burst samples. Protect tokens in the generator.

Record provider/region, commit, CPU/RAM, instance/process/thread counts, DB plan/connection limit,
client location/concurrency, request count/rate, throughput, p50/p95/p99/max, expected rejections,
unexpected errors, connection/lock/CPU/memory observations and accepted-answer integrity.
Begin with 100 concurrent HTTP requests for the 500 students and repeat the expected worst burst
after warm/cold restart. Do not assume this equals 500 simultaneous requests.

Proposed acceptance for owner review: zero unexpected errors or lost accepted responses; start
p99 <5s, save/heartbeat/submit p99 <2s, no sustained resource exhaustion, and generous margin to
60s start/15s ordinary client timeouts. These are operational targets, not a capacity certification.
If actual deployment cannot sustain the expected burst, **NO-GO** until resized/fixed and retested.
