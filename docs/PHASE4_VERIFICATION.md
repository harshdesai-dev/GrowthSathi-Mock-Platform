# Phase 4 verification — Reliable Live Exam Engine

Date: 2026-10-03. Baseline: `develop`, clean at
`d94982d9b68a2f391fa71b1491d82b2bac92cfe7` (`feat: implement payments and mock access`).
SPEC.md was read completely, along with all eight existing ADRs, EXAM_ADMINISTRATION.md,
PAYMENTS.md, PHASE2_VERIFICATION.md and PHASE3_VERIFICATION.md. All six design-reference
assets were inspected. Existing code and invariants were inspected before implementation.

## 1. Summary

Phase 4 only: server-timed attempts, secure phase-specific questions, durable ordered
responses, offline/session recovery, submission and reconciliation, responsive exam UI.
No scoring, correctness calculation, Result, rank, percentile, report card, leaderboard,
answer review, subject analytics, AI, NEET, Redis or Celery. Phase 5 is not started.

## 2. Architecture decisions

[ADR 0009](adr/0009-reliable-live-exam-engine.md) extends the modular monolith and existing
commerce/auth/scheme boundaries. PostgreSQL/Django remain authoritative. Per-attempt row
locks serialize mutations and submission; full paper validation still runs at new start.
Scheduled mocks activate lazily on eligible start. IndexedDB is a retry journal, not an
authority. No correctness depends on a worker or client heartbeat.

## 3. Models / migrations

`attempts.0001_initial` adds Attempt and StudentResponse only. UUID identities, protected
foreign keys, unique student/mock and attempt/question pairs, valid status/terminal-time
constraints, safe positive versions, exclusive option/numeric response shape and an
attempt status/mock index. A response stores canonical decimal text, not float/correctness.
Application writes are restricted to domain services; Admin records are read-only.

Fresh PostgreSQL migration passed. Upgrade of the existing Phase 3-schema test database
`growthsathi_phase2_empty` applied only `attempts.0001_initial`; both pre-existing schemes
remained (2 before, 2 after). Despite its historical name, its pre-upgrade ledger contained
both `exams.0001_initial` and `commerce.0001_initial`. No committed migration was edited.

## 4. Attempt lifecycle

Active paid entitlement, complete onboarding, valid attested paper and an open global
window are required. Repeated/concurrent starts return one attempt; terminal attempts
never reopen. IN_PROGRESS transitions to SUBMITTED, AUTO_SUBMITTED or (on cancelled mock)
INVALID. Empty auto-submissions are retained without any Phase 5 ranking calculation.

## 5. Timing implementation

UTC server time and fixed mock timestamps govern all operations. Time is read after row
lock acquisition and rechecked before response persistence. Late start, refresh, retries
and process restart cannot change deadlines. Countdown uses server time plus monotonic
elapsed time, never browser wall-clock authority. Local zero only disables editing and
asks the server for the next authoritative state.

## 6. CET phase handling

Global minute 0–90 is Physics/Chemistry; minute 90–180 is Mathematics. Half-open intervals
reject PC at exactly minute 90. Late students enter the currently active global phase.
No early Mathematics unlock, PC return or final submission during PC. JEE exposes its
single phase/all subjects throughout its fixed window.

## 7. Secure exam payload

Separate explicit serializers and restricted question/option query fields. Nested payload
tests deny `is_correct`, numeric keys, explanations, tolerances, marks/audits. Future-phase
questions are not sent. Attempt ownership is enforced and exam API responses are no-store.
Markdown excludes raw HTML/links; images require HTTPS and omit referrers; KaTeX trust is
disabled with expansion/size limits. No live answer-key fields are hidden merely with CSS.

## 8. IndexedDB / autosave design

