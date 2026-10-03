# Phase 8 — production hardening and launch readiness

Date: 2026-10-03 (Asia/Calcutta). Scope ends at Phase 8. No push or deployment.

## 1. Executive summary

Implemented production configuration guards, static/runtime deployment configuration,
auth/CSRF/session hardening, abuse guards, safe operational logs/errors, owner payment
recovery, lossless logo delivery, regression coverage and practical launch/recovery guides.
The owner confirmed **no staging deployment exists**. Real providers, devices and the
mandatory full private mock rehearsal remain unverified. **Paid launch is not approved.**

## 2. Repository starting state

Application repository: `GrowthSathi-Mock-Platform/` inside the outer workspace.
Branch `develop`, HEAD `011bb59` (`style: polish growthsathi student experience`), clean.
The required commit was HEAD and therefore an ancestor; no partial Phase 8 changes existed.
The outer workspace's separate Git repository reported the application folder untracked;
all application work and commits were scoped to the inner repository.

Read completely: SPEC, ADRs 0001–0011 and index, Phase 3/4/4.5/5/6 reports, RESULTS,
PAYMENTS, EXAM_ADMINISTRATION, README and `.env.example`. SPEC/prior migrations/accepted
prior ADR decisions were preserved. Baseline before editing: Ruff/format passed;
SQLite 252 passed/23 PG-only skips; frontend 45 tests plus format/lint/types/build passed;
15 browser fixture scenarios passed. No claim that the historical provider checks passed.

## 3. Production architecture

Existing React/Vite frontend, Django modular monolith and PostgreSQL remain. Recommendation:
Vercel plus paid always-on Render and colocated managed PostgreSQL, with same-site HTTPS
custom domains. Owner must choose/provision providers and domains; no silent deployment.
Gunicorn replaces any development server at deployment. No Redis/Celery/microservices added.
Question images remain externally managed HTTPS URLs; ephemeral local media writes are disabled.

## 4. Deployment readiness

Prepared `gunicorn.conf.py` (3 gthread processes × 4 threads as a measurement candidate,
90s timeout/graceful timeout), Python 3.13 marker, WhiteNoise hashed/compressed static storage,
backend wheel template inclusion, Vercel fallback/cache/security headers and CI gates.
Production fails closed for missing critical values, weak placeholder signing keys, SQLite,
non-TLS DB configuration, unsafe origins/hosts and live payment keys. Deployment check and
collected Admin CSS smoke passed with synthetic configuration. Actual Linux runtime,
provider proxy/TLS, availability, sizing and deployed release remain **UNVERIFIED**.

## 5. Google real-login status

**UNVERIFIED.** No real Web client/credentialed browser session was available. No client
secret introduced. Exact required client/origin values and new/returning user, onboarding,
refresh/reload/logout/revocation checks are in REHEARSAL. Google login now requires CSRF;
the frontend bootstraps it first. Certificate lookup has a five-second network timeout.

## 6. Razorpay smoke-test status

**UNVERIFIED with real provider.** Existing real SDK HMAC plus mocked network tests pass
for authoritative amounts, JEE/CET/combo, failures, duplicates, ownership and races.
Owner `commerce_operation reconcile-payment` fetches payment/order truth and reuses the
transactional reconciler; it does not move money. New recovery tests verify two combo
grants once, no duplicate payment, no student operation, and no mismatched amount acceptance.
Real 2900/2900/5000 paise TEST checkout evidence is still required.

## 7. Webhook/capture status

Signature checking, event uniqueness/body-hash replay checks, rollback/retry-safe processing,
duplicate 200 and unknown-order/provider-failure 503 behavior retain their tested semantics.
Endpoint: `https://<actual-api-host>/api/v1/payments/webhook/`. **Actual production hostname
is unassigned; reachability is unverified.** Automatic capture is an application expectation,
not an observed account setting. TEST and eventual Live account capture are **OWNER MANUAL CHECK**.

## 8. Legal-page readiness

All three routes use `LegalDraftPage` and explicitly say unapproved draft. No legal claims
or approvals were fabricated. **LIVE PAYMENTS = BLOCKED** in both client and server; there
is no enable switch. Legal/provider approval and a separately reviewed live implementation
are required before collecting money. TEST-only development/rehearsal may continue.

