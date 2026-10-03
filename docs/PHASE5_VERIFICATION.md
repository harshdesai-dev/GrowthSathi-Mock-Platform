# Phase 5 verification — scoring and published results

Verification date: 2026-10-03. Base: `develop` at
`8a1f21c6df8549003b266f6a7a274fbe67f03c19`, initially clean. SPEC, all ADRs through
0010, EXAM_ADMINISTRATION, PAYMENTS and Phase 3/4/4.5 verification were read before
implementation. Actual logo and result reference informed only in-scope styling.
No Phase 6 features, Redis, Celery, AI, analytics or dependency additions.

## 1. Summary

Phase 5 implements configuration-driven scoring, manually published private report
cards, competition ranks, Mock Percentile, masked leaderboard, published answer review,
previous same-exam score/history and audited correction/republication. No automatic
clock-triggered publication. Existing live exam code remains authoritative for saves.

## 2. Architecture

[ADR 0011](adr/0011-published-results.md) records the decisions. Django/PostgreSQL
remain the source of truth. Every result mutation and key correction serializes on
MockTest, then attempt locks protect accepted inputs. Frozen generation snapshots,
source/input/output hashes and atomic writes prevent partial or mixed batches.
Student reads select a published generation, then use its immutable snapshots.

## 3. Models/migration

`results.0001_initial` adds ResultCalculationRun, ResultCalculationEntry and Result.
Result has UUID, one-to-one Attempt, score/counts/rank/percentile, run/entry pointers,
published timestamp and creation/update timestamps. Entries preserve old generations.
Runs retain verifier, paper/key/rules/audit revision, accepted responses via entries,
participant count, excluded attempts/reasons, status/error/notes and publication/
withdrawal actors/times/reason. Partial unique constraints allow one current draft and
one published run per mock. Rank/percentile/count checks and one-entry-per-run-attempt
constraints apply. Direct save/update/delete is blocked outside domain operations.

Fresh migration passed. Upgrade on `growthsathi_final100_phase45_phase4_load` applied
only the new migration: **500 attempts and 1,000 responses before and after**, no
Result rows fabricated. Migration drift check passed.

## 4–8. Scoring, numerical answers, eligibility, rank and percentile

- Pure scoring reads Question positive/negative marks and SchemeRule unanswered marks;
  no exam-name branch. Baselines verified: JEE +4/-1/0, CET P/C +1 and M +2, no penalty.
- Finite Decimal text, precision 50, inclusive absolute tolerance; no float equality,
  no operand rounding. Canonical saved blank values are unattempted.
- All SUBMITTED qualify, including blank; AUTO_SUBMITTED requires any saved row.
  INVALID, no-response auto submissions and never-started users do not qualify.
- Competition rank: `1 + count(score > own score)`. Equal scores share rank; no speed tie-break.
- Mock Percentile: `100 * count(score <= own score) / eligible_count`, two-decimal
  ROUND_HALF_UP. It is explicitly not official NTA/CET normalization.

## 9–11. Runs, publication and corrections

Owner flow: CLOSED after global end → reconcile → explicitly verify key with notes →
calculate → inspect entries → publish at/after earliest release. Calculation is
transactional and repeatable for the same inputs. Empty eligible batches are supported
without invented rank/percentile rows. Failed semantic calculations record FAILED;
unexpected transaction failures roll back. Retry does not duplicate results.

Publication revalidates current paper, stored snapshot, input digest, exact eligible
membership, count and output digest before atomically publishing every row and mock.
Duplicate publication retains the original timestamp. Reaching release time alone
does nothing. Early CLOSED mocks still cannot release keys before global end.

Audited correction invalidates draft runs. Published keys first require reasoned,
actor-attributed withdrawal to CLOSED; all subsequent student reads are gated until
verification, recalculation and republication. Old entries remain immutable. Injected
first-publication and republication failures verified transaction rollback, including
retaining old pointers without exposing the withdrawn batch.

## 12. APIs

Authenticated GET `/api/v1/mocks/{id}/result/`, `/leaderboard/`, `/review/` and
`/api/v1/results/history/`. Own result/review/history only. No student-ID override.
409 for unpublished/withdrawn/excluded, 404 when no own attempt, 401 without auth.
Explicit serializers exclude internal/audit/payment/Google identity fields. Masked
leaderboard rows contain only rank/name/score/percentile. All responses are private,
no-store. Review comes from the published snapshot, never the mutable current key.

## 13–14. Frontend and Admin