Atomic IndexedDB writes precede serial network sync; one coalesced record per
user/attempt/question retains the newest local intent and last known server answer.
Clear, visit, numerical and review mutations persist too. Local/server save status is
explicit. Storage errors are visible. Reopen merges server and local entries before the
paper is published; a browser test found and fixed an initial blank-visit hydration race.
Closed-phase drafts are retained as unaccepted, never sent into the next phase.

## 9. Mutation ordering

Positive JavaScript-safe integer versions per question. Higher versions replace; identical
equal-version retries acknowledge; older/conflicting versions return 409. IndexedDB
transactions serialize version allocation across tabs. A delayed ack cannot erase a newer
queued edit. Cross-device conflict does not trigger automatic version inflation; a new
explicit student edit is required. Lost acknowledgements and reconnect storms are tested.

## 10. JWT / network recovery

Existing AuthProvider refresh deduplication, CSRF and HttpOnly cookie are reused; an exam
401 refreshes and retries once. Token-free answers survive refresh failure. Network retries
use capped exponential backoff with jitter, plus reconnect/visibility/pageshow/manual retry.
Requests have bounded timeouts (start 60s, ordinary requests 15s). Heartbeat is about 30s,
with backend heartbeat writes limited similarly. 30-second and five-minute outages are
tested with accelerated timers; real carrier/OS outage tests remain manual.

## 11. Submission / auto-submit

The client waits for local writes and attempts to flush before submitting. If sync cannot
finish, confirmation offers retry/cancel or explicit server-saved-only submission. The
server accepts no answer body at submit. Submit/save share the row lock. Duplicate submit
returns the original terminal state. Deadline reconciliation commits even when a late save
returns 409; its submission timestamp is the global end, not the later cleanup time.

`reconcile_expired_attempts --batch-size 200` is idempotent and batch-scanned. It also
invalidates unfinished cancelled mocks. Owner Admin reconciles before showing attempts.
Operational/refund boundaries and incident handling are in [LIVE_EXAMS.md](LIVE_EXAMS.md).

## 12. APIs

