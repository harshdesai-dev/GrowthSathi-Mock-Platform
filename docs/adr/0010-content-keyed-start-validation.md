# ADR 0010: Content-keyed field validation on the exam start path

Date: 2026-10-03. Status: accepted for Phase 4.5.

## Evidence and scope

The unchanged Phase 4 burst reproduced slow starts: 500 students, 100 HTTP clients,
32 Waitress threads, start p99 18.50s (historical Phase 4: 24.08s). Opt-in profiling
measured 71.14s of 83.70s aggregate application thread CPU in full-paper validation.
The application p99 was 7.69s; HTTP-minus-application p99 was 13.08s. Spans overlap,
so these percentiles must not be added. PostgreSQL sampled no blocking lock waits,
at most 33 connections against a 100-connection limit, and indexed warm lookup
plans executed in approximately 0.1ms. Repeated Python/ORM validation saturates the
single-process worker pool; the evidence does not justify removing safety locks,
adding indexes, or introducing infrastructure.

This refines the implementation of ADRs 0007 and 0009, not their requirement to
derive current paper validity at every new start. No Phase 5 functionality.

## Decision

- Read current scheme/rules, mock phases, questions and options for every new start.
  Use scalar question/option rows and a phase map instead of duplicated joined ORM
  instances. Read scheme phases/rules once. Audit timestamps are not paper content
  and need not be decoded for validation.
- Reuse only **pure Question/QuestionOption field-validation errors**, keyed by the
  model, exact field values and excluded relation fields. Use a bounded 2,560-entry
  process-local LRU; no cached paper-valid flag, timestamp-only freshness token,
  database snapshot, entitlement, timing, lifecycle state or student payload.
  Unsaved authoring/import model instances retain their original `clean_fields`
  behavior and normalization; memoization applies only to database scalar rows.
- Every aggregate/domain check still runs: row counts and numbering, phase ownership,
  scheme/rule distribution, marks, question/answer shape, option labels/order,
  correct-answer cardinality, explanations, content, and fixed scheme duration.
  Raw content changes without updated timestamps change the field-cache key.
- The start service explicitly validates **persisted** mock/phase rows. PostgreSQL
  already enforces their foreign keys, UNIQUE and CHECK constraints. Do not issue
  redundant validation queries for those constraints; retain field and model clean
  checks. Authoring/default validation still performs full constraint validation.
- Join onboarding profile when locking the student, using `FOR UPDATE OF self`.
  Keep the same student lock ordering as commerce, per-attempt resume lock,
  unique student/mock constraint, and short lazy mock-activation lock.
- A newly inserted, uncommitted attempt cannot have responses. Return zero counts
  and an empty response list without three queries. Resumes and other state reads
  still query authoritative saved responses.
- Recheck server time after validation/lock waits. No deadline, CET, entitlement,
  terminal-state, response-write or payload-security rule changes.

## Consequences

Cold starts/eviction/restarts recompute pure validation; correctness never depends on
cache availability. Each process owns its own bounded cache; concurrent cold misses
may duplicate pure work. It retains private answer-key content in server memory,
never in student responses, shared client caches, logs or profile output. No mutable
ORM instances are cached. Field validators must remain pure; future DB-dependent
validators must not be put behind this function.

PostgreSQL/Django remain authoritative, with no Redis, Celery, external cache,
connection-pool dependency or schema migration. Synthetic local benchmarks are not
production certification. See PHASE45_VERIFICATION.md for final measurements,
regression results, commands, and remaining launch gates.