Mobile-first charcoal/lime/white report, leaderboard, review and history use the
actual logo and existing tokens. Score/rank/Mock Percentile lead; required counts and
previous comparison follow. No charts, predictions, exports or Phase 6 dashboard.
Safe existing Markdown/KaTeX and HTTPS image handling are reused. Existing JWT refresh
recovery, loading/error/retry and first-result/empty-history states are covered.
New answer review is not persisted in IndexedDB/localStorage.

Owner-only Result operations are linked from MockTest. Reconcile, verify, calculate,
inspect, publish and withdraw require explicit forms/confirmation; verify/withdraw
require notes/reason. Entries/results/runs are readonly; exclusions are visible.
[RESULTS.md](RESULTS.md) is the operational checklist.

## 15. Tests and quality gates

| Gate | Final result |
| --- | --- |
| PostgreSQL full pytest | **264 passed**, 202.85s |
| SQLite full pytest | **241 passed**, 23 PostgreSQL-only skips, 87.58s |
| New Phase 5 backend cases | **46**, including 5 PostgreSQL concurrency cases |
| Frontend Vitest | **41 passed**, 10 files (35 existing + 6 new) |
| Chromium Playwright | **13 passed**, 55.3s (7 existing + 6 new) |
| Frontend Prettier/ESLint/TypeScript | Passed, zero lint warnings |
| Production build / payment secret scan | Passed |
| npm audit | 0 vulnerabilities |
| Backend Ruff / format | Passed; 86 files formatted |
| Django checks / deployment checks | No issues |
| OpenAPI validation with fail-on-warn | Passed |
| Fresh migrations / Phase 4.5 populated upgrade / drift | Passed |
| Fresh-process live attempt recovery | PREPARE PASS / RECOVER PASS |
| Existing real-HTTP exam burst | 6,500 requests, zero unexpected errors; all integrity assertions passed |

Coverage includes JEE MCQ/numerical, CET P/C/M, maximum/zero/negative scores, decimal
boundaries and unsafe floats, all counts, blank visits/submissions, every exclusion,
ties/rounding/single participant, earlier same-exam selection, draft/different-exam
exclusion, publication timing/state/owner gates, unpublished/privacy/key leakage,
corruption of membership/score/source/responses/stored snapshot, failed batch retry,
correction rank/percentile changes, withdrawal and atomic republication.

All five viewport widths (360/390/430/768/1440) were checked for document overflow.
Report → leaderboard → review → history navigation passed, including math and
Correct/Incorrect/Unattempted states. Publication gate, network retry, JWT recovery,
refresh and withdrawal checks passed. Screenshots were visually inspected at mobile
and desktop sizes; artifacts remain ignored in `frontend/test-results/`.

Initial admin template-location and frontend non-component-export lint failures were
fixed, then the full checks rerun. Initial migration generation warned that the default
5432 connection was unavailable; final migration/check/test runs explicitly used the
isolated local cluster on 55432. No system-cluster data was modified.

## 16. PostgreSQL/concurrency

All **23 PostgreSQL-only cases** ran (none skipped in the PostgreSQL suite), including
existing payment/import/live exam lock-wait races. New threaded, separate-connection,
barrier-synchronized tests exercise duplicate verification+calculation starts, duplicate
calculation, duplicate publication, correction vs publication and calculation vs
publication. There is one generation/entry set for duplicate starts, one Result per
Attempt and either a complete old-key publication or rejection/invalidation, never a
mixed batch. Deliberate final-write failures confirm rollback of publication/republication.

## 17. Performance and regression methodology

Host: Windows, Ryzen 5 7520U (4 cores/8 threads), ~15.28 GiB RAM, PostgreSQL 18.6 on
127.0.0.1:55432, embedded Python 3.13 and installed project dependencies. Isolated
synthetic datasets only, no real gateway or official-rule attestation. No worker/cache
infrastructure introduced. The benchmark script refuses non-PostgreSQL, wrong-suffix
or populated databases; it never deletes fixtures.

`scripts/phase5_results.py`: 500 participants each for real configured JEE 75 and CET
150-question papers, with 37,500/75,000 saved response rows. Includes five expired
IN_PROGRESS attempts, mixed correct/incorrect/blank answers and a maximum-score student.
Fixtures/migrations are outside timings. Each verify/calculate/publish call is measured
with perf_counter and CaptureQueriesContext (transaction SQL included). Field-validation
memoization is cleared before verification and calculation. All 500 independently
expected scores, maximum, membership and reconciliation are asserted. Query guards
reject >=60 calculation/publication queries; no per-student/question database loop.

