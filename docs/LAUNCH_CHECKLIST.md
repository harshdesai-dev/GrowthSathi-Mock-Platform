# Paid mock launch checklist

As of 2026-10-03: **NO-GO**. Code/local verification is not paid-launch approval.
Unchecked items require evidence. Owner confirmed **no staging deployment**.
Use [REHEARSAL.md](REHEARSAL.md) for exact credentials, steps and success conditions;
[PHASE8_VERIFICATION.md](PHASE8_VERIFICATION.md) records executed local checks.

Release commit: record final Phase 8 commit and deployment IDs before sign-off.
Owner/operator, rehearsal date and evidence location: **PENDING**.

## CODE

- [ ] Clean release branch reverified immediately before deployment (local Phase 8 commits alone are insufficient).
- [x] Local backend PostgreSQL tests, frontend tests and critical browser fixtures pass.
- [x] Frontend build, lint, types, format, secret bundle check pass with synthetic config.
- [x] Fresh migrations and populated current-schema upgrade pass; no schema changes.
- [ ] CI on the exact release and production Linux/Gunicorn image passes.
- [ ] Final deployed build/env values match the signed-off commit.

## AUTH

- [ ] Real Google login, new/returning user and onboarding on exact HTTPS origin.
- [ ] Real reload, rotation/revocation/logout on Android Chrome and desktop Chrome.
- [ ] Deployed CORS/CSRF/cookie/proxy behavior and rejected untrusted origins verified.

## PAYMENTS

- [ ] Real Razorpay TEST JEE 2900 / CET 2900 / COMBO 5000 paise payments and exact grants.
- [ ] Exact HTTPS webhook URL recorded, signed delivery/retry/duplicate/race verified.
- [ ] Capture setting explicitly inspected in account; captured/paid provider state confirmed.
- [ ] Cancel/fail/repeated verify/already-paid/missed-callback recovery checked with provider.
- [ ] Owner-approved `/privacy`, `/terms`, `/refund-policy` copy implemented and approved.
- [ ] If accepting real money: provider onboarding, Live capture/webhook/credentials and
  separately authorized, reviewed/tested live-mode implementation. Current code rejects live keys.

**LIVE PAYMENTS = BLOCKED.** There is no setting that bypasses this gate.

## EXAM

- [x] Automated fixed timing, accepted autosave, duplicate submit and server boundaries pass.
- [x] Automated refresh/reopen/reconnect/JWT retry and CET transition fixtures pass.
- [x] PostgreSQL late-write/phase/save-submit/start concurrency cases pass.
- [ ] Actual authored JEE/CET paper validation and current official-rule owner attestation.
- [ ] Real deployed fixed start, late start, autosave, reconnect, CET transition and auto-submit.
- [ ] Real Android Chrome and desktop Chrome touch/keyboard payment/exam/result walkthrough.
- [ ] Actual 30s/5min network loss, near-deadline submit, device sleep/reopen and backend restart.

## RESULTS

- [x] Automated calculation, rank, Mock Percentile, privacy and answer review pass.
- [x] Automated correction/withdrawal/recalculation/republication/race tests pass.
- [ ] Owner rehearses real result operations with independently checked answer key and scores.
- [ ] Controlled published-key correction changes score/rank/percentile correctly and retains audit.

## INFRA

- [ ] Actual HTTPS frontend/backend, DNS, proxy and cookie topology verified.
- [ ] Paid always-on backend confirmed; deployment freeze and provider maintenance controls ready.
- [ ] Managed PostgreSQL TLS/private connectivity/UTC/connection sizing verified.
- [ ] Managed backups configured, encrypted retention and pre/post-mock backup ownership verified.
- [ ] Managed isolated restore/PITR timed and checked; local restore evidence is insufficient.
- [ ] Monitoring/alerts actually reach owner; health outage and recovery demonstrated.
- [ ] Staging 500-participant burst and long soak pass agreed latency/integrity gates.
- [ ] Admin edge/network restriction and NAT-safe abuse rules actually verified.
- [ ] Durable HTTPS question images, retention and backup ownership verified if images are used.

## OPERATIONS

- [ ] Complete real private JEE and MHT-CET PCM rehearsal, from TEST purchase to published review.
- [x] Mock-day runbook, freeze recommendation, incident actions and rollback plan written.
- [ ] Owner walks through Admin, uncertain payment recovery and result correction successfully.
- [ ] Frontend and backend rollback exercised on staging without reversing DB migrations blindly.
- [ ] Evidence reviewed, every issue assigned severity/owner, critical/high issues closed.
- [ ] Owner signs off the exact release for the specific paid mock.

## Remaining issue register

| ID | Severity | Issue / resolution required |
| --- | --- | --- |
| C1 | CRITICAL | Live payments are blocked in code; legal copy unapproved. Approve copy/provider readiness, then separately authorize/review/test live support. |
| C2 | CRITICAL | No deployed infrastructure or complete real JEE/CET rehearsal. Provision and complete both before paid admission. |
| H1 | HIGH | Actual Google browser/origin/session checks unverified. Complete Google matrix. |
| H2 | HIGH | Real TEST checkout, capture, reachable webhook and provider retries unverified. Complete payment matrix. |
| H3 | HIGH | Managed backup/restore/PITR and incident recovery unverified. Restore and time recovery on chosen provider. |
| H4 | HIGH | Actual multi-process 500-student capacity/three-hour soak unverified; local burst tails need staging measurement. |
| H5 | HIGH | Real Android/desktop flow, storage, offline/deadline and human result correction rehearsal pending. |
| H6 | HIGH | Deployed proxy trust, admin restrictions, shared-NAT edge limits, monitoring alerts and rollback unverified. |
| M1 | MEDIUM | Throttles are approximate per-process guards. Revisit only if measured abuse/traffic requires stronger protection. |
| M2 | MEDIUM | Backend dependency ranges are not a complete reproducible Linux lock; retain immutable release artifacts and audit exact installed environment. |
| M3 | MEDIUM | Strict frontend CSP requires a provider-compatible Google/Razorpay/media policy trial; existing sanitization/security headers remain. |
| L1 | LOW | Logo remains 1.25 MB after lossless optimization; optional smaller responsive delivery can be evaluated later without redesign. |

CRITICAL means launch must not happen. HIGH strongly blocks paid launch until resolved.
MEDIUM should be addressed or explicitly assessed against measured risk. LOW can follow launch.
No critical/high issue is waived by passing local tests or by this document's existence.
