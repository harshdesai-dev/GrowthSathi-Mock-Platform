# Phase 4.5 — exam-start performance hardening

Date: 2026-10-03. Branch `develop`; initially clean at
`beb1c4718b32a3dadaafd08babeab03c87fb6f1b`.
Scope: profiling, start-path hardening and regression verification only. No Phase 5,
scoring, results, ranking, analytics, frontend feature, Redis or Celery implementation.

## 1. Root cause and evidence

The **unchanged** Phase 4 application reproduced the problem before optimization:
500 starts, p99 **18,497.01ms**, p95 17,972.04ms, throughput 6.48/s, zero errors.
The historical 24,076.33ms Phase 4 run included browser verification on the same
laptop. We reproduced the slow-start mechanism, not that exact historic duration.

An independent instrumented baseline identified repeated full-paper validation and
ORM materialization as the dominant work: **71.14s of 83.70s aggregate application
thread CPU (85%)** for 500 starts. It instantiated hundreds of question/options and
duplicate joined mock/phase models per request, repeatedly ran field validators,
and repeated scheme/phase and database-constraint queries. It was not a per-question
SQL N+1, but large repeated Python work plus redundant constant-count queries.

Thirty-two WSGI threads in one Python process backed up. Instrumented application
p99 was 7.69s versus HTTP p99 18.83s; HTTP-minus-application p99 was 13.08s. The
residual includes worker queue, transport, client scheduling and middleware boundary
effects; it is **not** a precise pure queue timer. Overlapping span percentiles must
not be summed. Long transactions amplified occupancy but were not serialized on
one shared row in the baseline. No lock was removed to obtain the improvement.

## 2. Profiling methodology

