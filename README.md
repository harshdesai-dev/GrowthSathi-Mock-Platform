# GrowthSathi Mock Platform

Production foundation for the GrowthSathi JEE Main and MHT-CET PCM mock-test platform.

Only Phase 0 is implemented. Authentication, exam administration, payments, attempts, results, and student dashboard functionality intentionally remain unimplemented.

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

The API exposes:

- `GET /api/v1/health/live/` - confirms that the Django process is running.
- `GET /api/v1/health/ready/` - confirms that Django can query PostgreSQL.
- `GET /api/schema/` - OpenAPI schema.

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
