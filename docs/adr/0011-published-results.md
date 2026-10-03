# ADR 0011: Deterministic scoring and atomic, manually published results

Status: Accepted for Phase 5

## Authority and arithmetic

Only backend-accepted StudentResponse records count. Immutable scheme rules and
question marks are the scoring authority; there is no exam-name scoring branch.
Numerical answers use finite Decimal arithmetic with precision 50 and inclusive
absolute tolerance: `abs(response - key) <= tolerance`, without operand rounding.
Rank is competition rank (`1 + count(score > own score)`), never speed-based.
Mock Percentile is `100 * count(score <= own score) / eligible_count`, rounded to
two decimal places using ROUND_HALF_UP. It is not official exam normalization.

## Eligibility

SUBMITTED attempts all qualify, including blank submissions. AUTO_SUBMITTED
attempts qualify when at least one saved response row exists (a saved blank visit
counts, but scores unattempted). INVALID, zero-response AUTO_SUBMITTED and users
who never started do not qualify. One central function defines this rule.

## Batch model and operations

An explicit owner key verification creates a ResultCalculationRun with immutable
private paper/key/configuration and audit-revision snapshots. Calculation locks
the mock, then its attempts, reconciles expired attempts and snapshots accepted
responses. Immutable ResultCalculationEntry rows retain every generation. Result
is one current published row per Attempt. Input and output SHA-256 digests bind a
complete generation; reads never combine mutable answer keys with old scores.

All calculation/publication/correction operations serialize on the same MockTest
row in PostgreSQL. Duplicate calculation and publication are idempotent for the
same generation. Batch writes and status changes are atomic. Queries are bounded
batch reads/writes, not per-student/per-question database loops. There is no worker,
Redis or Celery. Synchronous operations require deployment timeout sizing.

Publication is a separate owner operation, only for CLOSED mocks after the global
exam end and result_release_at. It rechecks key validity, revision, reconciled
inputs, complete membership and output integrity before publishing all rows and
the mock together. Reaching result_release_at never publishes automatically.

## Corrections and privacy

An audited answer-key correction invalidates any verified/draft generation. Admin
must verify and calculate again. After publication, Admin must explicitly withdraw
the current generation with a reason (actor/time retained). This returns the mock
to CLOSED and hides results/review/history/leaderboard. Audited correction, new
verification, calculation, inspection and publication follow. Old snapshots remain
for audit; the new Result pointers switch atomically. No silent replacement.

Student report/review reads are scoped to the authenticated student and require a
published run and mock. Leaderboards expose only rank, masked name, score and Mock
Percentile. Review is built from immutable published snapshots with an explicit
allowlist, never internal digests/audits. Responses are private/no-store. Requests
already reading a published immutable generation may finish during withdrawal;
withdrawal cannot revoke data already delivered. Subsequent requests are gated.

Previous score means the latest earlier-starting published mock of the same
ExamType for that student, not purchase time or a draft calculation. No analytics
or Phase 6 dashboard is introduced.
