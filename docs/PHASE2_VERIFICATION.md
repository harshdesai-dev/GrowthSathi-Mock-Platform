# Phase 2 verification — 2026-10-02

Started on `develop`, clean, at `d4e4fba79cbda31428c869ebe329bd1643e20d07`.
No earlier committed migration or frontend source was changed.

## Final results

| Check | Result |
| --- | --- |
| Backend Ruff / format | Passed; 52 Python files formatted |
| SQLite suite | 119 passed, 1 PostgreSQL-only concurrency test skipped (20.98s) |
| PostgreSQL suite | 120 passed, no skips (36.33s) |
| Frontend format/lint/types | Passed |
| Frontend tests | 9 passed, 4 test files |
| Frontend production build | Passed |
| Django system/deployment checks | No issues |
| Migration drift | No changes detected |
| OpenAPI validation | Passed |
| Fresh PostgreSQL migration | Passed, all apps including exams.0001_initial |
| Phase 1.5 PostgreSQL upgrade | Passed, exams.0001_initial applied |
| Seed command, twice | Created both baselines; second run unchanged |
| Git whitespace check | Passed |

The backend suite preserves all 42 existing tests and adds 78 Phase 2 cases. It includes complete
75-question JEE / 150-question CET papers, query-count ceilings, manual MCQ/numerical Admin POSTs,
CSRF/owner checks, malformed files/rows, token tampering/expiry/replay, database constraints,
immutability, transitions, audited corrections and atomic rollback after questions are inserted.
The PostgreSQL concurrency test confirms two concurrent commits of one preview result in exactly
one imported question and four options; the second commit is rejected as a duplicate.

## Exact backend process invocation

The available Python executable was:

```text
C:\Program Files\PostgreSQL\18\pgAdmin 4\python\python.exe
```

Commands ran from `backend`. This embedded runtime ignores `PYTHONPATH`, so project and installed
virtualenv dependencies were inserted explicitly. The exact test invocation was run once without
`DATABASE_URL` (SQLite) and once with the PostgreSQL URL below:

```powershell
& 'C:\Program Files\PostgreSQL\18\pgAdmin 4\python\python.exe' -c "import sys,runpy; sys.path.insert(0,r'.'); sys.path.insert(1,r'.venv\Lib\site-packages'); sys.argv=sys.argv[1:]; runpy.run_module('pytest',run_name='__main__')" pytest -q -p no:cacheprovider
```

Ruff used the same executable and this bootstrap with arguments `check .`, `format .` during
editing, and `format --check .` for final verification:

```powershell
& 'C:\Program Files\PostgreSQL\18\pgAdmin 4\python\python.exe' -c "import sys,runpy; sys.path.insert(0,r'.venv\Lib\site-packages'); runpy.run_module('ruff',run_name='__main__')" check .
```

Every Django command used this exact invocation prefix followed by the arguments listed below:

```powershell
& 'C:\Program Files\PostgreSQL\18\pgAdmin 4\python\python.exe' -c "import sys,runpy; sys.path.insert(0,r'.'); sys.path.insert(1,r'.venv\Lib\site-packages'); sys.argv=sys.argv[1:]; runpy.run_path('manage.py',run_name='__main__')" manage.py
```

```text
makemigrations exams --settings=config.settings.test
migrate --noinput
seed_exam_schemes
seed_exam_schemes
showmigrations exams
check
makemigrations --check --dry-run
spectacular --validate --file phase2-openapi-check.yml
check --deploy --settings=config.settings.production
```

The temporary OpenAPI file was removed after successful validation. Production checks used
temporary non-production values for `DJANGO_SECRET_KEY`, `JWT_SECRET` and `GOOGLE_CLIENT_ID`.
No real OAuth credential was used or committed. The `-p no:cacheprovider` flag avoids the managed
workspace's previously observed pytest-cache permission issue; it does not disable any tests.

Dependencies were installed into `backend/.venv/Lib/site-packages` using the same runtime's pip:

```text
install --target .venv\Lib\site-packages "openpyxl>=3.1.5,<4" "defusedxml>=0.7.1,<1"
```

## PostgreSQL

The existing project-local PostgreSQL 18.6 cluster was started on `127.0.0.1:55432`:

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe' -D 'backend\.postgres-data' -l 'backend\.postgres-data\server.log' -o '-p 55432 -h 127.0.0.1' -w start
$env:PGPASSWORD = 'growthsathi'
& 'C:\Program Files\PostgreSQL\18\bin\createdb.exe' -h 127.0.0.1 -p 55432 -U growthsathi growthsathi_phase2_empty
& 'C:\Program Files\PostgreSQL\18\bin\createdb.exe' -h 127.0.0.1 -p 55432 -U growthsathi growthsathi_phase2_pytest
```

`DATABASE_URL` values, in order:

```text
postgresql://growthsathi:growthsathi@127.0.0.1:55432/growthsathi_phase2_empty
postgresql://growthsathi:growthsathi@127.0.0.1:55432/growthsathi_phase15_verify
postgresql://growthsathi:growthsathi@127.0.0.1:55432/growthsathi_phase2_pytest
```

The first received all migrations and two seed runs. The second already contained the Phase 1.5
schema (accounts/admin/auth/contenttypes/sessions/token_blacklist) and received only the new exams
migration. The third backed pytest's disposable test database. SQL inspection confirmed nine exams
tables and baseline totals of 75/300/180 for JEE and 150/200/180 for CET (questions/marks/minutes).
These are local development credentials, not deployment secrets. The system service on 5432 was
not modified. The isolated server was stopped after verification:

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe' -D 'backend\.postgres-data' -w stop
```

## Frontend and Git

From `frontend`:

```powershell
npm.cmd run format:check
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run test
npm.cmd run build
```

From the repository root:

```powershell
git diff --check
git diff --cached --check
git commit -m "feat: implement exam administration and question import"
```

## Manual requirements

Install dependencies, migrate and run `seed_exam_schemes` in the intended development/deployment
database. Set up the owner account as documented in README. Review latest official exam rules
and record the per-mock attestation before scheduling. The seeds are SPEC baselines, not official
2027 validation. Actual question content and answer keys must be authored/reviewed by the owner.
Real Google login still needs the earlier manual smoke test when actual credentials are available.