Seven authenticated routes under `/api/v1`: mock exam-info/start; attempt state/paper;
heartbeat; question-response PUT; submit. Strict inputs and the existing error envelope
apply. Complete route/body semantics are in [the API contract](LIVE_EXAMS.md#api-contract).

## 13. Frontend exam UI / Admin

Instructions and fixed IST schedule; actual GrowthSathi logo; charcoal/lime design tokens;
MCQ and decimal entry; safe Markdown/LaTeX and lazy diagrams; subject navigation, palette,
clear, review, previous/save-next, synchronized sticky mobile timer/actions, mobile bottom
drawer and desktop sidebar. Accessible labels, visible focus, native modal focus handling,
44px targets and text status accompany color. Terminal view has no scores/answer review.
Exam/math code is lazy-loaded (about 417kB minified exam chunk, 338kB main chunk).

Read-only Attempt/StudentResponse Admin, lifecycle/rejection ID logging, reconciliation
command and operations guide are included. No response values or credentials are logged
by these services. Actual brand image is reused unchanged, not generated from screenshots.

## 14. Tests

39 new backend tests cover access, schedules, JEE/CET, invalid input, canonical decimals,
stale/equal/new versions, clear/review, no answer leakage, ownership, immutable records,
heartbeat write throttling, cancellation, deadline/command/Admin and eight PG race cases.
Existing 165 tests remain passing.

14 new frontend tests (35 total) cover IndexedDB reopen/isolation, multi-tab transactions,
late acks, conflicts, canonical ack, closed queues, browser-clock tampering, reconnect,
submit fallback, storage failure, hydration ordering, 30s/5m simulated outages and safe math.
Seven Chromium scenarios cover 360/390/430/768/1440px, radio/numerical/clear/review/palette,
refresh/page-close/new-page recovery, intercepted network failures, 401 refresh, submit,
CET lock/transition and auto-submitted UI. API responses are controlled browser fixtures;
this is not a real Google-provider session or a full browser-to-Django integration test.
Backend HTTP load uses real Django middleware/JWT/API/PostgreSQL separately.

Screenshots were visually inspected at mobile, tablet and desktop sizes. They are ignored
under `frontend/test-results/`; running browser tests regenerates them. A two-invocation
restart check persisted an active attempt/version-7 answer, exited, then resumed and
submitted in a fresh Python process with unchanged original start/end.

Development failures fixed before final verification: delayed controlled-radio feedback;
blank visit overwriting a recovered queue before hydration; string timer comparison in the
browser test; PostgreSQL statistics snapshot caching in the lock-wait observer; lint lines.
The production build's initial large main chunk warning was removed by lazy exam loading.

## 15. PostgreSQL concurrency results

All eight Phase 4 cases passed on PostgreSQL 18.6 with independent thread connections:
8 simultaneous starts -> one attempt; save/save -> newest version; save/submit -> one
serialized winner; 8 duplicate submits -> same timestamp; deadline/save/heartbeat/command
race -> auto-submit/no late row; CET boundary -> PC rejected; and two actual row-lock wait
tests crossing exam end and CET minute 90. The latter observe a real PostgreSQL lock wait,
advance server time, then release the lock. They prove checks happen after lock acquisition.
Together with six previous PG-only tests, the full PG suite runs 204 tests without skips.

## 16. Load-test methodology / results

`backend/scripts/phase4_load.py`: 500 distinct paid synthetic CET students, full 150-question
paper and real JWT-authenticated loopback HTTP. One Waitress 3.0.2 process, 32 WSGI threads,
100 concurrent HTTP clients, PostgreSQL 18.6 on isolated port 55432. Windows laptop: AMD
Ryzen 5 7520U, 4 cores/8 logical processors, 15.28 GiB usable RAM. Browser verification ran
on the same machine during part of the benchmark. Seeds are explicitly test-only and do
not represent verified real payments or official-rule review.

The script requires a **new empty** migrated database ending in `phase4_load`; it refuses
other databases/existing datasets and deletes nothing. Server time is controlled only
inside this test process to cross phases/deadline without waiting three hours. No timing
override endpoint is included in the product. Each burst queues all its participants and
allows at most 100 HTTP requests in flight; this is not 500 simultaneous open requests.

| Burst | Requests | p50 ms | p95 ms | p99 ms | Requests/s | Expected status |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Start | 500 | 16597.74 | 22920.32 | 24076.33 | 5.60 | 200 |
| PC paper | 500 | 7479.68 | 9165.98 | 9822.20 | 12.96 | 200 |
| Heartbeat | 500 | 2519.99 | 2930.01 | 3130.27 | 38.21 | 200 |
| Autosave v1 | 500 | 1816.96 | 2255.43 | 2524.75 | 52.67 | 200 |
| Autosave v2 | 500 | 1505.29 | 1730.11 | 1845.55 | 63.87 | 200 |
| Autosave v3 | 500 | 1639.07 | 1943.90 | 2207.33 | 58.08 | 200 |
| Lost-ack retry | 500 | 1545.19 | 1846.55 | 1952.38 | 60.97 | 200 |
| Stale reconnect | 500 | 1575.44 | 1821.35 | 2024.08 | 60.67 | 409 |
| Closed PC | 500 | 1392.91 | 1698.78 | 1923.06 | 68.42 | 409 |
| Math paper | 500 | 3381.90 | 4092.26 | 4430.41 | 28.35 | 200 |
| Math save | 500 | 1775.36 | 2194.30 | 2360.95 | 54.60 | 200 |
| Manual submit | 250 | 2083.20 | 2418.39 | 2568.43 | 45.50 | 200 |
| Duplicate submit | 250 | 1852.18 | 2197.27 | 2363.42 | 50.78 | 200 |
| Late deadline save | 250 | 1578.44 | 2094.01 | 2367.46 | 59.67 | 409 |
| Deadline recovery | 250 | 1383.36 | 1700.72 | 1918.32 | 67.60 | 200 |

**6,500 requests; zero unexpected errors** (1,250 intentional 409 rejections). Integrity:
500 unique attempts, 250 SUBMITTED, 250 AUTO_SUBMITTED, exactly 1,000 responses, all PC
versions 3 and Math versions 1. No stale/late overwrites. Reconciliation repeated -> 0 changes.
Worst start was 25.42s; the start burst took 89.36s. Full paper validation is expensive.

This passes correctness/burst verification, **not production capacity certification**.
There is no asserted production latency SLO in SPEC. Start latency is a material launch
risk: profile and size the actual multi-process deployment. The start client timeout is
60s; saves remain 15s. No validation was skipped, no cache/worker added. TLS, mobile WAN,
external images, mixed long-running traffic, provider auth, multi-host clocks, worker/DB
failover and a three-hour soak were not measured by this loopback test.

## 17. Exact verification commands

All commands were scoped to this repository. The normal Python launcher was unavailable;
the pgAdmin embedded Python used the existing ignored local site-packages. Shell execution
required escalation because the managed sandbox helper failed before process creation.
No system PostgreSQL service or production database was changed.

From repository root (existing isolated cluster):

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe' -D 'backend\.postgres-data' -l 'backend\.postgres-data\server.log' -o '-p 55432 -h 127.0.0.1' -w start
```

From `backend`, the same bootstrap was used with the argument lists below:

```powershell
$env:DJANGO_SETTINGS_MODULE='config.settings.test'
$env:PGPASSWORD='growthsathi'
# Each createdb command was run once on a previously absent, dedicated database.
& 'C:\Program Files\PostgreSQL\18\bin\createdb.exe' -h 127.0.0.1 -p 55432 -U growthsathi growthsathi_phase4_pytest
& 'C:\Program Files\PostgreSQL\18\bin\createdb.exe' -h 127.0.0.1 -p 55432 -U growthsathi growthsathi_phase4_empty
& 'C:\Program Files\PostgreSQL\18\bin\createdb.exe' -h 127.0.0.1 -p 55432 -U growthsathi growthsathi_phase4_load
& 'C:\Program Files\PostgreSQL\18\bin\createdb.exe' -h 127.0.0.1 -p 55432 -U growthsathi growthsathi_phase4_restart

$env:DATABASE_URL='postgresql://growthsathi:growthsathi@127.0.0.1:55432/growthsathi_phase4_pytest'
& 'C:\Program Files\PostgreSQL\18\pgAdmin 4\python\python.exe' -c "import sys,runpy; sys.path.insert(0,r'.'); sys.path.insert(1,r'.venv\Lib\site-packages'); sys.argv=['pytest','-q','-p','no:cacheprovider','--create-db']; runpy.run_module('pytest',run_name='__main__')"

Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
& 'C:\Program Files\PostgreSQL\18\pgAdmin 4\python\python.exe' -c "import sys,runpy; sys.path.insert(0,r'.'); sys.path.insert(1,r'.venv\Lib\site-packages'); sys.argv=['pytest','-q','-p','no:cacheprovider']; runpy.run_module('pytest',run_name='__main__')"
& 'C:\Program Files\PostgreSQL\18\pgAdmin 4\python\python.exe' -c "import sys,runpy; sys.path.insert(0,r'.venv\Lib\site-packages'); sys.argv=['ruff','check','.']; runpy.run_module('ruff',run_name='__main__')"
& 'C:\Program Files\PostgreSQL\18\pgAdmin 4\python\python.exe' -c "import sys,runpy; sys.path.insert(0,r'.venv\Lib\site-packages'); sys.argv=['ruff','format','--check','.']; runpy.run_module('ruff',run_name='__main__')"

$env:DATABASE_URL='postgresql://growthsathi:growthsathi@127.0.0.1:55432/growthsathi_phase4_empty'
$env:DJANGO_SECRET_KEY='phase4-check-only-not-production-long-secret-0123456789abcdef'
$env:JWT_SECRET='phase4-check-only-jwt-signing-key-0123456789abcdef'
$env:GOOGLE_CLIENT_ID='phase4-verification.apps.googleusercontent.com'
foreach ($verificationCommand in @('migrate --noinput','check','makemigrations --check --dry-run','spectacular --validate --fail-on-warn --file .postgres-data/phase4-openapi.yml','check --deploy --settings=config.settings.production')) {
  & 'C:\Program Files\PostgreSQL\18\pgAdmin 4\python\python.exe' -c "import sys,runpy,shlex; sys.path.insert(0,r'.'); sys.path.insert(1,r'.venv\Lib\site-packages'); sys.argv=['manage.py']+shlex.split(sys.argv[1]); runpy.run_path('manage.py',run_name='__main__')" "$verificationCommand"
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

Upgrade: set DATABASE_URL to `.../growthsathi_phase2_empty` and run the same manage.py
bootstrap with `['manage.py','migrate','--noinput']`. Before and after, ran:

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\psql.exe' -h 127.0.0.1 -p 55432 -U growthsathi -d growthsathi_phase2_empty -Atc "SELECT app || ':' || name FROM django_migrations WHERE app IN ('exams','commerce','attempts'); SELECT count(*) FROM exams_examscheme;"
```

Load: migrate the new `.../growthsathi_phase4_load` using the same bootstrap, then:

```powershell
$env:DATABASE_URL='postgresql://growthsathi:growthsathi@127.0.0.1:55432/growthsathi_phase4_load'
& 'C:\Program Files\PostgreSQL\18\pgAdmin 4\python\python.exe' -c "import sys,runpy; sys.path.insert(0,r'.'); sys.path.insert(1,r'.venv\Lib\site-packages'); sys.argv=['phase4_load.py','--students','500','--concurrency','100','--threads','32']; runpy.run_path('scripts/phase4_load.py',run_name='__main__')"
```

Restart: migrate new `.../growthsathi_phase4_restart`, then run two separate processes:

```powershell
$env:DATABASE_URL='postgresql://growthsathi:growthsathi@127.0.0.1:55432/growthsathi_phase4_restart'
& 'C:\Program Files\PostgreSQL\18\pgAdmin 4\python\python.exe' -c "import sys,runpy; sys.path.insert(0,r'.'); sys.path.insert(1,r'.venv\Lib\site-packages'); sys.argv=['phase4_restart.py','prepare']; runpy.run_path('scripts/phase4_restart.py',run_name='__main__')"
& 'C:\Program Files\PostgreSQL\18\pgAdmin 4\python\python.exe' -c "import sys,runpy; sys.path.insert(0,r'.'); sys.path.insert(1,r'.venv\Lib\site-packages'); sys.argv=['phase4_restart.py','recover']; runpy.run_path('scripts/phase4_restart.py',run_name='__main__')"
```

Targeted backend passes used `tests/test_attempts.py` before `-q`. Development formatting
used the same Ruff bootstrap with `check --fix .` and `format .`. Command reconciliation
and batch-size idempotency are exercised with Django `call_command` in pytest.

From `frontend`:

```powershell
npm.cmd install idb react-markdown remark-math rehype-katex katex
npm.cmd install --save-dev fake-indexeddb @playwright/test
npx.cmd playwright install chromium
$env:RAZORPAY_KEY_SECRET='phase3-secret-sentinel-not-a-real-credential'
$env:RAZORPAY_WEBHOOK_SECRET='phase3-webhook-sentinel-not-a-real-credential'
foreach ($scriptName in @('format','format:check','lint','typecheck','test','build','build:check-secrets','test:browser')) {
  npm.cmd run $scriptName
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
npm.cmd audit --audit-level=high
```

Waitress 3.0.2 was installed into the ignored local `.venv/Lib/site-packages` through pip
using the same embedded-Python bootstrap; it is recorded as a backend dev dependency.
On a standard environment use `python -m pip install -e '.[dev]'` instead.

From repository root after successful verification:

```powershell
git diff --check
git diff --cached --check
git commit -m "feat: implement reliable live exam engine"
git status --short
git log -1 --format=%H
& 'C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe' -D 'backend\.postgres-data' -w stop
```

## 18. Overall results / changed files

| Check | Result |
| --- | --- |
| PostgreSQL complete suite | 204 passed; no skips |
| SQLite complete suite | 190 passed; 14 PostgreSQL-only skips |
| Frontend unit/integration | 35 passed |
| Chromium browser scenarios | 7 passed |
| 500-student HTTP burst | 6,500 requests; 0 unexpected errors; integrity passed |
| Separate-process restart | Original attempt, deadline and response recovered |
| Ruff / format | Passed; 75 Python files formatted |
| Django / deployment / OpenAPI fail-on-warn | Passed |
| Migration drift / fresh / Phase 3 upgrade | Passed |
| Frontend format / lint / types / build | Passed |
| Bundle payment-secret scan | Passed, both secret sentinels |
| npm audit | 0 vulnerabilities |
| Git whitespace | Passed |

Changed files, grouped by scope:

- New `backend/apps/attempts/`: package, models, services, student payload, API, Admin,
  migration and reconciliation command/package initializers.
- New `backend/tests/attempt_helpers.py`, `test_attempts.py`, and
  `backend/scripts/phase4_load.py`, `phase4_restart.py`.
- `backend/config/settings/base.py`, `backend/config/urls.py`, `backend/pyproject.toml`.
- New `frontend/src/exam/`: API types/client, engine, storage, safe Markdown/URLs and tests.
- New `frontend/src/pages/ExamPages.tsx`, `src/styles/exam.css`, `e2e/exam.spec.ts`,
  `playwright.config.ts`.
- `frontend/src/app/AppRouter.tsx`, `src/pages/CommercePages.tsx`, `src/api/client.ts`,
  `package.json`, `package-lock.json`, `vite.config.ts`, `.prettierignore`.
- `.github/workflows/ci.yml`, `.gitignore`, `README.md`, `docs/adr/README.md`, new ADR 0009,
  `docs/LIVE_EXAMS.md` and this report. Browser smoke tests are now included in CI.

No earlier migration, SPEC or approved logo was changed. No gateway call charged money.
Generated local screenshots, build output, database files and secrets are not committed.

## 19. Commit

Exactly one commit: `feat: implement reliable live exam engine`. Its hash is in the
delivery message and available through `git log -1 --format=%H`; a containing commit
cannot embed its own hash. No push and no Phase 5 work.

## 20. Remaining risks / manual tests

Start validation latency requires profiling and actual multi-process deployment testing
before paid launch; this local run does not certify 500-student production capacity.
Real Android/iOS, private/quota/eviction, complete browser-process crash, device sleep,
carrier outages, production worker/network failure and long soak remain manual checks.
Browser recovery automated here closes/reopens a page in the same browser context; it
does not simulate every OS crash/storage-loss mode. The restart script uses fresh Python
processes, not a production load balancer/rolling restart.

Real Google refresh/re-auth on deployed cookie domains and Razorpay provider smoke still
need credentials. Official exam-rule review/attestation before each mock, legal copy and
launch approval remain required. The process-local throttle is not distributed abuse
protection. Browser storage is neither guaranteed permanent nor encrypted from a device
owner. Server clocks must be synchronized. Full checklist: [LIVE_EXAMS.md](LIVE_EXAMS.md).

No additional authority or blocking product question was needed to implement Phase 4.
These are launch-readiness limitations, not claims of production approval. Stop here.
