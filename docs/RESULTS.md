# Phase 5: scoring and published result operations

## Phase 6 dashboard read model

`GET /api/v1/dashboard/` is an authenticated, `private, no-store` student-only read model.
It composes the existing paid-access, exam-info/start eligibility, attempt, and published-result
services; it does not calculate access, timing, scoring, ranking, or publication state in the
browser. It returns public mock schedule cards with the student's access/attempt state, the
server time used for countdown display, latest published result and comparison, and the existing
private published-result history. It never exposes payment details, other students, unpublished
scores, answer keys, or review content.

Dashboard actions only link into existing instruction/exam and published result flows. The actual
start remains the existing server-authorized start endpoint, so a client clock cannot enable a
new attempt.

See [ADR 0011](adr/0011-published-results.md) and [verification](PHASE5_VERIFICATION.md).
There is no automatic publication, worker, Redis or Celery. No Phase 6 dashboard or
subject analytics is included. The existing live exam payload remains key-free.

## Owner checklist

1. End the global exam window and transition the mock to **CLOSED** in Mock operations.
2. Open **Result operations** from the MockTest list/detail. Reconcile expired attempts.
   This locks this mock's attempts and converts stale IN_PROGRESS rows to AUTO_SUBMITTED
   at the original global end, never accepting device-only or late answers.
3. Select **Verify answer key / prepare run**. Enter what was checked against the key,
   check confirmation, and submit. This is a distinct attestation from official exam
   rules verification performed before each mock. The complete valid paper and key
   are captured privately with a revision hash and correction audit IDs.
4. Select that generation and **Calculate selected run**. Wait for success, then inspect
   the run and linked calculation entries. Check participant count, excluded attempts,
   score/counts, ranks and Mock Percentiles. Errors do not produce a partial published
   batch. VERIFIED → CALCULATING → COMPLETE occurs in one transaction.
5. After `result_release_at`, select the inspected COMPLETE generation and **Publish**.
   Confirmation is mandatory. The service checks closed/end/release gates, current key,
   snapshot integrity, inputs, membership and output digest again. All Result rows,
   generation and MockTest status publish atomically. Duplicate publication is harmless.

Only active staff superusers may perform operations. Runs/entries/results are readonly
in Admin and guarded against casual ORM save/update/delete. These are application
guards, not a substitute for restricting database credentials. Do not repair result
rows with SQL or edit scores by hand. No public calculation or publication endpoint exists.

## Corrections and retry

Before publication: use the existing Question **Correct answer key with audit reason**.
It invalidates VERIFIED/COMPLETE generations under the same mock lock. Verify the key
again, calculate a new generation, inspect and publish. Old entries remain for audit.

After publication: first select the PUBLISHED generation and **Withdraw**, with a
specific reason. Actor/time/reason are retained and the mock returns to CLOSED.
All subsequent student result/history/leaderboard/review requests are unavailable.
Then correct the key through the audited Question operation, verify, calculate,
inspect and publish the new generation. Existing Result rows switch generation in
one transaction; one Result per Attempt is retained. Excluded old rows remain hidden.
Withdrawal cannot revoke a previously delivered report or an already-in-flight read.

A semantic scoring failure records FAILED with an error and no entries; verify again
to create a replacement run after resolving the cause. Unexpected database/process
failure rolls the transaction back; retry the same run. A caller timing out must
inspect run status before retrying. No uncommitted CALCULATING state is visible.
Different result operations and audited key correction serialize on the MockTest row;
attempt rows are locked before snapshotting responses. PostgreSQL is required for
these concurrency guarantees. SQLite tests alone do not establish lock behavior.

## Exact scoring, eligibility and comparison

- Configured Question positive/negative marks and SchemeRule unanswered marks are
  authoritative. No scoring branch depends on an exam name. Negative scores are valid.
- Decimal text only; numerical correctness is inclusive `abs(response-key) <= tolerance`
  at precision 50. No operand rounding or float equality. Blank responses are unattempted.
- SUBMITTED always qualifies; AUTO_SUBMITTED needs at least one saved response row.
  A saved blank visit qualifies but scores unattempted. INVALID, zero-response auto
  submissions and never-started purchases do not qualify. Admin sees exclusions/reasons.
- Competition rank is `1 + count(greater scores)`; ties produce 1,2,2,4, with no speed rule.
- **Mock Percentile** is `100 * count(score <= own score) / eligible_count`, ROUND_HALF_UP
  to two decimals. One participant gets 100.00; an empty batch has no percentile rows.
- Previous score is the student's most recent strictly earlier-starting PUBLISHED
  result for the same ExamType. Drafts/withdrawn/different-exam results are ignored.
  First published result shows no comparison. Tied start dates are not earlier mocks.

## APIs and UI

All endpoints require the existing authenticated JWT session and send `private, no-store`.
The frontend uses the existing single-flight short-lived-token refresh mechanism.
No review/answer-key data is written to IndexedDB or localStorage.

| GET endpoint | Published response |
| --- | --- |
| `/api/v1/mocks/{id}/result/` | Own report with score, maximum, counts, rank, Mock Percentile and previous comparison |
| `/api/v1/mocks/{id}/leaderboard/` | Rank, masked name (`Harsh D.`), score and Mock Percentile only |
| `/api/v1/mocks/{id}/review/` | Own question/answer/outcome/marks/explanation from the published immutable snapshots |
| `/api/v1/results/history/` | Own published mock summaries, most recent mock date first |

Unpublished/withdrawn results return 409 `result_unavailable`; no own attempt returns
404; no authentication returns 401. Excluded attempts get a clear unranked reason,
not a made-up rank. A student parameter cannot change private record ownership.
Leaderboard is available to authenticated students only after publication. Private
serializers do not expose digests, audit events, payment data or Google identities.

Routes: `/results`, `/results/{mockId}`, `/results/{mockId}/leaderboard`,
`/results/{mockId}/review`. Entry links are added to the existing account placeholder
and terminal exam screen only. The actual logo/design tokens are reused; no screenshot
artwork, prediction, report export or analytics is added. Math reuses the existing
safe Markdown/KaTeX renderer (no raw HTML/trusted commands; HTTPS images only).

## Deployment limitations

Runs retain full paper/response snapshots, so storage grows with generations. Plan
backup/retention and protect sensitive snapshots. History and leaderboard are unpaginated
for the current mock scale; measure multi-year/high-participant scale before expansion.
Calculation/publication are synchronous and hold row locks; configure request and
database timeouts above measured batch durations on the deployment host. Results
may be in-flight during withdrawal but never combine generations. Actual Admin
key verification quality remains an operational responsibility. All live-exam
[launch checks](LIVE_EXAMS.md) still apply; local benchmarks are not launch approval.
