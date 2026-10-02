# ADR 0007: Versioned exam authoring, validation and import boundaries

- Status: Accepted
- Date: 2026-10-02
- Clarifies: ADR 0002 and SPEC sections 8, 11, 18-20

## Decision

`ExamType -> ExamScheme -> SchemePhase -> SchemeRule` stores normalized configuration.
Each rule identifies a subject, question type, expected count and marking values. Phase rules
determine subject membership, phase order, offsets, duration and whether that phase locks after
its end. Negative marks store a nonnegative penalty magnitude; unanswered marks are explicitly zero.
Subjects and question types use stable enumerations; their distributions and marks are data.

`MockTest` binds permanently to one scheme. `MockPhase` copies the configured phases and is
validated against them. SPEC section 11 freezes schemes at the first mock reference; we use
that stricter boundary, including DRAFT mocks, rather than delaying the freeze until scheduling.
All referenced scheme fields and child rules are immutable. Create a new version for changes.

The owner creates schemes/phases/rules before creating a mock. Django Admin generates mock
phases on creation. Draft papers allow manual authoring and append-only CSV/XLSX imports.
Partial batches are useful alongside manual authoring: previews warn when counts are incomplete,
but every imported row must be valid and cannot exceed the configured distribution. Full-paper
validation gates registration, scheduling and going live. Question numbers are global per mock,
contiguous from 1 through the configured total. MCQs have four options A-D and exactly one answer;
numericals have no options, one accepted decimal value and an explicit default tolerance of zero.

All paper content and schedule edits are restricted to DRAFT, which avoids invalidating an
already operational paper. Transitions are centralized and lock the mock row. Model writes lock
the owning scheme/mock row; public bulk updates/inserts are rejected because they skip guards.
The private import writer uses validated bulk inserts only while holding the mock lock, inside
one transaction. The lifecycle service similarly locks question status in one validated update.
These are application boundaries, not defenses against a database administrator issuing raw SQL.

Import preview performs no writes. Its signed, 30-minute confirmation token binds the parsed
rows to the owner and mock. Commit verifies the signature and binding, locks the mock, revalidates
against the current paper, and inserts all rows/options atomically. Replays fail on duplicate
questions. Templates are downloadable in both formats. Files are limited to 2 MiB, 1000 rows,
16 columns and 20 MiB expanded XLSX; only one sheet is allowed, and formulas/error cells are rejected.
Markdown/LaTeX are stored as text and escaped in previews; this phase does not render student content.

Before opening registration/scheduling, the owner must record a per-mock official-rule review:
actor, time, source URL/edition/date and notes. Seed data comes only from SPEC and makes no
claim to be authoritative for 2027. Revalidation is a human attestation, not an automated web check.

After CLOSED and before RESULTS_PUBLISHED, the owner may correct answer keys through the dedicated
service/Admin form. Append-only audit records contain actor, timestamp, field, old/new values and
reason. Content/marks cannot change through this action. Score recalculation is deferred to Phase 5.
The CLOSED -> RESULTS_PUBLISHED transition is reserved and deliberately refuses publication until
Phase 5 provides verified calculations and answer-key publication checks. `result_release_at`
remains an earliest-publication guard, never an automatic trigger.

## Consequences

- Complete 75/150-question papers are validated with prefetched questions, options and rule maps.
- All new HTTP workflows are owner-only, CSRF-protected Django Admin views. No student exam API,
  public paper endpoint, purchasing, attempts, scoring, worker or dashboard feature is added.
- The database enforces unique versions, phase order, question numbers, option labels/order,
  schedule inequalities and basic marks/answer shape. Cross-table/completeness checks live in
  model validation and services; direct SQL and migrations require separate operational control.
- An invalid scheme cannot create a mock through Admin. Operational papers are intentionally
  read-only; cancel and create a corrected mock instead of changing a scheduled paper in place.
