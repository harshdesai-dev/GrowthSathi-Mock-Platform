# ADR 0003 Deadline enforcement without a Phase 0 worker

- Status: Accepted
- Date: 2026-10-02

## Context

The exam must reject late writes and honor global phase deadlines even if a browser timer is wrong. Introducing Redis and Celery before measured need would add infrastructure and failure modes.

## Decision

Do not add Redis, Celery or another task queue in Phase 0.

PostgreSQL timestamps and Django domain services will be authoritative. Starting an attempt, loading it, saving a response, handling a heartbeat, submitting, reading a result and performing an Admin operation must first reconcile the mock, phase and attempt state against the server clock.

Expired response writes are rejected. An unfinished expired attempt is lazily transitioned to `AUTO_SUBMITTED` using its successfully saved responses. Reconciliation operations must be idempotent and transaction-safe.

Deadline and reconciliation behavior will live behind service interfaces so a scheduled worker can call the same operations later without changing domain rules. Phase 8 load and reliability tests determine whether a worker is necessary.

## Consequences

- Correctness does not depend on a scheduler firing at an exact instant.
- An attempt row may remain physically `IN_PROGRESS` until a relevant request or reconciliation command observes it, while its effective state is already expired.
- Admin monitoring and result calculation must invoke reconciliation before relying on stored statuses.
- A future worker is an optimization and operational improvement, not a second source of truth.