Final run (`growthsathi_final_phase5_results`, after snapshot-integrity guard):

| Paper / 500 participants | Key verification | Calculation | Publication |
| --- | --- | --- | --- |
| JEE, 75 questions | 0.527s / 32 queries | **1.332s / 35 queries** | 0.668s / 49 queries |
| CET, 150 questions | 1.033s / 35 queries | **2.643s / 38 queries** | 1.347s / 52 queries |

Earlier full run: JEE calculation 1.650s/35 queries, publication 0.806s/49; CET
calculation 2.427s/38, publication 1.116s/52. Both runs passed all independent
500-score/membership/reconciliation assertions. Variability is expected on one laptop.

Unmodified existing `phase4_load.py` ran afterward with 500 paid synthetic CET students,
100 client concurrency, 32 Waitress threads, real HTTP/PostgreSQL and a full 150-question
paper. **6,500 requests, zero unexpected errors**. Unique attempt, exact terminal
counts/response counts/versions, stale replay rejection, closed-phase rejection and
deadline rejection assertions all passed. Representative timings (milliseconds):

| Burst | Requests | p50 | p95 | p99 |
| --- | ---: | ---: | ---: | ---: |
| Starts | 500 | 3222.76 | 3901.61 | 4478.41 |
| PC paper | 500 | 4807.97 | 6095.19 | 6435.46 |
| Heartbeat | 500 | 1951.46 | 2519.61 | 2688.79 |
| Autosave v1 | 500 | 1632.09 | 2408.97 | 4590.60 |
| Autosave v2 | 500 | 1524.78 | 1709.77 | 1835.23 |
| Autosave v3 | 500 | 1492.29 | 1759.36 | 1949.10 |
| Lost-ack retry | 500 | 1370.43 | 1549.24 | 1773.38 |
| Stale reconnect (expected 409) | 500 | 1424.89 | 1623.10 | 1722.48 |
| Closed PC (expected 409) | 500 | 1163.97 | 1539.35 | 1749.08 |
| Mathematics paper | 500 | 3086.33 | 3638.14 | 3867.31 |
| Mathematics save | 500 | 1541.84 | 1985.91 | 3492.44 |
| Manual submit | 250 | 1377.06 | 1647.64 | 1820.24 |
| Duplicate submit | 250 | 1134.99 | 1343.79 | 1491.77 |
| Late save (expected 409) | 250 | 921.28 | 1126.05 | 1249.69 |
| Deadline recovery | 250 | 1187.13 | 1408.90 | 1460.56 |

These inherited live-exam p95 targets are **not claimed met**. Start p99 4.478s here
versus ~3.92s in the earlier Phase 4.5 run is not a controlled causal comparison;
the live start implementation is unchanged. Capacity/timeout launch work remains.

These are single-process local service timings, not HTTP result-operation latency,
production p95/p99, WAN or multi-mock capacity measurements. Snapshot memory/storage,
database/HTTP timeouts and deployment-host concurrency still need sizing.

## 18. Exact verification commands

Commands below use PowerShell from `backend` unless marked otherwise. The bundled
interpreter needs the repository and existing ignored virtualenv added to sys.path.
No environment file or production secret is read or printed. Credentials here are
only for the isolated development cluster.

