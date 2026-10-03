# ADR 0009 Reliable live exam engine

- Status: Accepted within the approved Phase 4 scope
- Date: 2026-10-03
- Extends: ADRs 0001, 0002, 0003, 0005, 0007, 0008

## Scope

Implement only SPEC Phase 4. No scoring, correctness calculation, Result, rank,
percentile, leaderboard, review, report card, analytics, AI, NEET, Redis or Celery.
The existing versioned schemes and per-mock owner attestation remain authoritative;
this implementation does not claim that baseline seeds are newly verified official rules.

## Backend authority and lifecycle

`apps.attempts` is a domain module in the existing Django modular monolith. PostgreSQL
holds all accepted responses and lifecycle state. It does not depend on heartbeats,
browser presence or a scheduler to enforce a deadline.

An active, paid MockAccessGrant and completed onboarding are required to start.
Start locks the purchasing student row, consistent with commerce refund/revocation
lock ordering. A unique `(student, mock_test)` constraint provides the final duplicate
start guard. Validated/attested SCHEDULED papers can become LIVE lazily on the first
authorized start; REGISTRATION_OPEN alone does not allow starting. Full paper validity
is derived at each new start, preserving Phase 2's validation boundary. Paper authoring
and schedules are already immutable outside DRAFT.

An existing attempt resumes without changing its original start. Terminal attempts
never reopen. IN_PROGRESS becomes SUBMITTED on manual final-phase submission,
AUTO_SUBMITTED at the global end, or INVALID when its mock is cancelled. Empty
AUTO_SUBMITTED attempts are retained; their later ranking exclusion belongs to Phase 5.

Save and submit lock **only the attempt row**, not the shared mock row. Server time
is checked after acquiring that lock, and again immediately before saving a response.
The server decision immediately before persistence is the acceptance point; request
arrival, browser timestamps and HTTP response arrival are not deadlines. A saved answer
can commit before the connection drops; the retry protocol handles that lost acknowledgement.
No grace period, client timestamp or device-only queue can authorize a late response.

Reconciliation must commit even when the requested late mutation returns a 409.
Services therefore return domain errors from their transaction and raise them only
after commit. Submission/save lock ordering defines a single winner: a save committed
first is included, while a save acquiring the lock after submission is rejected.

## Global timing and CET

Use timezone-aware Django server UTC time and the stored global schedule. All deployed
application hosts require synchronized clocks. Intervals are half-open `[start, end)`.
Versioned MockPhase offsets/durations derive windows from **mock start**, never attempt
start. Baseline JEE is one 180-minute phase; CET is 90-minute Physics/Chemistry followed
by 90-minute Mathematics. Final submission is allowed only in the final phase.

Only current-phase questions and current-phase responses are delivered. Future CET
questions are withheld. The server rejects closed/future-phase writes even if a browser
retains an earlier payload. GET/state, heartbeat, submit, late save, Admin inspection
and `reconcile_expired_attempts` apply the same lifecycle rules. A physically stale
IN_PROGRESS row is never permission to save past its deadline.

## Secure student contract

`student_payload.py` owns explicit non-model allowlist serializers, separate from Admin
authoring. Its question/option queries omit key fields. No correct-option flag, numeric
key, tolerance, explanation, scoring fields or key audit enters the live contract.
Owner checks scope every attempt operation. Student responses are only the student's
chosen values, never correctness. All exam responses use `Cache-Control: private, no-store`.
Question content is parsed as Markdown/math with no raw HTML, no clickable links,
HTTPS-only images, no referrer and KaTeX `trust: false` with expansion/size limits.
Owner-authored question text must itself be checked for accidentally included solutions.

## Mutation protocol and durable browser state

StudentResponse stores decimal **text**, option identity, review mark, first visit and
a per-question integer version in the JavaScript-safe range 1..2^53-1. Decimal parsing
is finite, exact, canonical and consistent with existing 20,8 key precision; no float
is used and no correctness is calculated. The current scheme has no separate configurable
student numeric-format rule. An officially required change to that format must update
the versioned scheme contract, not silently reinterpret submissions.

- Higher version replaces the response after validation.
- Equal version and equal canonical content acknowledges an idempotent retry.
- Older version, or equal version with different content, returns `stale_mutation` 409.
- Clear, visit and review changes are versioned too.

IndexedDB `growthsathi-exam-v1` stores one coalesced entry per user/attempt/question.
Each edit commits locally before network transmission. A readwrite transaction allocates
`max(local_version, known_server_version)+1`, serializing tabs. Acknowledgement clears
only the matching queued version; it cannot erase an edit made during a request.
Paper and hydrated local entries are published together to prevent blank visit recovery
from overwriting a pending answer. Only token-free student responses are persisted.

Different devices do not share a local counter. Conflicting writes are blocked and the
server value is displayed; the local draft is retained for diagnosis. The student must
explicitly edit again. The client never automatically increases an old queue's version
to defeat a server rejection. Use one tab/device operationally. Closed-phase queues are
retained as unaccepted data and never replayed into a later phase.

## Connectivity, time display and submission

The existing AuthProvider wraps every exam request, deduplicates refresh calls, obtains
CSRF, uses the HttpOnly refresh cookie, then retries once after 401. No exam token is
placed in localStorage/IndexedDB. Fetch timeouts are 15 seconds, except the expensive
start request at 60 seconds. A failed refresh does not delete the queue. If the refresh
session itself expires, sign in in another tab and retry the existing attempt.

The serial save loop coalesces pending updates, retries transient failures with capped
exponential backoff and jitter (roughly 1..30 seconds), and retries on online, pageshow,
visibility and manual recovery. Heartbeats run about every 30 seconds; heartbeat DB
writes are similarly limited. A lost heartbeat does not invalidate an attempt.

Display time uses a server sample plus monotonic `performance.now()`, conservatively
including request round-trip duration. `Date.now()` does not drive countdowns. A local
boundary disables input and asks the server; it cannot advance phases or set terminal
state. Wake/reopen requires resynchronization. A completely offline fresh page cannot
authenticate or obtain a new authoritative paper; durable answers survive until reconnect.

Manual submit awaits local writes and attempts to flush the queue. If sync fails, the
student can cancel, retry, or explicitly submit server-saved answers only. The server
never accepts a submission body containing unsaved answers. Terminal UI shows only
submission status and response counts, with no answer review/results.

## Operations and measured consequences

The management command is a bounded, keyset-scanned set of short row transactions,
idempotent under concurrent callers. It can be invoked by an external scheduler later;
no worker infrastructure is added. Admin uses the same reconciliation before inspection.
The application throttle is a process-local abuse guard, not distributed rate limiting.
Logs contain lifecycle/rejection identifiers, not answer values or credentials.

The 500-student loopback benchmark passed integrity, but single-process start validation
was slow (p99 24.08s). Autosave p99 was 1.85..2.52s at 100 concurrent HTTP clients.
This is evidence for production process sizing/profiling, not a paid-launch capacity
certification. Do not weaken paper validation or introduce Redis/Celery to conceal it.
See the complete methodology and limits in PHASE4_VERIFICATION.md.

## Implementation references

- [IndexedDB transaction lifetime and idb usage](https://github.com/jakearchibald/idb)
- [react-markdown security guidance](https://github.com/remarkjs/react-markdown#security)
- [KaTeX security controls](https://katex.org/docs/security)
- [Playwright managed web server](https://playwright.dev/docs/test-webserver)
- [Waitress server configuration](https://docs.pylonsproject.org/projects/waitress/en/stable/arguments.html)
