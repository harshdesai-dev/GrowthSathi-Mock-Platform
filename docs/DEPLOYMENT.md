# Phase 8 deployment and recovery

Status on 2026-10-03: **not deployed**. The owner confirmed that no staging exists.
This guide prepares deployment; it is not an infrastructure or paid-launch approval.
Use [LAUNCH_CHECKLIST.md](LAUNCH_CHECKLIST.md) as the release gate.

## Architecture and owner decision

The existing SPEC recommends Vercel, Render or Railway, and managed PostgreSQL.
The simplest candidate is Vercel for `frontend/`, one **paid always-on** Render web
service for `backend/`, and paid managed PostgreSQL in the backend's region.
Keep the Django monolith and PostgreSQL authority. No Redis, Celery, Kubernetes or
new auth system is required by the available measurements.

Owner action: choose the providers/region/paid plans, provision separate staging and
production projects, and assign HTTPS custom domains under the same registrable
domain, for example `app.<owned-domain>` and `api.<owned-domain>`. Record the **actual**
origins and deployment IDs in the rehearsal evidence. Example domains in this guide
are placeholders, not deployed URLs. Do not use a sleeping tier or the local 55432
PostgreSQL cluster as launch infrastructure. Railway remains a viable alternative,
but its proxy, backup and deployment controls must be verified separately.

Same-site custom domains avoid relying on third-party cookie acceptance. A Vercel
default domain plus an unrelated backend default domain is cross-site; Secure plus
SameSite=None is necessary but may still fail browser tracking protection. Prefer
same-site domains. If cross-site is retained, set BOTH refresh and CSRF SameSite=None
and prove login/reload/logout on the target devices before approval.

No deploy or account purchase was made. Hosting remains an owner decision.

## Production environment

Set process variables in the provider's secret manager. Django does not load `.env`.
Use `DJANGO_SETTINGS_MODULE=config.settings.production` for **build, release and runtime**.
Never log environment dumps, put passwords in shell history, or share secrets in chat.

| Variable | Required configuration |
| --- | --- |
| `DJANGO_DEBUG` | Explicit `false` |
| `DJANGO_SECRET_KEY`, `JWT_SECRET` | Separate randomly generated secrets, at least 50 characters; no reused examples |
| `DATABASE_URL` | Managed PostgreSQL, database-specific least-privilege role, `sslmode=require`; prefer `verify-full` and provider CA |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated exact API hostnames; no schemes/wildcards/localhost |
| `FRONTEND_URL` | Exact HTTPS origin, no trailing slash |
| `CORS_ALLOWED_ORIGINS` | Explicit HTTPS browser origins; includes FRONTEND_URL; no arbitrary preview domains |
| `CSRF_TRUSTED_ORIGINS` | Same explicit browser origins, plus API origin only if needed for Admin |
| `GOOGLE_CLIENT_ID` | OAuth **Web** client, identical to frontend build value |
| `RAZORPAY_KEY_ID` | `rzp_test_...` only |
| `RAZORPAY_KEY_SECRET` | Provider TEST secret |
| `RAZORPAY_WEBHOOK_SECRET` | Independently generated secret, matching configured TEST webhook |
| `AUTH_ACCESS_TOKEN_MINUTES`, `AUTH_REFRESH_TOKEN_DAYS` | Defaults 5 minutes / 7 days; enforced upper bounds 15 minutes / 14 days |
| `AUTH_REFRESH_COOKIE_SAMESITE`, `CSRF_COOKIE_SAMESITE` | Lax on recommended same-site domains; reviewed cross-site exception described above |
| `AUTH_REFRESH_COOKIE_DOMAIN`, `CSRF_COOKIE_DOMAIN` | Empty: cookies remain API-host-only |
| `DJANGO_TRUST_PROXY_HEADERS` | Set `true` only after confirming proxy strips/replaces incoming forwarded headers and direct backend access is blocked |
| `TRUSTED_PROXY_COUNT` | Exact trusted proxy count for DRF client-IP calculation; verify provider chain before setting, do not guess |
| `WEB_CONCURRENCY`, `GUNICORN_THREADS` | Initial measurement candidate 3 processes / 4 threads each |
| `MEDIA_STORAGE_CONFIG` | Empty; upload storage is not implemented and production rejects local uploads |
| `LOG_LEVEL` | INFO |

Production startup fails closed for missing critical settings, weak placeholders,
SQLite, non-TLS database configuration, wildcard hosts, HTTP origins and live payment
keys. Validation verifies configuration shape, not provider credentials, certificates,
network reachability, or account approval. Deployed readiness must be checked too.

Refresh cookies are Secure, HttpOnly and scoped to `/api/v1/auth/`. CSRF and Admin
session cookies are Secure; CSRF token bootstrap returns the token in JSON. Google
login, refresh and logout require CSRF. Refresh rotation is blacklist-backed and
serialized in PostgreSQL. API authentication remains JWT-only, including for Admin.

