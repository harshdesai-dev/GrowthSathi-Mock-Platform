# Phase 3 implementation and verification report

Date: 2026-10-02. Branch: `develop`. Starting commit:
`da4fad70d9ce942ac708baddd150f268683d412d`. Working tree was clean before implementation.

## 1. Summary

Phase 3 implements sandbox registration, explicit offers, immutable orders, verified
payments and mock access. No Phase 4 attempts, timers, answer delivery, autosave,
submission, scoring, results, rank or leaderboard were added. No Redis/Celery or push.

## 2. Architecture decisions

[ADR 0008](adr/0008-offers-payments-and-access.md) defines the commerce aggregate,
saleability, integer allocation, durable remote-create receipts, shared reconciliation,
PostgreSQL locking, explicit entitlements and sandbox/live boundary. Prior ADRs remain
unchanged. Browser success is a request to verify, not authority to grant access.

## 3. Models created

`MockOffer`, `MockOfferItem`, `Order`, `OrderItem`, `Payment`, `PaymentWebhookEvent`,
`MockAccessGrant` in `backend/apps/commerce/models.py`. UUID identities, protected
financial history, positive integer money, INR-only orders, constrained statuses,
unique gateway IDs/event IDs/order-mock pairs and one ACTIVE grant per student/mock.

## 4. Migrations created

`backend/apps/commerce/migrations/0001_initial.py` creates seven tables, constraints
and order-reuse index. Fresh PostgreSQL migration and upgrade from the committed
Phase 2 schema passed; SQL confirmed seven commerce tables and the upgrade retained
the two existing exam schemes. No prior migration was rewritten.

## 5. Offers and combo

Explicit one-JEE, one-CET or one-of-each contents. Initial blank prices resolve to
2900/2900/5000 paise. Owner edits affect future orders only. Purchase checks current
paper validity, rule attestation, lifecycle, sales window and redundant ownership.
Partial overlap is allowed at full price, without invented proration.

## 6. Order/payment state machine

CREATED → PENDING → PAID → REFUNDED; PENDING → FAILED → PAID permits eventual
capture reconciliation. PAID and REFUNDED never downgrade on stale failures. Only
the first paid transition grants access. Pending-order reuse uses a 30-minute window,
same student/offer/amount/mock contents. Unknown remote-create outcomes retain CREATED
receipts and require owner reconciliation rather than blind gateway retries.

## 7. Razorpay integration

Official Python SDK 2.0.0, 15-second network timeouts, no automatic create retries.
Ownership checked before payment lookup. SDK callback HMAC uses stored gateway
order ID; payment and order are fetched to confirm identity, amount, INR, receipt
and capture. Both server and browser reject live keys. Only public checkout fields
are returned. Real SDK HMAC checks run in tests; gateway network calls are mocked.

## 8. Webhooks and idempotency

Raw-body SDK signature verification with separate webhook secret; captured/failed
events fetch current provider state. Unique event ID plus body hash, transactional
receipt/effects, duplicate 200, replay mismatch rejection, failed processing rollback.
No sensitive raw payload retention. Callback and webhook use one reconciliation service.

## 9. Access entitlements

Explicit ACTIVE/REVOKED/REFUNDED grants from paid order items. PostgreSQL conditional
uniqueness prevents duplicate active access. Cancellation suppresses effective access.
Revoked/refunded access is not recreated by replay. Overlapping paid coverage survives
a refund of its original source order. Owner commands record verified full-order
refunds/revocations; no automated financial refund action exists.

## 10. APIs added

Public GET mocks/list/detail and offers/list/detail; authenticated POST orders,
GET own order, POST payment verification, GET own access/list/per-mock; signed public
POST webhook. Full request/response contract is in [PAYMENTS.md](PAYMENTS.md).
Unknown purchase fields are rejected. Student payloads whitelist safe metadata only.

## 11. Frontend screens/components

Catalogue `/mocks`, details `/mocks/:mockId`, protected checkout `/checkout/:offerId`,
checkout confirmation/failure/cancellation/pending states, purchased-access block on
`/dashboard`, draft legal pages. Fixed-origin on-demand SDK script loader. Uses actual
GrowthSathi logo and existing charcoal/lime styling. A delayed pending response cannot
overwrite confirmed payment. The auth page links to public offers. No exam UI exists.

## 12. Admin capabilities

Owner-only offer editing and activation/deactivation. Read-only financial records,
filters for state/date/type/mock, protected gateway identities, review-required flags.
`commerce_operation` supports owner-verified link-order, record-refund and revoke-access
operations. Gateway signatures are not exposed in Admin forms.

## 13. Tests added

45 backend commerce cases, including five required PostgreSQL race scenarios and
concurrent duplicates of signed-but-ignored events. Coverage includes
all offer types, initial/future prices, invalid papers/schemes/lifecycle/windows,
snapshot stability, extra purchase fields, signatures, identity/amount mismatches,
failed/authorized/captured states, repeated verification, webhook retries/replay,
authorization, refund eligibility, revoked access, overlap and uncertain remote create.
12 new frontend tests (21 total) cover loading/catalogue/errors/prices, checkout SDK
initialization, authoritative verification, failure/cancel, pending recovery, stale
lookup race, access display, legal labels, live-key rejection and request payloads.
Production asset scan is also wired into CI. Existing Phase 2 threaded test now closes
its worker connection explicitly; all original assertions/tests are retained.

