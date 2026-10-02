# GrowthSathi Mock Platform

GrowthSathi JEE Main and MHT-CET PCM mock-test platform.

Phases 0 and 1 are implemented: the production foundation, Google authentication, secure browser sessions, and student onboarding. Exam administration, payments, attempts, results, and the functional student dashboard intentionally remain unimplemented.

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

The backend reads process environment variables. The frontend reads variables prefixed with `VITE_`.

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

## Initial platform owner

The bootstrap command never hard-codes an identity and never creates a usable password. Obtain the
owner's verified Google `sub` (for example, after their first normal Google login, inspect that
account in the trusted database), then run:

```bash
.venv/Scripts/python manage.py bootstrap_admin \
  --email owner@example.com \
  --google-sub verified-google-sub \
  --first-name Platform \
  --last-name Owner
```

The command creates or promotes only an exact email/`sub` match and aborts on conflicts. Phase 1
sets the staff/superuser role but does not add a password login or a separate admin login UI.

## Google Cloud configuration

Create an OAuth 2.0 Client ID of type **Web application** in Google Cloud. Add every exact frontend
origin (scheme, host, and port) to **Authorized JavaScript origins**, including
`http://localhost:5173` for local development and the production HTTPS origin. This credential flow
does not use a redirect URI or client secret. Configure Django's allowed hosts, CORS allowed origins,
and CSRF trusted origins for the corresponding API/frontend deployment. For separate subdomains,
review cookie domains and SameSite values together; any cross-site setup requires HTTPS,
`SameSite=None`, and Secure cookies.

## Local PostgreSQL

```bash
docker compose up -d postgres
```

PostgreSQL is the only stateful service in Phase 0. Deadlines will be enforced by server-side domain services and database state in the exam phase. A worker may be introduced later only if reliability or load testing demonstrates the need.

## Working rules

- Treat `docs/SPEC.md` as authoritative.
- Implement one numbered phase at a time.
- Do not introduce screenshot-only or unspecified product features.
- Keep dates, prices, exam rules, and publication controls backend-configurable.
- Run relevant checks before declaring a phase complete.