`scripts/start_probe.py` is opt-in test-process instrumentation, not middleware or
production settings. Context-local spans measure JWT authentication, entitlement,
paper validation, ORM lookups/locks, atomic entry, connection creation, commit,
state serialization and JSON rendering. Django's scoped
[execute wrapper](https://docs.djangoproject.com/en/5.2/topics/db/instrumentation/)
groups SQL by operation/table without emitting tokens, parameters or answer keys.
An autocommit observer samples `pg_stat_activity`, wait events and blocking PIDs
every 50ms. Short waits may be missed; sampled absence is not proof of no waits.

Thread CPU is coarse on Windows (15.625ms ticks); aggregate attribution is more
useful than tiny per-request CPU percentiles. SQL wall times include driver/GIL
scheduling and fetch/decoding, not just PostgreSQL execution. There is no pool in
this configuration, so connection creation is measured, not a nonexistent pool wait.

Baseline inclusive wall span p50 / p95 / p99 (ms):

| Span | p50 | p95 | p99 |
| --- | ---: | ---: | ---: |
| JWT + user lookup, including first connection | 189.67 | 1,355.73 | 2,742.89 |
| Connection open (zero on reused connections) | 0 | 1,327.63 | 2,626.88 |
| Atomic entry, including nested savepoints | 173.33 | 509.41 | 859.10 |
| Student lock query/ORM | 169.58 | 496.17 | 874.04 |
| Mock/phase lookup ORM | 180.66 | 589.83 | 796.84 |
| Existing attempt lookup ORM | 77.31 | 300.48 | 706.10 |
| Paid access lookup | 84.76 | 289.55 | 675.24 |
| Full paper validation | 3,366.93 | 4,611.50 | 5,445.88 |
| Attempt INSERT, client-observed SQL | 86.17 | 266.53 | 600.38 |
| State serialization including response queries | 298.52 | 827.91 | 1,088.87 |
| JSON rendering | 0.12 | 0.17 | 0.25 |
| Commit | 80.48 | 293.13 | 636.69 |
| Full WSGI application | 5,029.13 | 6,536.31 | 7,685.99 |

The baseline sampled 9,420 idle-in-transaction/ClientRead backend observations,
61 active/no-wait and 13 WAL-write observations; max blocking PIDs **0**, max
observed other connections **33**, configured max_connections **100**. Connections
reopened after the existing 60s lifetime during the long run (64 opens). This is
application/driver scheduling and cold-connection overhead, not demonstrated
connection exhaustion or a PostgreSQL row-lock bottleneck.

## 3. Queries, locks and indexes

`scripts/start_query_plans.py` inventories indexes and uses EXPLAIN ANALYZE BUFFERS
on the synthetic load data, following the
[PostgreSQL EXPLAIN guidance](https://www.postgresql.org/docs/18/using-explain.html).

- Attempt already has unique `(student_id, mock_test_id)`. On this one-mock/student
  fixture PostgreSQL chose its student FK index plus mock filter; no rows discarded.
- Active access already has the compound partial unique index
  `one_active_mock_access(student_id, mock_test_id) WHERE status='ACTIVE'`.
  Entitlement used it and PK joins to OrderItem/Order, including `order.status='PAID'`.
- Mock and scheme are PK lookups; auth uses the User PK. Email/google identity
  unique indexes already exist but are not the JWT start lookup.
- Initial warm representative execution times: user 0.103ms, attempt 0.093ms,
  grant/order joins 0.123ms, mock/scheme 0.099ms; all shared-buffer hits, no disk reads.
  The first user probe included default ordering; the committed probe clears it to
  match `.get()` and repeats the plans. Tiny-fixture plans do not certify large history.

**No indexes, migrations, PostgreSQL configuration, connection settings or worker
counts changed.** The same student lock protects start versus commerce changes;
attempt resumes still lock the attempt, and first activation locks the mock briefly.
All authority, unique constraints and post-lock server-time checks remain.

## 4. Changes

[ADR 0010](adr/0010-content-keyed-start-validation.md) records the measured decision.

- Scalar question/options loading, reused scheme phase/rule reads and phase maps;
  no repeated hydration of joined mock objects or unused audit timestamps.
- Bounded 2,560-entry process-local memoization of **pure field validation only**,
  keyed by exact row contents. Never cache paper validity, entitlements or timing.
  Current rows and all aggregate/domain checks are read/run for every new start.
- Persisted mock/phase validation relies on existing database FK/UNIQUE/CHECK
  constraints instead of querying them again; field/domain checks remain. Default
  authoring validation retains full constraint checks.
- Join onboarding profile with the student lookup, locking only the student row.
- A newly created uncommitted attempt returns empty responses/zero counts directly;
  resumed attempts still query actual saved responses.
- Optional profiling/start-only benchmark modes; read-only plan/index probe;
  deadline/content-freshness/query-budget/concurrency regression tests.

No stale validity flag, pre-validation at scheduling alone, reduced entitlement
checks, relaxed answer security, changed deadlines, or extra student time.

## 5. Comparable before / after

Same full Phase 4 harness, 500 synthetic paid CET students, full 150-question paper,
real JWT/middleware/loopback HTTP/PostgreSQL 18.6. One Waitress 3.0.2 process with
32 threads, 100 HTTP clients. Windows Ryzen 5 7520U, 4 cores/8 logical CPUs,
15.28GiB RAM; isolated PostgreSQL port 55432. System PostgreSQL port 5432 untouched.
Each run uses a fresh migrated database, fresh process and cold HTTP connections.
After changes, validation memoization is explicitly cleared after fixture seeding.
No browser suite or other load benchmark was run concurrently with final starts.

| Start burst | p50 ms | p95 ms | p99 ms | max ms | Starts/s | Seconds | Errors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Before, unchanged full harness | 14,341.31 | 17,972.04 | 18,497.01 | 19,008.87 | 6.48 | 77.14 | 0 |
| After, cold full harness | 3,201.41 | 3,647.82 | 3,920.57 | 4,640.76 | 30.19 | 16.56 | 0 |

Both runs: **500 HTTP 200 starts; 6,500 total requests, zero unexpected errors**,
including 1,250 intentional 409 rejections. Both integrity checks passed: 500 unique
attempts, 250 SUBMITTED, 250 AUTO_SUBMITTED, 1,000 responses, PC version 3 and Math
version 1, no late/stale overwrites; repeated reconciliation changed zero rows.

Start p99 improved **78.8%**, throughput **4.66x**. The p99 <5s target passed on the
unprofiled comparable run; **p95 <3s was not met** (3.65s). This is not a claim that
further optimization is impossible. Further production-process sizing and profiling
remain appropriate; correctness was not traded for the target.

Final full-run non-start p99s (ms): PC payload 5,604.85; heartbeat 2,222.64; autosave
v1/v2/v3 2,208.71 / 4,369.66 / 1,972.82; lost-ack 1,969.44; stale reconnect 2,052.22;
closed PC 1,776.13; Math payload 5,184.54; Math save 4,795.61; manual submit 2,299.78;
duplicate submit 1,941.08; late save 1,562.49; deadline recovery 1,663.54. Tail variation
remains material; do not claim autosave capacity certification from this local run.
Lightweight editing/formatting occurred during later non-start bursts.

An intermediate implementation measured 5.90s p99 and passed all 6,500 requests.
Its fixture-warmed cache was identified and removed from final benchmarking. A
subsequent cold instrumented run before dropping unused timestamp decoding measured
6.03s p99. These exploratory results are not substituted for the final comparison.

## 6. Additional bursts and final profiling

Each row is 500 distinct students, 32 WSGI threads and a fresh process/database.
All returned 500 HTTP 200s, with exactly 500 distinct IN_PROGRESS attempts.

| Clients | Mode | p50 ms | p95 ms | p99 ms | max ms | Starts/s | Errors |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 50 | Cold, start-only | 1,508.45 | 2,163.83 | 4,226.08 | 5,053.93 | 30.16 | 0 |
| 100 | Cold, full reliability run | 3,201.41 | 3,647.82 | 3,920.57 | 4,640.76 | 30.19 | 0 |
| 200 | Cold, start-only | 5,701.84 | 6,172.10 | 6,489.88 | 6,686.98 | 32.91 | 0 |
| 100 | Cold, instrumented repeat | 2,978.33 | 3,783.73 | 4,290.95 | 4,988.48 | 31.56 | 0 |

Final profile: paper-validation aggregate thread CPU **7.80s**, application CPU
**15.67s**, versus 71.14s and 83.70s before. Typical SQL calls dropped from **34 to
12** per start (execute-wrapper statements, excluding connection/commit protocol).
Field validation and paper aggregate checks were still invoked for all 500 starts.

| Inclusive wall span | Before p95 ms | After p95 ms | After p99 ms |
| --- | ---: | ---: | ---: |
| Paper validation | 4,611.50 | 515.70 | 610.82 |
| Entire transactional start service | 6,165.55 | 1,019.61 | 1,205.55 |
| State serialization | 827.91 | 0.81 | 1.02 |
| Atomic entry | 509.41 | 0.08 | 0.10 |
| Entitlement | 289.55 | 91.95 | 148.57 |
| Attempt INSERT | 266.53 | 101.95 | 148.19 |
| WSGI application | 6,536.31 | 1,454.89 | 4,153.04 |
| HTTP minus application | 12,516.41 | 2,674.16 | 2,973.04 |

Final sampled max blocked backends **0**, connections **33**; 32 cold connection
opens, p99 2,903.36ms across all 500 requests (reuse contributes zeros). Cold opens
are now a conspicuous tail component, still not connection-limit exhaustion. A
prior intermediate profile sampled one brief activation blocker; activation locks
are intentional and retained. No worker count or connection setting was tuned.

Final plan repeat: user 0.124ms, attempt 0.147ms, entitlement 0.186ms, mock/scheme
0.180ms, all shared-buffer hits, no disk reads. Same index choices. The 200-client
tail and approximately 30–33 starts/s show the local single-process ceiling of the
tested configuration, not proof of PostgreSQL's production capacity ceiling.

## 7. Correctness / full verification

Fourteen new backend cases cover exact/after deadline denial, six types of current
content corruption after warming validation (including edits without timestamps),
JEE/CET cold/warm/cache-clear equivalence and a <=15-query service budget, three
actual PostgreSQL start lock waits (student/end, mock/end, mock/CET boundary), and
16 simultaneous start requests for eight students. All original tests remain.

The row-lock tests observe an actual PostgreSQL waiter before moving server time
across the boundary and releasing the lock. End-crossing starts create no attempt;
a CET boundary-crossing start enters Math with the original global end. The mixed
start race creates exactly eight attempts. Original duplicate-start, resume,
terminal-no-reopen, access, payload security, save/submit, deadline/phase and all
previous commerce/authoring concurrency tests remain green.

| Check | Result |
| --- | --- |
| Complete PostgreSQL suite | 218 passed, zero skips; includes 18 PG-only cases |
| Complete SQLite suite | 200 passed, 18 expected PostgreSQL-only skips |
| Frontend unit/integration | 35 passed |
| Chromium existing scenarios | 7 passed |
| Ruff lint / format | Passed; 78 files formatted |
| Django / deployment checks | Passed, zero issues |
| OpenAPI validation / fail-on-warn | Passed |
| Migration drift | No changes detected |
| Fresh PostgreSQL migration | Passed |
| Existing Phase 4 database | No migrations pending; 500 attempts / 1,000 responses retained |
| Separate-process recovery | Same attempt, deadline, version-7 response; submitted once |
| Frontend format / lint / types / build | Passed |
| Payment-secret bundle scan | Passed with both configured synthetic sentinels |
| npm audit | Zero vulnerabilities |
| Final full 6,500-request reliability run | Zero unexpected errors; integrity passed |
| Additional 50/200/100-profile start bursts | All passed; zero unexpected errors |
| Git whitespace | Passed |

Final review preserved original model-field normalization for unsaved authoring/
import objects; only database scalar rows use memoization. Both complete backend
suites were rerun after this compatibility refinement. The measured start path is
unchanged. Development-only failures corrected: initial script lint/format errors;
the restart suffix safety guard rejected an incorrectly named empty test database.
No application correctness/concurrency failure was observed in the full suites.

Browser tests use controlled API fixtures, as in Phase 4, rather than real Google
sessions. The benchmark separately uses actual Django/JWT/PostgreSQL HTTP requests.

## 8. Exact commands

PowerShell, repository `GrowthSathi-Mock-Platform`. The sandbox helper failed before
process launch, so shell commands used escalation. The normal Python launcher is
unavailable here; the existing ignored site-packages were loaded with embedded Python.
No new dependency was installed. Benchmark/verification output remained local.

From repository root, start the existing isolated cluster:

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe' -D 'backend\.postgres-data' -l 'backend\.postgres-data\server.log' -o '-p 55432 -h 127.0.0.1' -w start
```

From `backend`:

```powershell
$env:DJANGO_SETTINGS_MODULE='config.settings.test'
$env:PGPASSWORD='growthsathi'
& 'C:\Program Files\PostgreSQL\18\bin\createdb.exe' -h 127.0.0.1 -p 55432 -U growthsathi growthsathi_phase45_pytest
$env:DATABASE_URL='postgresql://growthsathi:growthsathi@127.0.0.1:55432/growthsathi_phase45_pytest'
& 'C:\Program Files\PostgreSQL\18\pgAdmin 4\python\python.exe' -c "import sys,runpy; sys.path.insert(0,r'.'); sys.path.insert(1,r'.venv\Lib\site-packages'); sys.argv=['pytest','-q','-p','no:cacheprovider','--create-db']; runpy.run_module('pytest',run_name='__main__')"
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
& 'C:\Program Files\PostgreSQL\18\pgAdmin 4\python\python.exe' -c "import sys,runpy; sys.path.insert(0,r'.'); sys.path.insert(1,r'.venv\Lib\site-packages'); sys.argv=['pytest','-q','-p','no:cacheprovider']; runpy.run_module('pytest',run_name='__main__')"
& 'C:\Program Files\PostgreSQL\18\pgAdmin 4\python\python.exe' -c "import sys,runpy; sys.path.insert(0,r'.venv\Lib\site-packages'); sys.argv=['ruff','check','.']; runpy.run_module('ruff',run_name='__main__')"
& 'C:\Program Files\PostgreSQL\18\pgAdmin 4\python\python.exe' -c "import sys,runpy; sys.path.insert(0,r'.venv\Lib\site-packages'); sys.argv=['ruff','format','--check','.']; runpy.run_module('ruff',run_name='__main__')"
```

Also ran Ruff `format .` during development, an initial full SQLite pass (190 passed,
14 skips) and targeted `tests/test_start_hardening.py` before the final full suites.

For each database below, `createdb` used the same host/port/user command above,
then DATABASE_URL was set to that name and this migration command was executed:

```powershell
& 'C:\Program Files\PostgreSQL\18\pgAdmin 4\python\python.exe' -c "import sys,runpy; sys.path.insert(0,r'.'); sys.path.insert(1,r'.venv\Lib\site-packages'); sys.argv=['manage.py','migrate','--noinput']; runpy.run_path('manage.py',run_name='__main__')"
```

| Database | Script and extra flags |
| --- | --- |
| `growthsathi_before_phase45_phase4_load` | Unchanged Phase 4 full harness, 100 clients |
| `growthsathi_profile_before_phase45_phase4_load` | Start-only, profile, 100 clients, pre-optimization |
| `growthsathi_after_phase45_phase4_load` | Intermediate full harness, 100 clients |
| `growthsathi_profile_after_phase45_phase4_load` | Intermediate cold profile, 100 clients |
| `growthsathi_final100_phase45_phase4_load` | Final cold full harness, 100 clients |
| `growthsathi_verify50_phase45_phase4_load` | Final cold start-only, 50 clients |
| `growthsathi_verify200_phase45_phase4_load` | Final cold start-only, 200 clients |
| `growthsathi_verify100_phase45_phase4_load` | Final cold start-only/profile, 100 clients |
| `growthsathi_phase45_empty` | Fresh schema and management checks |
| `growthsathi_phase45_phase4_restart` | Separate-process prepare/recover |

Full benchmark command (same bootstrap, replace concurrency and append
`'--start-only'` / `'--profile'` as listed above):

```powershell
& 'C:\Program Files\PostgreSQL\18\pgAdmin 4\python\python.exe' -c "import sys,runpy; sys.path.insert(0,r'.'); sys.path.insert(1,r'.venv\Lib\site-packages'); sys.argv=['phase4_load.py','--students','500','--concurrency','100','--threads','32']; runpy.run_path('scripts/phase4_load.py',run_name='__main__')"
```

Harnesses refuse existing populated databases and never delete fixtures. Retained
databases cannot be reused for a new benchmark; choose a new name with the required
`phase4_load` / `phase4_restart` suffix. An initial restart invocation on the empty
`growthsathi_phase45_restart` was correctly refused by its suffix guard; it was
rerun on the correctly suffixed database, not by weakening the guard.

Plans on the before and final100 load databases, using their respective DATABASE_URL:

```powershell
& 'C:\Program Files\PostgreSQL\18\pgAdmin 4\python\python.exe' -c "import sys,runpy; sys.path.insert(0,r'.'); sys.path.insert(1,r'.venv\Lib\site-packages'); sys.argv=['start_query_plans.py']; runpy.run_path('scripts/start_query_plans.py',run_name='__main__')"
```

Management verification on `growthsathi_phase45_empty`:

```powershell
$env:DJANGO_SECRET_KEY='phase45-check-only-not-production-long-secret-0123456789abcdef'
$env:JWT_SECRET='phase45-check-only-jwt-signing-key-0123456789abcdef'
$env:GOOGLE_CLIENT_ID='phase45-verification.apps.googleusercontent.com'
foreach ($verificationCommand in @('migrate --noinput','check','makemigrations --check --dry-run','spectacular --validate --fail-on-warn --file .postgres-data/phase45-openapi.yml','check --deploy --settings=config.settings.production')) {
  & 'C:\Program Files\PostgreSQL\18\pgAdmin 4\python\python.exe' -c "import sys,runpy,shlex; sys.path.insert(0,r'.'); sys.path.insert(1,r'.venv\Lib\site-packages'); sys.argv=['manage.py']+shlex.split(sys.argv[1]); runpy.run_path('manage.py',run_name='__main__')" "$verificationCommand"
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

Existing Phase 4 migration verification: set DATABASE_URL to the baseline load
database and run `migrate --noinput` again (no migrations pending), then:

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\psql.exe' -h 127.0.0.1 -p 55432 -U growthsathi -d growthsathi_before_phase45_phase4_load -Atc "SELECT app || ':' || name FROM django_migrations WHERE app IN ('exams','commerce','attempts'); SELECT count(*) FROM attempts_attempt; SELECT count(*) FROM attempts_studentresponse;"
```

Restart with DATABASE_URL ending in `growthsathi_phase45_phase4_restart`, two invocations:

```powershell
foreach ($restartStep in @('prepare','recover')) {
  & 'C:\Program Files\PostgreSQL\18\pgAdmin 4\python\python.exe' -c "import sys,runpy; sys.path.insert(0,r'.'); sys.path.insert(1,r'.venv\Lib\site-packages'); sys.argv=['phase4_restart.py',sys.argv[1]]; runpy.run_path('scripts/phase4_restart.py',run_name='__main__')" "$restartStep"
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

From `frontend` (unchanged product files; formatting verified without rewriting them):

```powershell
$env:RAZORPAY_KEY_SECRET='phase3-secret-sentinel-not-a-real-credential'
$env:RAZORPAY_WEBHOOK_SECRET='phase3-webhook-sentinel-not-a-real-credential'
foreach ($scriptName in @('format:check','lint','typecheck','test','build','build:check-secrets','test:browser')) {
  npm.cmd run $scriptName
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
npm.cmd audit --audit-level=high
```

Final repository checks/commit and isolated-cluster shutdown:

```powershell
git branch --show-current
git merge-base --is-ancestor beb1c4718b32a3dadaafd08babeab03c87fb6f1b HEAD
git diff --check
git add README.md backend/apps/attempts/services.py backend/apps/exams/validation.py backend/scripts/phase4_load.py backend/scripts/start_probe.py backend/scripts/start_query_plans.py backend/tests/test_start_hardening.py docs/adr/README.md docs/adr/0010-content-keyed-start-validation.md docs/PHASE45_VERIFICATION.md
git diff --cached --check
git commit -m "perf: harden concurrent exam start path"
git status --short
git log -1 --format=%H
git rev-list --count beb1c4718b32a3dadaafd08babeab03c87fb6f1b..HEAD
& 'C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe' -D 'backend\.postgres-data' -w stop
```

## 9. Changed files and commit

Application: `backend/apps/attempts/services.py`, `backend/apps/exams/validation.py`.
Tests/tools: `backend/tests/test_start_hardening.py`, `backend/scripts/phase4_load.py`,
`backend/scripts/start_probe.py`, `backend/scripts/start_query_plans.py`.
Documentation: `README.md`, `docs/adr/README.md`, ADR 0010 and this report.
No frontend product changes, dependency additions, schema or old ADR edits.

Exactly one intended commit: `perf: harden concurrent exam start path`. The final
delivery supplies its hash; a containing commit cannot embed its own hash. No push.

## 10. Remaining risks / readiness

The improvement supports proceeding with **Phase 5 development** following the
successful full verification; it is **not paid-launch or production capacity
approval**. The p95 target remains open. Cold PostgreSQL connections, single-process
Python scheduling, process-local cache cold misses and simultaneous larger bursts
still affect tails. Cache capacity is entry-bounded, not byte-bounded; unusually
large authored content can consume more memory. Future field validators must remain
pure or be excluded from memoization. No mutable ORM instances are cached.

Deployment-host multi-process sizing, simultaneous paper fetch/save traffic, TLS/WAN,
real phone/browser storage, real Google/Razorpay sessions, three-hour soak, clock
synchronization, restart/failover and multi-mock/history-scale plans remain launch
checks. Client and server sharing one laptop limits causal capacity conclusions.
All existing [live exam launch gates](LIVE_EXAMS.md) remain. Phase 5 is not started.