## 9. Security review

Reviewed auth/profile/catalogue/offers/orders/verify/webhooks/access/start/paper/responses/
heartbeat/submit/results/review/leaderboard and Admin boundaries. Explicit serializers,
per-student queries, server timing, paid grants, omitted answer keys and publication guards
remain. Existing IDOR, price manipulation, early/unpublished leakage, mass assignment,
inactive identity, duplicate payment and PostgreSQL race tests passed.

Concrete fixes: login CSRF; serial refresh rotation/revocation; bounded Google lookup;
read-only role/Google identity fields and blocked student-password/UserAdmin creation;
private no-store API/Admin responses; independent signing-secret validation; secure,
host-only cookies; production 12-character minimum Admin password; process-local auth,
read/order/verify/start throttles. Exam autosave's 600/min allowance remains unchanged.
Provider edge/NAT/admin restrictions and proxy trust remain a deployed HIGH gate.

Source scan found no matches for the selected private-key/JWT/cloud-token patterns in
tracked/nonignored text files; it is not a complete Git-history entropy scan or a guarantee
against every secret format. Bundle scan covers sensitive variable names/configured sentinels.
npm: zero vulnerabilities. pip-audit: no known vulnerabilities in installed distributions;
private `growthsathi-backend` skipped because it is not on PyPI. Gunicorn 23.0.0 audited
separately (Windows excludes its runtime marker): no known vulnerabilities. No real secrets
were read/printed/committed. Backend dependency ranges still need exact-release Linux audit.

## 10. Database readiness

PostgreSQL 18.6 local isolated cluster at 127.0.0.1:55432, never deployment infrastructure.
Fresh migration passed. A restored current-schema baseline had 500 attempts/1,000 responses
before and after `migrate`, with no pending migration. Drift check reported no changes.
No old migration edits or new schema migration. Existing constraints/indexes/transaction
semantics remain; full PostgreSQL suite includes all old race tests plus refresh reuse.
Production requires TLS, health-checked connections, bounded connect timeout and UTC storage.
Managed connection limits, private access and provider configuration remain unverified.

## 11. Backup/restore result

Created a custom-format `pg_dump` of new synthetic `growthsathi_phase8_phase5_results`,
then `pg_restore --no-owner --no-acl --exit-on-error --single-transaction` into the new empty
`growthsathi_phase8_restore`. Dump 1.932s; restore 6.975s (local disk/host only).
Every row of **34 public tables** matched sorted-row SHA-256 checksums, including **112,500
responses and 1,000 published results**. Migration check passed; restored authenticated
report/review/leaderboard each returned 200. These were synthetic test identities.

Dump SHA-256: `6295c538e0d031b0e52d65aee3d07b5e8640a757736874200052939cf97f6e29`.
Artifacts are ignored under `artifacts/phase8/`. No production data was backed up/restored.
Managed backup/PITR, encrypted remote retention and timed incident cutover remain **UNVERIFIED**.

## 12. Health/readiness monitoring

Liveness is DB-independent; readiness SELECT 1 returns 503 safely on DB failures and never
depends on Google/Razorpay uptime. No-store, HTTPS redirect and correlation headers verified.
Owner alert thresholds/monitoring procedure are documented; deployed alert delivery is pending.

## 13. Logging/error handling

Production JSON console logs retain event/status, correlation ID, exception type and stack
locations, excluding request bodies/query strings/framework exception values. Existing attempt
lifecycle logs remain; payment/result/reconciliation events added. Unhandled DRF production
errors return generic JSON, never SQL/tracebacks. Readiness failures are generic. Regression
tests check sensitive logging/error values. Provider logs need the same owner configuration.

## 14. Frontend production review

Build requires HTTPS `/api/v1` and Google client ID; unexpected VITE variables are rejected.
Negative builds confirmed HTTP API and synthetic VITE secret rejection. Only backend checkout
supplies Razorpay's public key. Source maps disabled, existing lazy chunks preserved, hashed
assets immutable/HTML revalidated in Vercel config. Actual CDN fallback, headers and cookies
remain staging checks; browser fixture tests run through Vite, not Vercel.

## 15. Asset optimization

