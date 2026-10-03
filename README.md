# GrowthSathi Mock Platform

GrowthSathi JEE Main and MHT-CET PCM mock-test platform.

Phases 0, 1, 1.5, 2, 3, 4, 4.5 and 5 are implemented: the production foundation, Google authentication,
secure browser sessions, student onboarding, owner access to Django Admin, versioned exam
administration, question authoring, atomic CSV/XLSX imports, paper validation, explicit
offers, verified Razorpay test-mode payments, mock access, and the reliable live exam engine.
Deterministic scoring, private published report cards, ranking, Mock Percentile, answer review
and audited correction/republication are implemented. Phase 6 adds the authenticated student dashboard,
using server-derived mock access/start state and published-result history. Live payments remain disabled.

See [result operations](docs/RESULTS.md), [result architecture](docs/adr/0011-published-results.md)
and [Phase 5 verification](docs/PHASE5_VERIFICATION.md).

See [live exam operations](docs/LIVE_EXAMS.md),
[exam architecture](docs/adr/0009-reliable-live-exam-engine.md), and
[Phase 4 verification](docs/PHASE4_VERIFICATION.md) and
[Phase 4.5 start-path hardening](docs/PHASE45_VERIFICATION.md).

See [Phase 3 payments operations](docs/PAYMENTS.md),
[payment architecture](docs/adr/0008-offers-payments-and-access.md) and
[Phase 3 verification](docs/PHASE3_VERIFICATION.md).

See [Phase 2 operations](docs/EXAM_ADMINISTRATION.md) for the complete authoring/import workflow,
template column definitions, baseline scheme policy and verification commands.

## Repository layout

- `frontend/` - React, TypeScript, Vite, Tailwind CSS, shared UI foundation and design tokens.
- `backend/` - Django and Django REST Framework project with common API infrastructure.
- `docs/SPEC.md` - authoritative product and implementation specification.
- `docs/adr/` - approved architecture decisions.
- `docs/design-references/` - visual references; they do not define product functionality.
- `compose.yaml` - local PostgreSQL service. Phase 0 deliberately has no Redis or worker service.

## Prerequisites

- Node.js 24 or a supported current LTS release
- Python 3.13
- PostgreSQL 18, locally installed or started with Docker Compose

## Environment setup

Copy `.env.example` to `.env` and replace development defaults as needed. Never commit `.env` or actual credentials.

The backend reads process environment variables. Vite reads the repository-root `.env` and exposes
only variables prefixed with `VITE_`. Do not put an Admin password in `.env` or commit credentials.

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Checks:

```bash
npm run format:check
npm run lint
npm run typecheck
npm test
npm run build
```

## Backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python manage.py migrate
.venv/Scripts/python manage.py runserver
```

Checks:

```bash
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m ruff format --check .
.venv/Scripts/python -m pytest
.venv/Scripts/python manage.py check --deploy --settings=config.settings.production
```

Phase 1 authentication uses Google Identity Services. Set the same OAuth Web client ID in
`GOOGLE_CLIENT_ID` and `VITE_GOOGLE_CLIENT_ID`. Access tokens live only in frontend memory; the
rotating refresh token is an HttpOnly cookie. Development may set cookie `Secure` flags to false,
but production settings force the refresh and CSRF cookies to be secure.

The API exposes:

- `GET /api/v1/health/live/` - confirms that the Django process is running.
- `GET /api/v1/health/ready/` - confirms that Django can query PostgreSQL.
- `GET /api/v1/auth/csrf/` - bootstraps a CSRF token for refresh/logout.
- `POST /api/v1/auth/google/` - verifies a Google ID token and starts a local session.
- `POST /api/v1/auth/refresh/` - rotates the HttpOnly refresh cookie and returns an access token.
- `POST /api/v1/auth/logout/` - revokes and clears the refresh session.
- `GET /api/v1/auth/me/` - returns minimal authenticated-user routing state.
- `GET/PATCH /api/v1/profile/` - reads or completes the current student's profile.
- `GET /api/schema/` - OpenAPI schema.

## Initial platform owner and Django Admin

Obtain the owner's verified Google `sub` after their first normal Google login, then explicitly
bootstrap that exact email/`sub` pair:

```bash
.venv/Scripts/python manage.py bootstrap_admin \
  --email owner@example.com \
  --google-sub verified-google-sub \
  --first-name Platform \
  --last-name Owner
```

The bootstrap command creates or promotes only an exact match, aborts on conflicts, and initially
leaves the password unusable. Assign the internal owner password through a non-echoing prompt:

```bash
.venv/Scripts/python manage.py set_admin_password \
  --email owner@example.com \
  --google-sub verified-google-sub