HSTS is one year, includes subdomains and advertises preload eligibility. Check that
every covered subdomain supports HTTPS before pointing real traffic at this service;
the application does not submit a domain to a browser preload list. Hostname/proxy
checks must be performed at the provider edge as well as in Django.

## Backend build, release and runtime

Root directory: `backend`. Python: 3.13. In a clean deployment environment:

```sh
python -m pip install .
python manage.py check --deploy --fail-level WARNING
python manage.py collectstatic --noinput
```

Release command, **once before switching traffic** (not in every worker):

```sh
python manage.py migrate --noinput
python manage.py migrate --check
```

Start command:

```sh
gunicorn config.wsgi:application --config gunicorn.conf.py
```

Do not use runserver. WhiteNoise serves collected, hashed Admin static assets.
Build the static manifest in the same immutable release as the Python code. Never
reuse a stale static manifest after changing dependencies. Inspect `/admin/login/`
and its CSS responses on staging. Question images are externally hosted HTTPS URLs;
authoritative data is never written to ephemeral media folders. Import uploads are
validated/processed, not stored as persistent files. Keep an owner-controlled copy
of all externally hosted diagrams and validate URLs before freezing the paper.

Health check: HTTPS `/api/v1/health/ready/`, expected 200 JSON. Liveness is
`/api/v1/health/live/`, expected 200 even during DB failure. Readiness executes SELECT 1,
returns 503 without exception details on DB failure, and does not call Google/Razorpay.
Health responses must be uncached. Configure the platform probe to reach Django as
HTTPS through the trusted proxy and send an allowed Host. An HTTP redirect is not a
successful readiness check. Do not exempt all endpoints from HTTPS for a broken probe.

Use a small paid instance as a **candidate**, with sufficient memory for three Python
processes and result snapshots (start evaluation around 2 vCPU / 4 GiB). Measure actual
CPU/RAM and change sizing from evidence. The initial worker connection budget is about
12 connections per instance, plus release/admin/monitoring connections; account for
two instances during a rolling deployment and leave at least 30% DB connection headroom.
Connections have health checks, 60-second reuse and a 5-second production connect timeout.
Confirm managed database clock/timezone, private network access, backups and connection limits.

Gunicorn timeout/graceful timeout is 90s; configure upstream request timeouts accordingly.
The browser start timeout is 60s; ordinary requests are 15s. Timeouts are failure bounds,
not acceptable latency targets. Result calculation holds locks: run it after exams,
measure on staging and inspect status before retrying a timed-out operation.

## Frontend build and delivery

Vercel root directory: `frontend`. Install with `npm ci`. Set only:

```text
VITE_API_BASE_URL=https://<actual-api-host>/api/v1
VITE_GOOGLE_CLIENT_ID=<same-public-Google-Web-client-ID-as-backend>
```

`npm run build` now rejects missing/HTTP/local API URLs, missing Google client IDs,
and unexpected VITE names. Rebuild whenever these public values change. Checkout
obtains its Razorpay public key from the server order response; **there is no
VITE_RAZORPAY_KEY_ID**. All backend secrets belong only in backend runtime configuration.
`build:check-secrets` checks emitted assets against sensitive variable names and
configured secret sentinels. Run it on the actual deployment output too.

`vercel.json` supplies SPA fallback, revalidated HTML, immutable hashed assets,
nosniff/frame/referrer protections and popup-compatible COOP for Google. Source maps
are disabled; exam, math and results stay lazy-loaded. Verify direct/reloaded deep
links, old-chunk availability across releases, headers and API URLs at the actual CDN.
Keep the previous deployment's assets available during rollback and the exam freeze.

## Abuse protection and admin

Application throttles are process-local, approximate guards, not DDoS protection.
Limits per user (or IP for anonymous routes), per process: login 120/min, refresh
300/min, reads 120/min, create order 10/min, verify payment 30/min, start 20/min.
The existing exam bucket remains 600/min for paper/state/heartbeat/saves/submission;
normal 30-second heartbeat plus autosave is far below it. Results inherit that bucket.
Logout is not throttled. Webhooks bypass student throttles and require HMAC.

Configure provider edge limits for auth and costly public catalogue reads, and protect
`/admin/` using network allowlisting or provider access policy. Do not apply a blanket
low IP limit to response saves: many students may share a college/mobile NAT. Rehearse
the expected NAT burst, Retry-After recovery and spoofed forwarded headers. No distributed
limit is claimed. Block direct origin access if relying on edge controls.

Bootstrap only the verified owner identity; use `set_admin_password` with its non-echoing
prompt, a password manager and a unique password (production minimum 12 characters).
No password value in `.env`, commands or screenshots. Student passwords cannot be
assigned via UserAdmin; role/Google identity fields are read-only there. Student APIs
cannot assign privileges or authenticate with Admin session cookies. Schedule
`clearsessions` and `flushexpiredtokens` daily outside the mock window; no worker needed.

## Monitoring