Official logo source retained unchanged. Lossless 1254×1254 WebP delivery is **1,247,538 bytes**
versus **1,660,497 bytes** PNG: 412,959 bytes / **24.87%** saved. Decoded RGBA bytes are identical;
source and output visually inspected. Eight page imports updated, with no redesign/resampling.

## 16. Local load sanity

Same existing guarded real-HTTP harness: 500 synthetic CET students, full 150-question paper,
100 concurrent HTTP clients, one Waitress 3.0.2 process/32 threads, Python 3.13.14,
PostgreSQL 18.6, Windows Ryzen 5 7520U (4 cores/8 logical CPUs), 15.28 GiB RAM.
Test settings, loopback, synthetic entitlements and accelerated test-only server clock.
No provider calls/TLS/WAN/Gunicorn/multi-host/physical-device/three-hour soak. Browser/full
test suites were not run during the benchmark; lightweight review/docs continued.

| Burst | Requests | req/s | p50 ms | p95 ms | p99 ms | Unexpected errors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Starts | 500 | 29.98 | 2992.63 | 4280.41 | 6473.17 | 0 |
| PC paper | 500 | 24.63 | 3992.28 | 4540.84 | 4659.19 | 0 |
| Heartbeat | 500 | 68.73 | 1488.55 | 1737.81 | 1847.11 | 0 |
| Save v1 | 500 | 63.88 | 1451.85 | 2180.84 | 2311.14 | 0 |
| Save v2 | 500 | 68.80 | 1419.74 | 1597.12 | 1802.95 | 0 |
| Save v3 | 500 | 50.34 | 1765.11 | 2517.52 | 6183.63 | 0 |
| Lost acknowledgement | 500 | 65.43 | 1433.52 | 1773.56 | 1882.04 | 0 |
| Stale reconnect (409) | 500 | 60.28 | 1688.54 | 1954.22 | 2085.95 | 0 |
| Closed PC (409) | 500 | 90.73 | 1078.74 | 1200.17 | 1269.97 | 0 |
| Math paper | 500 | 29.18 | 3188.18 | 4454.19 | 4783.32 | 0 |
| Math save | 500 | 59.38 | 1669.96 | 2011.04 | 2089.99 | 0 |
| Submit | 250 | 67.00 | 1421.68 | 1651.96 | 1745.49 | 0 |
| Duplicate submit | 250 | 43.57 | 1402.49 | 4305.12 | 5543.48 | 0 |
| Late save (409) | 250 | 96.11 | 961.14 | 1214.80 | 1513.20 | 0 |
| Deadline recovery | 250 | 82.09 | 1145.20 | 1387.15 | 1481.96 | 0 |

**6,500 requests, 0 unexpected errors, 1,250 intentional 409s**. Exactly 500 attempts,
250 SUBMITTED/250 AUTO_SUBMITTED, 1,000 responses with correct PC/Math versions, no
late/stale overwrites, idempotent reconciliation. Starts max 6.89s. Start p99 <5s and
save p99 <2s targets are **not met consistently**; no capacity certification. These are
not controlled causal comparisons with Phase 4.5's 3.92s p99. Actual deployment sizing,
burst and soak remain a HIGH blocker. No evidence here requires Redis/Celery.

500-participant result service benchmark, independently checked scores/membership:

| Exam | Responses | Verify | Calculate | Publish |
| --- | ---: | --- | --- | --- |
| JEE | 37,500 | 0.570s / 32 queries | 1.296s / 35 queries | 0.617s / 49 queries |
| CET | 75,000 | 0.926s / 35 queries | 3.192s / 38 queries | 1.188s / 52 queries |

## 17–20. Devices, failure and full mock/result rehearsal

Real Android Chrome/desktop Google + TEST checkout + full mock: **PENDING**.
Browser fixture checks passed at 360/390/430/768/1024/1440px, including reconnect,
IndexedDB refresh/reopen, JWT recovery, final submit and CET phase rejection/transition.
Fixtures/accelerated unit clocks do not prove actual carrier outage, OS crash or touch.
No complete credentialed private JEE/CET mock or human answer-key correction rehearsal
was claimed. Automated calculation/correction/withdrawal/republication passed. REHEARSAL
specifies the exact real flow, controlled accounts, network/device matrix and evidence.

## 21–22. Runbooks and rollback

