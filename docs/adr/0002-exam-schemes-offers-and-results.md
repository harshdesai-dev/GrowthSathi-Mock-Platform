# ADR 0002 Exam schemes offers and results

- Status: Accepted
- Date: 2026-10-02

## Context

Official exam rules may change, combo purchases must identify their exact mocks, and publication must wait for answer-key verification.

## Decision

Exam schemes are versioned and configurable. Each mock references an immutable scheme version. Before every mock, Admin revalidates the scheme against the latest official JEE Main or MHT-CET PCM rules and creates a new version when required.

`MockOffer` and `MockOfferItem` define products. A combo offer must contain exactly one JEE Main mock and exactly one MHT-CET PCM mock. Backend services calculate order totals from the offer and create price snapshots on order items.

`result_release_at` is an earliest-publication guard. It never publishes results automatically. Admin may publish only after verifying the answer key and completing a consistent calculation run.

Ranking includes:

- all `SUBMITTED` attempts
- `AUTO_SUBMITTED` attempts with at least one saved response

It excludes `INVALID` attempts, empty auto-submissions and users who never started.

V1 phone numbers are Indian mobile numbers, stored as `+91XXXXXXXXXX`, and are not unique.

## Consequences

- Historical mocks remain reproducible when official rules change.
- Combo access is deterministic and auditable.
- Ranking and percentile calculations share one explicit participant population.
- Publication needs a transactionally consistent calculation and validation service in Phase 5.