Collect stdout/stderr and set owner-visible alerts for readiness failures, 5xx bursts,
payment failures/old CREATED/PENDING orders, CPU/RAM saturation, database connection
pressure, disk space and backup failures. Verify alert delivery with a controlled staging
failure. Inspect `request_rejected`, `api_unhandled_exception`, `payment_provider_unavailable`,
`payment_reconciled`, `owner_payment_reconciliation`, `attempt_*` and `result_operation`.
Use X-Request-ID for correlation. Logs omit request bodies, query strings, credentials,
PII and exception values; unhandled error logs retain exception type and frame locations.
Provider access/error logs must follow the same policy. Do not enable SQL/body debug logs.
Retain restricted operational logs initially for 14 days, subject to owner privacy approval.

Alert candidates: readiness failure twice at 30s intervals; any repeated payment 5xx;
5xx >1% for 1 minute; saves p99 approaching 10s; persistent CPU >80% or exhausted memory;
DB connections >70% of capacity. Owner must tune thresholds from rehearsal measurements.
Accepted-answer integrity and zero unexpected errors are mandatory regardless of averages.

## Backup and restore

Use managed automated backups/PITR plus a pre-mock and pre-results logical backup.
Initial retention recommendation: 7 daily and 4 weekly recovery points, encrypted and
access restricted, subject to approved privacy/retention policy. Target RPO <=5 minutes
with managed PITR and RTO <=30 minutes; these are proposed goals, **not measured guarantees**.
Check provider plan capabilities and quota before purchasing/approving launch.

Use a private PostgreSQL service file (`PGSERVICEFILE`) and password file (`PGPASSFILE`,
0600 on Linux or owner-only Windows ACL), or provider secure shell environment. Never
put a connection URL/password in process arguments, logs, repository or chat.
Service names below are local labels configured by the owner, not real credentials.

```sh
PGSERVICE=growthsathi_backup pg_dump --format=custom --no-owner --no-acl --file=pre-mock.dump
pg_restore --list pre-mock.dump
sha256sum pre-mock.dump
```

Verify each command's exit status and upload the encrypted artifact/checksum to separate
durable storage. A file or successful dump alone is not restore proof.

Create a **new empty isolated restore database**, separate role/project where possible,
with outbound provider operations disabled. Inspect the resolved restore destination
before running this command. Never restore over an active database or use `--clean` casually.

```sh
PGSERVICE=growthsathi_restore pg_restore --dbname=service=growthsathi_restore --no-owner --no-acl --exit-on-error --single-transaction pre-mock.dump
```

Point a private validation instance at the restored database. Run `migrate --check`,
`check`, health checks, and compare table counts/digests plus order/payment/grant identities,
accepted response versions, run snapshots and published Result pointers. Verify owner login,
a saved attempt and report/review with test identities. Record recovery duration and backup
timestamp. The local `scripts/verify_restore.py` checks all rows of every public table in
two explicitly isolated local Phase 8 databases; it is not a managed-PITR test.

Production restore and PITR remain **UNVERIFIED** until performed on the chosen provider.
Do not erase exam responses by reverting to a pre-exam snapshot during a live incident.
Prefer repairing connectivity/failover; a restore cutover requires owner incident approval,
known recovery point, payment reconciliation, and an explicit data-loss assessment.

## Rollback

Record known-good frontend/backend deployment IDs and commit before release. Disable
auto-deploy during the freeze. Keep deploy access separate from owner exam operations.

1. Diagnose which release failed using health, error rate and request IDs; preserve logs.
2. Frontend: restore/promote the previous immutable Vercel deployment with its matching
   public env values. Check `/auth`, `/dashboard`, a deep exam URL and asset responses.
3. Backend: redeploy the previous compatible artifact via provider rollback. Retain
   current database and secrets; check migrations, readiness, cookie flow and saved attempt.
4. Do **not** reverse migrations automatically or restore the DB just to roll back code.
   Phase 8 adds no schema migration; its code is schema-compatible with Phase 7. Returning
   to Phase 7 would remove security fixes and is not an approved steady-state launch build.
5. New-schema deployments require a compatibility review. Destructive schema/data changes
   need a forward fix or separately approved recovery, not blind `migrate <old-version>`.
6. Inspect any uncertain order/submit/result operation before retrying. A network timeout
   does not prove rollback. Reconcile through existing domain commands/Admin, never raw SQL.

The Phase 8 Google login contract adds CSRF bootstrap. A Phase 7 frontend cannot log
in against the hardened backend without that header. Do not roll back only the frontend
to Phase 7: use a compatible Phase 8 artifact/forward fix, or coordinate both releases
under an incident decision and restore the security fixes before any paid launch.

Test frontend/backend rollback in staging before the freeze. Do not rotate secrets during
an exam unless responding to a confirmed compromise; JWT rotation signs students out.
Webhook-secret rotation has one active secret: coordinate dashboard/runtime changes, retain
old delivery evidence, reconcile missed captures and test retries. Do not accept unsigned events.

## Primary references

Checked for this phase: [Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/),
[Render Django deployment](https://render.com/docs/deploy-django),
[Google Web client setup](https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid),
[Razorpay capture settings](https://razorpay.com/docs/payments/payments/capture-settings/).
Provider account settings and deployed behavior still require direct verification.