```

For controlled automation, put the password in a temporary process environment variable and name
that variable with `--password-env`; never put the password directly on the command line:

```powershell
$env:GROWTHSATHI_ADMIN_PASSWORD = "value-from-an-approved-password-manager"
.venv/Scripts/python manage.py set_admin_password `
  --email owner@example.com `
  --google-sub verified-google-sub `
  --password-env GROWTHSATHI_ADMIN_PASSWORD
Remove-Item Env:GROWTHSATHI_ADMIN_PASSWORD
```

The command accepts only an active user who is already both staff and superuser, runs Django's
password validators, and stores only Django's password hash. The owner then signs in at `/admin/`
with their email and this internal password. This is an operational mechanism only: students still
have unusable passwords, and no password login/signup/reset API exists for the product.

## Google Cloud configuration

The implementation uses the Google Identity Services JavaScript callback and sends its ID token to
Django for independent verification. Follow Google's
[Web client setup](https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid)
and [server verification](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token)
guides:

1. Create/select a Google Cloud project and configure its OAuth branding/consent screen.
2. Create an OAuth 2.0 Client ID with application type **Web application**.
3. Add `http://localhost` and `http://localhost:5173` to **Authorized JavaScript origins** for local
   development. Add the exact production HTTPS frontend origin before deployment.
4. This callback-based ID-token flow requires no authorized redirect URI and no
   `GOOGLE_CLIENT_SECRET`.
5. Set the same client ID as backend `GOOGLE_CLIENT_ID` and frontend-build
   `VITE_GOOGLE_CLIENT_ID`.
6. Keep local `CORS_ALLOWED_ORIGINS` and `CSRF_TRUSTED_ORIGINS` set to
   `http://localhost:5173`; the local API remains `http://localhost:8000`.

### Manual Google login smoke test

1. Put the Web client ID in both environment variables without committing `.env`.
2. Start Django at `http://localhost:8000` and Vite at `http://localhost:5173`.
3. Open `/auth`; confirm the official Google button renders without an origin error.
4. Sign in with an allowed Google account. If the consent screen is in Testing, add the account as
   a test user first.
5. In browser developer tools, confirm `POST /api/v1/auth/google/` succeeds, the response contains a
   short-lived access token, and `growthsathi_refresh` is an HttpOnly cookie rather than browser
   storage.
6. Confirm a new account reaches `/onboarding`, completes the profile, and reaches `/dashboard`.
7. Sign out, sign in again, and confirm the returning account bypasses onboarding.
8. Confirm refresh survives a page reload and logout prevents the old refresh session from being
   reused.

For separate production subdomains, review cookie domains and SameSite values together. Any
cross-site deployment requires HTTPS, `SameSite=None`, and Secure cookies.

## Local PostgreSQL

The Compose configuration provisions the documented `growthsathi` role/database on port 5432:

```bash
docker compose up -d postgres
```

If another PostgreSQL service already owns port 5432, Compose cannot provision those credentials
there. Either stop/reconfigure that service deliberately, change the Compose host port, or create an
isolated project cluster. On Windows with PostgreSQL 18 installed, the following keeps the existing
service untouched and uses port 55432:

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\initdb.exe' `
  -D 'backend\.postgres-data' `
  -U growthsathi `
  -W `
  --encoding=UTF8 `
  --auth-host=scram-sha-256 `
  --auth-local=scram-sha-256

& 'C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe' `
  -D 'backend\.postgres-data' `
  -l 'backend\.postgres-data\server.log' `
  -o '-p 55432 -h 127.0.0.1' `
  -w start

$env:PGPASSWORD = 'growthsathi'
& 'C:\Program Files\PostgreSQL\18\bin\createdb.exe' `
  -h 127.0.0.1 -p 55432 -U growthsathi growthsathi
$env:DATABASE_URL = 'postgresql://growthsathi:growthsathi@127.0.0.1:55432/growthsathi'

cd backend
.venv/Scripts/python manage.py migrate
.venv/Scripts/python manage.py runserver
```

Stop that isolated cluster with:

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe' `
  -D 'backend\.postgres-data' -w stop
```

The checked-in username/password are local-development values only. Use independently managed
credentials in every deployed environment. `DATABASE_URL` remains the single Django database
configuration interface.

PostgreSQL is the only stateful service in Phase 0. Deadlines will be enforced by server-side domain services and database state in the exam phase. A worker may be introduced later only if reliability or load testing demonstrates the need.

## Working rules

- Treat `docs/SPEC.md` as authoritative.
- Implement one numbered phase at a time.
- Do not introduce screenshot-only or unspecified product features.
- Keep dates, prices, exam rules, and publication controls backend-configurable.
- Run relevant checks before declaring a phase complete.