## 14. PostgreSQL and concurrency verification

PostgreSQL 18.6 isolated cluster on 127.0.0.1:55432, not the system service on 5432.
Five new concurrent tests cover duplicate callbacks, callback/webhook race, duplicate
webhooks, repeated order creation, and DB-level entitlement uniqueness. The pre-existing
concurrent question-import test also runs. Final full suite: **165 passed, no warnings**.
Worker-thread connections are closed before test database teardown.

## 15. Commands run

Commands below are the verification commands used; working directories are explicit.
Normal `python` is unavailable here, so the installed pgAdmin Python 3.13 runtime was
bootstrapped with the project-local ignored dependency directory. In a conventional
environment the equivalent is the project `.venv` Python executable.

From `backend`, dependency installation used that runtime with
`sys.path.insert(0, r'.venv\Lib\site-packages')` and `runpy.run_module('pip', run_name='__main__')`:

```text
install --target .venv/Lib/site-packages razorpay==2.0.0
install --target .venv/Lib/site-packages --no-deps chardet==5.2.0
```

The second is an ignored local-runtime fallback only: Windows Application Control
blocked charset-normalizer's native extension. The pure-Python chardet fallback removed
the requests warning. It is not a new product dependency or a committed environment.

Ruff from `backend`:

```powershell
& 'C:\Program Files\PostgreSQL\18\pgAdmin 4\python\python.exe' -c "import sys,runpy; sys.path.insert(0,r'.venv\Lib\site-packages'); sys.argv=['ruff','check','.']; runpy.run_module('ruff',run_name='__main__')"
& 'C:\Program Files\PostgreSQL\18\pgAdmin 4\python\python.exe' -c "import sys,runpy; sys.path.insert(0,r'.venv\Lib\site-packages'); sys.argv=['ruff','format','--check','.']; runpy.run_module('ruff',run_name='__main__')"
```

During editing `ruff check --fix .` and `ruff format .` used the same bootstrap.
Every Django command used this exact prefix, followed by the arguments below:

```powershell
& 'C:\Program Files\PostgreSQL\18\pgAdmin 4\python\python.exe' -c "import sys,runpy; sys.path.insert(0,r'.'); sys.path.insert(1,r'.venv\Lib\site-packages'); sys.argv=sys.argv[1:]; runpy.run_path('manage.py',run_name='__main__')" manage.py
```

```text
makemigrations commerce
migrate --noinput
check
makemigrations --check --dry-run
spectacular --validate --fail-on-warn --file .postgres-data/phase3-openapi.yml
check --deploy --settings=config.settings.production
```

Migration generation initially warned that the unconfigured default database on 5432
was unavailable; no system service/database was changed. All subsequent database checks
used explicit URLs on 55432. The generated initial migration's default-price field was
refined before applying it. Drift check subsequently reported no changes.
The generated OpenAPI artifact stays in the ignored local verification directory.
Deployment checks used dummy non-production `DJANGO_SECRET_KEY`, `JWT_SECRET` and
`GOOGLE_CLIENT_ID`; no real OAuth/payment secret was used or committed.

From the repository root:

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe' -D 'backend\.postgres-data' -l 'backend\.postgres-data\server.log' -o '-p 55432 -h 127.0.0.1' -w start
$env:PGPASSWORD='growthsathi'
& 'C:\Program Files\PostgreSQL\18\bin\createdb.exe' -h 127.0.0.1 -p 55432 -U growthsathi growthsathi_phase3_empty
& 'C:\Program Files\PostgreSQL\18\bin\createdb.exe' -h 127.0.0.1 -p 55432 -U growthsathi growthsathi_phase3_pytest
```

`migrate --noinput` ran against each of:

```text
postgresql://growthsathi:growthsathi@127.0.0.1:55432/growthsathi_phase3_empty
postgresql://growthsathi:growthsathi@127.0.0.1:55432/growthsathi_phase2_empty
```

The first was empty; the second contained the committed Phase 2 schema and two seeded
schemes. Local database credentials above are development-only. SQL inspection used:

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\psql.exe' -h 127.0.0.1 -p 55432 -U growthsathi -d growthsathi_phase3_empty -Atc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_name LIKE 'commerce_%'; SELECT app || ':' || name FROM django_migrations WHERE app='commerce';"
& 'C:\Program Files\PostgreSQL\18\bin\psql.exe' -h 127.0.0.1 -p 55432 -U growthsathi -d growthsathi_phase2_empty -Atc "SELECT app || ':' || name FROM django_migrations WHERE app IN ('commerce','exams'); SELECT count(*) FROM exams_examscheme;"
```

Final PostgreSQL suite from `backend`:

```powershell
$env:DATABASE_URL='postgresql://growthsathi:growthsathi@127.0.0.1:55432/growthsathi_phase3_pytest'
& 'C:\Program Files\PostgreSQL\18\pgAdmin 4\python\python.exe' -c "import sys,runpy; sys.path.insert(0,r'.'); sys.path.insert(1,r'.venv\Lib\site-packages'); sys.argv=['pytest','-q','-p','no:cacheprovider','--create-db']; runpy.run_module('pytest',run_name='__main__')"
```

Targeted commerce passes used the same bootstrap with
`['pytest','tests/test_commerce.py','-q','-x','-p','no:cacheprovider']` on SQLite and
PostgreSQL. An interim full-suite invocation used unsupported `--noinput`; it stopped
before running tests and was corrected to pytest-django's `--create-db`.

Full SQLite suite from `backend`:

```powershell
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
& 'C:\Program Files\PostgreSQL\18\pgAdmin 4\python\python.exe' -c "import sys,runpy; sys.path.insert(0,r'.'); sys.path.insert(1,r'.venv\Lib\site-packages'); sys.argv=['pytest','-q','-p','no:cacheprovider']; runpy.run_module('pytest',run_name='__main__')"
```

From `frontend`:

```powershell
npm.cmd run format
npm.cmd run format:check
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run test
$env:RAZORPAY_KEY_SECRET='phase3-secret-sentinel-not-a-real-credential'
$env:RAZORPAY_WEBHOOK_SECRET='phase3-webhook-sentinel-not-a-real-credential'
npm.cmd run build
npm.cmd run build:check-secrets
```

From repository root after verification:

```powershell
git diff --check
git diff --cached --check
git commit -m "feat: implement payments and mock access"
git status --short
git log -1 --format=%H
& 'C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe' -D 'backend\.postgres-data' -w stop
```

The managed sandbox helper failed before spawning shell commands; scoped escalated
execution was used. No native-app windows were launched and no remote branch was pushed.

## 16. Results and changed files

| Check | Final result |
| --- | --- |
| PostgreSQL full backend suite | 165 passed, no warnings |
| SQLite full backend suite | 159 passed, 6 PostgreSQL-only tests skipped |
| Frontend tests | 21 passed |
| Ruff / format | Passed; 62 Python files formatted |
| Django check / deployment check | No issues |
| Migration drift | No changes detected |
| OpenAPI validation with fail-on-warn | Passed, no warnings/errors |
| Fresh/upgrade PostgreSQL migrations | Passed |
| Frontend format/lint/typecheck/build | Passed |
| Production bundle secret scan | Passed with both server-secret sentinels |
| Git whitespace | Passed |

Changed-file groups (all Phase 3):

- New `backend/apps/commerce/`: models, services, SDK adapter, API, Admin, initial
  migration and `commerce_operation` management command, plus package initializers.
- `backend/config/settings/base.py`, `backend/config/urls.py`, `backend/pyproject.toml`.
- New `backend/tests/test_commerce.py`; one connection-cleanup line in
  `backend/tests/test_exam_administration.py`.
- New `frontend/src/api/commerce.ts`, `commerce.test.ts`,
  `frontend/src/pages/CommercePages.tsx`, `CommercePages.test.tsx`,
  `frontend/src/payments/razorpay.ts`, `frontend/scripts/check-payment-bundle.mjs`.
- `frontend/src/api/client.ts`, `frontend/src/auth/AuthContext.tsx`,
  `auth-context.ts`, `frontend/src/app/AppRouter.tsx`, `AppRouter.test.tsx`,
  `frontend/src/pages/AuthPage.tsx`, `AuthPage.test.tsx`, `DashboardPage.tsx`,
  `OnboardingPage.test.tsx`, `frontend/src/styles/global.css`, `frontend/package.json`.
- `.env.example`, `.github/workflows/ci.yml`, `README.md`, `docs/adr/README.md`,
  new ADR 0008, `docs/PAYMENTS.md` and this report.

## 17. Commit

One commit titled `feat: implement payments and mock access`. Its full hash is reported
in the delivery message and available via `git log -1 --format=%H`. No push requested
or performed. This document cannot embed its own containing commit hash.

## 18. Remaining risks

No real Razorpay account/network checkout smoke test was possible without credentials.
Browser behavior is covered by unit/integration tests, not a credentialed end-to-end
provider session. Public catalogue paper validation is synchronous and needs load
measurement. Unknown remote-create outcomes deliberately require operator handling.
Partial/individual-payment refund accounting remains manual. Single-secret webhook
rotation, monitoring, rate limits and production hardening need deployment review.
No new exam scheme is claimed to be officially revalidated by this implementation.

## 19. Manual Razorpay configuration

Owner must supply test key/secret, enable automatic capture, configure the separate
webhook secret and publicly reachable HTTPS captured/failed webhook, and execute the
smoke-test checklist in [PAYMENTS.md](PAYMENTS.md). Localhost alone cannot receive
provider webhooks. No live keys should be supplied.

## 20. Legal/deployment blockers

Owner-approved privacy, terms and refund-policy copy is still absent. Draft pages
are explicitly non-authoritative. Both client/server reject live keys; production
payments require a later approved change plus legal/provider/operational readiness.
No blocking question prevented sandbox implementation. Phase 4 remains unstarted.