Start cluster from repository root (or reuse it if already running):

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe' -D 'backend\.postgres-data' -l 'backend\.postgres-data\phase5-server.log' -o '-p 55432 -h 127.0.0.1' -w start
```

Create fresh isolated databases (the already-populated fixtures must not be rerun):

```powershell
$env:PGPASSWORD='growthsathi'
foreach ($dbName in @('growthsathi_phase5_empty','growthsathi_phase5_results','growthsathi_final_phase5_results','growthsathi_phase5_phase4_load','growthsathi_phase5_phase4_restart')) {
  & 'C:\Program Files\PostgreSQL\18\bin\createdb.exe' -h 127.0.0.1 -p 55432 -U growthsathi $dbName
}
$env:DJANGO_SETTINGS_MODULE='config.settings.test'
$env:DATABASE_URL='postgresql://growthsathi:growthsathi@127.0.0.1:55432/growthsathi_phase5_empty'
```

Schema generation used `manage.py makemigrations results`. Final static/full tests:

```powershell
& 'C:\Program Files\PostgreSQL\18\pgAdmin 4\python\python.exe' -c "import sys,runpy; sys.path.insert(0,r'.venv\Lib\site-packages'); sys.argv=['ruff','check','.']; runpy.run_module('ruff',run_name='__main__')"
& 'C:\Program Files\PostgreSQL\18\pgAdmin 4\python\python.exe' -c "import sys,runpy; sys.path.insert(0,r'.venv\Lib\site-packages'); sys.argv=['ruff','format','--check','.']; runpy.run_module('ruff',run_name='__main__')"
& 'C:\Program Files\PostgreSQL\18\pgAdmin 4\python\python.exe' -c "import sys,runpy; sys.path.insert(0,r'.'); sys.path.insert(1,r'.venv\Lib\site-packages'); sys.argv=['pytest','-q','-p','no:cacheprovider']; runpy.run_module('pytest',run_name='__main__')"
```

SQLite: set `$env:DATABASE_URL=''` and rerun the exact pytest command. PostgreSQL
focused run used the same bootstrap with `['pytest','tests/test_results.py','-q','-p',
'no:cacheprovider','--maxfail=3']`; the final full run above includes every race.
Formatting edits used `ruff format .` and focused `ruff check ... --fix` before final gates.

Management gates:

```powershell
$env:DATABASE_URL='postgresql://growthsathi:growthsathi@127.0.0.1:55432/growthsathi_phase5_empty'
$env:DJANGO_SECRET_KEY='phase5-check-only-not-production-long-secret-0123456789abcdef'
$env:JWT_SECRET='phase5-check-only-jwt-signing-key-0123456789abcdef'
$env:GOOGLE_CLIENT_ID='phase5-verification.apps.googleusercontent.com'
foreach ($verificationCommand in @('migrate --noinput','check','makemigrations --check --dry-run','spectacular --validate --fail-on-warn --file .postgres-data/phase5-openapi.yml','check --deploy --settings=config.settings.production')) {
  & 'C:\Program Files\PostgreSQL\18\pgAdmin 4\python\python.exe' -c "import sys,runpy,shlex; sys.path.insert(0,r'.'); sys.path.insert(1,r'.venv\Lib\site-packages'); sys.argv=['manage.py']+shlex.split(sys.argv[1]); runpy.run_path('manage.py',run_name='__main__')" "$verificationCommand"
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

For each benchmark/restart DB, set its DATABASE_URL and run the same migrate command
before the harness. Upgrade used DATABASE_URL ending `growthsathi_final100_phase45_phase4_load`:

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\psql.exe' -h 127.0.0.1 -p 55432 -U growthsathi -d growthsathi_final100_phase45_phase4_load -Atc "SELECT count(*) FROM attempts_attempt; SELECT count(*) FROM attempts_studentresponse; SELECT count(*) FROM django_migrations WHERE app='results';"
& 'C:\Program Files\PostgreSQL\18\pgAdmin 4\python\python.exe' -c "import sys,runpy; sys.path.insert(0,r'.'); sys.path.insert(1,r'.venv\Lib\site-packages'); sys.argv=['manage.py','migrate','--noinput']; runpy.run_path('manage.py',run_name='__main__')"
& 'C:\Program Files\PostgreSQL\18\bin\psql.exe' -h 127.0.0.1 -p 55432 -U growthsathi -d growthsathi_final100_phase45_phase4_load -Atc "SELECT count(*) FROM attempts_attempt; SELECT count(*) FROM attempts_studentresponse; SELECT count(*) FROM django_migrations WHERE app='results'; SELECT count(*) FROM results_result;"
```

Benchmarks (first run DB `growthsathi_phase5_results`, final run DB below):

```powershell
$env:DATABASE_URL='postgresql://growthsathi:growthsathi@127.0.0.1:55432/growthsathi_final_phase5_results'
& 'C:\Program Files\PostgreSQL\18\pgAdmin 4\python\python.exe' -c "import sys,runpy; sys.path.insert(0,r'.'); sys.path.insert(1,r'.venv\Lib\site-packages'); sys.argv=['phase5_results.py']; runpy.run_path('scripts/phase5_results.py',run_name='__main__')"
$env:DATABASE_URL='postgresql://growthsathi:growthsathi@127.0.0.1:55432/growthsathi_phase5_phase4_load'
& 'C:\Program Files\PostgreSQL\18\pgAdmin 4\python\python.exe' -c "import sys,runpy; sys.path.insert(0,r'.'); sys.path.insert(1,r'.venv\Lib\site-packages'); sys.argv=['phase4_load.py','--students','500','--concurrency','100','--threads','32']; runpy.run_path('scripts/phase4_load.py',run_name='__main__')"
$env:DATABASE_URL='postgresql://growthsathi:growthsathi@127.0.0.1:55432/growthsathi_phase5_phase4_restart'
foreach ($restartStep in @('prepare','recover')) {
  & 'C:\Program Files\PostgreSQL\18\pgAdmin 4\python\python.exe' -c "import sys,runpy; sys.path.insert(0,r'.'); sys.path.insert(1,r'.venv\Lib\site-packages'); sys.argv=['phase4_restart.py',sys.argv[1]]; runpy.run_path('scripts/phase4_restart.py',run_name='__main__')" "$restartStep"
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

From `frontend` (focused Prettier writes preceded the final checks):

```powershell
$env:RAZORPAY_KEY_SECRET='phase3-secret-sentinel-not-a-real-credential'
$env:RAZORPAY_WEBHOOK_SECRET='phase3-webhook-sentinel-not-a-real-credential'
foreach ($scriptName in @('format:check','lint','typecheck','test','build','build:check-secrets','test:browser')) {
  npm.cmd run $scriptName
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
npm.cmd audit --audit-level=high
```

Repository-root completion commands:

```powershell
git branch --show-current
git diff --check
git add README.md backend/apps/exams/admin.py backend/apps/exams/services.py backend/apps/results backend/config/settings/base.py backend/config/urls.py backend/scripts/phase5_results.py backend/tests/test_results.py docs/RESULTS.md docs/PHASE5_VERIFICATION.md docs/EXAM_ADMINISTRATION.md docs/adr/README.md docs/adr/0011-published-results.md frontend/src/app/AppRouter.tsx frontend/src/pages/DashboardPage.tsx frontend/src/pages/ExamPages.tsx frontend/src/api/results.ts frontend/src/pages/ResultPages.tsx frontend/src/pages/ResultPages.test.tsx frontend/src/results/format.ts frontend/src/styles/results.css frontend/e2e/results.spec.ts
git diff --cached --check
git commit -m "feat: implement scoring and published results"
git status --short
git log -1 --format=%H
git rev-list --count 8a1f21c6df8549003b266f6a7a274fbe67f03c19..HEAD
& 'C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe' -D 'backend\.postgres-data' -w stop
```

## 19–20. Overall result, files and commit

The final delivery reports the containing commit hash (a commit cannot embed its own
hash). Exactly one intended commit: `feat: implement scoring and published results`.
No push and no Phase 6 work. No blockers requiring a product decision were identified.
All Phase 5 correctness/quality checks passed. The inherited live-exam production
latency readiness risk remains explicitly open; this is not production launch approval.

Changed files are the new `backend/apps/results/` domain/API/admin/migration/template,
`backend/scripts/phase5_results.py`, `backend/tests/test_results.py`, exam correction/
admin hooks, settings/URL registration; frontend results API/pages/tests/styles/format,
browser tests and narrow routing/account/terminal links; README, ADR index/new ADR,
EXAM_ADMINISTRATION pointer and RESULTS/PHASE5_VERIFICATION documentation. SPEC,
accepted earlier ADRs, old tests, dependencies, live engine persistence and design
assets are not rewritten.

## 21. Remaining risks/manual verification

- Local tests/benchmarks are not paid-launch approval. Existing Phase 4/4.5 p95 and
  deployment-host/WAN/three-hour-soak/restart/failover gates remain applicable.
- Run the owner verification/correction/withdrawal/republication checklist with a real
  authored paper and independently checked key; automated tests cannot verify human
  answer-key judgment. No real exam-rule attestation or payment was fabricated.
- Real Android/iOS browsers, screen-reader/keyboard walkthroughs and production Google
  sessions remain manual tests. Playwright uses synthetic API responses; backend tests
  separately verify real PostgreSQL services and authenticated DRF payloads.
- Measure HTTP/database timeouts and lock waits on the deployment host. Snapshot retention
  adds storage and memory; leaderboard/history are unpaginated at this V1 scale.
- Withdrawal cannot revoke content already delivered or an in-flight immutable read.
  No durable client review cache is added; subsequent requests are publication-gated.
- Maintain scorer-version compatibility when changing scoring algorithms in future.
  Existing saved snapshots/revisions and immutable entries must remain interpretable.

STOP after Phase 5.