Created DEPLOYMENT, MOCK_DAY_RUNBOOK, REHEARSAL, LAUNCH_CHECKLIST and ADR 0012. Covers
T-24h/T-2h/T-30m/live/post-exam, 24-hour freeze, backend/DB/payment/Google/access/key/result
incidents, owner credential handling, backups, monitoring and frontend/backend rollback.
No blind DB reversal. Explicitly notes old Phase 7 frontend lacks the new login CSRF header;
rollback must use compatible releases. Actual deployed rollback remains unverified.

## 23–24. Checks, exact results and execution notes

| Check | Result |
| --- | --- |
| Full PostgreSQL release pytest | **323 passed**, no skips, 191.89s; all 24 PG-only cases ran |
| Full SQLite pytest | 298 passed, 24 PG-only skipped, 69.81s (before final Google timeout-only change) |
| Frontend final Vitest | 46 passed / 12 files, 18.36s |
| Browser Chromium fixtures | 15 passed, ~1.1 minutes; six viewport widths |
| Frontend format / ESLint / TypeScript | Passed |
| Production frontend build / secret sentinels | Passed, WebP delivered |
| Rejected unsafe builds | HTTP API / unexpected VITE secret both refused |
| Ruff lint / format | Passed; 94 Python files |
| Django system / deploy fail-on-WARNING | Passed, zero issues |
| OpenAPI validate / fail-on-warn | Passed |
| Migration drift / fresh / populated upgrade | Passed; no schema change |
| Production collectstatic / HTTPS / hashed Admin CSS | Passed with synthetic configuration |
| Wheel contents | All four owner Admin templates included |
| Dependency audits | No known vulnerabilities, limitations in section 9 |
| Source/bundle secret scan | No selected-pattern/sentinel findings |
| Local backup/restore / published API smoke | Passed; 34 complete tables match |
| Local load / result benchmark | Integrity passed; latency limitations above |
| Git whitespace | Passed |

Tooling failures/warnings were not suppressed: sandbox launcher failed before execution,
so scoped approved external-shell commands were used. Initial embedded pip self-modification
guard was corrected by standard Python 3.13; duplicate-target/cache warnings affected local
tool installation, not dependency upgrades. Initial static collection failed with WhiteNoise's
optional hashed-only deletion on a Windows filename containing `?v=`; removing that optional
mode fixed collection. Initial production smoke import order, load PYTHONPATH precedence and
standalone test-client Host were corrected and rerun. No application test failure was hidden.
Playwright emitted harmless NO_COLOR/FORCE_COLOR warnings; Git reports normal LF/CRLF
conversion notices. Separate Gunicorn audit warns that `--no-deps` is not a hashed lock.
PowerShell labels captured INFO stderr as NativeCommandError in result benchmark output;
both benchmark exit status and independent integrity assertions succeeded.

Reproduction uses Python 3.13 and Node 24 with installed dependencies. This Windows session
used `C:/Users/Harsh Desai/AppData/Local/Python/pythoncore-3.13-64/python.exe`, with backend
root **before** `.venv/Lib/site-packages` in PYTHONPATH. PostgreSQL tools are in
`C:/Program Files/PostgreSQL/18/bin`. Only documented local test credentials were used.

```sh
# backend, isolated PostgreSQL test DATABASE_URL
python -m ruff check .
python -m ruff format --check .
python -m pytest -q -p no:cacheprovider
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py spectacular --validate --fail-on-warn --file ../artifacts/phase8/openapi.yml
# Synthetic production configuration from test_production_hardening.production_env;
# load values BEFORE django.setup, without importing the Django test module first.
python manage.py check --deploy --fail-level WARNING --settings=config.settings.production
python manage.py collectstatic --noinput --settings=config.settings.production
python -m pip wheel . --no-deps --wheel-dir ../artifacts/phase8/wheels
python -m pip_audit --path .venv/Lib/site-packages --progress-spinner off
# Fresh migrated empty databases, exact suffix safety guards retained:
python scripts/phase4_load.py --students 500 --concurrency 100 --threads 32
python scripts/phase5_results.py
# SOURCE_DATABASE_URL / RESTORE_DATABASE_URL refer only to local growthsathi_phase8_* DBs
python scripts/verify_restore.py
# frontend; explicit synthetic HTTPS/Google build env and payment-secret sentinels
npm run format:check
npm run lint
npm run typecheck
npm test
npm run build
npm run build:check-secrets
npm run test:browser
npm audit --audit-level=high
# repository root
git diff --check
```

DB names: `growthsathi_phase8_fresh`, `_pytest`, `_upgrade`, `_phase4_load`, `_phase5_results`,
`_restore`. Do not reuse populated load DBs or remove guards. Backup uses pg_dump custom/no-owner/
no-acl and pg_restore exit-on-error/single-transaction into an empty destination, as DEPLOYMENT
documents. Schema ledger is unchanged from baseline. No real provider call was faked as success.

## 25. Files changed

- Environment/CI: `.env.example`, `.gitignore`, `.github/workflows/ci.yml`.
- Backend config: `config/settings/base.py`, `production.py`, new `config/production_validation.py`,
  `gunicorn.conf.py`, `.python-version`, `pyproject.toml`.
- Auth: `apps/accounts/admin.py`, `api/serializers.py`, `api/views.py`, `services.py`, new `sessions.py`.
- Operations: `apps/common/api/exceptions.py`, `api/views.py`, new `observability.py`, `storage.py`,
  `throttles.py`; `apps/attempts/api.py`; `apps/commerce/api.py`, `services.py`,
  `management/commands/commerce_operation.py`; `apps/results/services.py`.
- Backend verification: new `tests/test_production_hardening.py`, `scripts/verify_restore.py`;
  tests `test_admin_bootstrap.py`, `test_commerce.py`, `test_errors.py`, `test_sessions.py`,
  `test_google_auth.py`.
- Frontend deployment/auth: `vite.config.ts`, new `vercel.json`, `scripts/check-payment-bundle.mjs`,
  `src/api/client.ts`, new `src/api/client.test.ts`.
- Asset: new `src/assets/brand/growthsathi-logo.webp`, brand README; imports in Auth, Commerce,
  Dashboard, Exam, Foundation, Landing, Onboarding and Result page files.
- Docs: root README, PAYMENTS, ADR index/new 0012, DEPLOYMENT, MOCK_DAY_RUNBOOK, REHEARSAL,
  LAUNCH_CHECKLIST and this report. Ignored dumps/builds/evidence are not committed.

## 26. Commits

- `696c0174bdef8a5e5b6bfcfa0b2ad2f6cfc6d049` — production deployment/security hardening.
- `f30421fba5d0b628e00f8a65e2e0a0fe202546cf` — lossless logo delivery.
- The containing `docs: add Phase 8 launch operations and verification` commit — runbooks/report.

The final delivery reports all three hashes; a document cannot embed its own containing
commit hash. Retrieve with `git log --oneline 011bb59..HEAD`. No rewrite, squash or push.

## 27–29. Remaining severity

CRITICAL: live payment implementation is still intentionally blocked/legal approval absent;
no actual deployment or complete mandatory credentialed private rehearsal.
HIGH: real Google/TEST payment/webhook/capture; managed restore/PITR; actual Gunicorn/load/soak
capacity; physical devices/network/human correction; deployed edge/proxy/monitoring/rollback.
MEDIUM: process-local throttling limitations, exact Linux dependency lock/release audit,
provider-compatible strict frontend CSP trial. LOW: optional smaller responsive logo delivery.
Full issue IDs/resolution requirements: LAUNCH_CHECKLIST. No critical/high gate is waived.

## 30. Manual owner actions

Choose/provision always-on staging and managed PostgreSQL; assign exact same-site HTTPS
origins; securely configure Google Web client and Razorpay TEST keys/webhook secret; inspect
capture settings; approve legal copy; perform REHEARSAL and actual restore/load/rollback/device
checks; close and document all critical/high issues. Only then consider separately authorizing
live support and its own provider checks. Do not paste secrets into chat or commit them.

## 31. Final checklist status

Local implementation/automated evidence is recorded. External launch gates remain unchecked.
The existence of runbooks does not mean the owner has rehearsed them. No production-ready,
real-provider-success, real-device-success or full-rehearsal claim is made.

## 32. Final verdict

**NO-GO** for a real paid mock. Stop after Phase 8; no Phase 9 work or new product features.
