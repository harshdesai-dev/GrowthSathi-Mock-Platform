# Live exam operations — Phase 4

Read SPEC.md, EXAM_ADMINISTRATION.md and PAYMENTS.md first. Phase 4 adds an exam
engine, not results. Owner-reviewed official rules are required before **each mock**;
the seeded schemes remain unverified baseline templates until that review.

## Before the exam

1. Review current official JEE Main / MHT-CET PCM rules, choose/create the correct
   versioned scheme, author and validate the complete paper, and record rules attestation.
2. Verify the global UTC start/end and IST display. JEE: one 180-minute phase. CET:
   PC minutes 0–90, Mathematics minutes 90–180, using the global start.
3. Finish the registration/payment workflow and transition the mock to SCHEDULED.
   A purchased mock still in REGISTRATION_OPEN cannot start. A valid scheduled mock
   activates to LIVE on its first eligible start; existing manual LIVE transition works.
4. Use always-on application/database infrastructure, synchronized host clocks, secure
   HTTPS cookies, tested backups, a sufficiently sized connection pool and active monitoring.
   Do not run a paid mock on sleeping/free-tier services.
5. Run the pre-launch manual checklist below on the actual deployment. Local benchmark
   results are not a substitute for hosting/network measurements.

## Student flow

Purchased access on `/dashboard` links to `/mocks/:mockId/instructions`. Instructions
show fixed IST times and the local/server-save distinction. Before opening, availability
is refreshed every 30 seconds. Starting late never adds time. An existing attempt links
to `/exam/:attemptId`; repeating start returns that attempt, not a second one.

The exam shows current-phase content only, subject navigation, answer/review/visit palette,
clear, previous, save-and-next, timer, sync state and final submission. On small screens the
palette is a keyboard-accessible modal. No results or scoring appear after submission.

All mutations persist in IndexedDB before sending. Device-only changes are **not accepted
answers**. Do not clear browser/site storage, use private browsing, change accounts or
switch devices during an exam. A browser/OS can evict local data; server acknowledgements
are the durable authority. Invalid partial decimal drafts remain editable locally but
cannot be sent until completed. On quota/storage failure stop and recover browser storage.

On connection loss, keep working within the current phase; queued changes retry when
connection returns. If the phase ends before server acceptance, those queued changes
cannot count. After refresh/reopen the server restores the global state and the local queue
is merged before showing the paper. A fresh offline page must reconnect to restore its
authenticated paper. If authentication has expired completely, sign in in another tab,
return to the original attempt and press Retry sync.

## API contract

All routes are under `/api/v1`, require JWT authentication, check ownership, and are
private/no-store. Responses use the established API error envelope.

| Method | Route | Behavior |
| --- | --- | --- |
| GET | `/mocks/:mockId/exam-info/` | Purchased instructions, global schedule, existing attempt |
| POST | `/mocks/:mockId/start/` | Empty body; access/validity check, create-or-resume |
| GET | `/attempts/:id/` | Reconciled state, current-phase student responses |
| GET | `/attempts/:id/paper/` | Current-phase allowlisted questions/options and state |
| POST | `/attempts/:id/heartbeat/` | Empty body; server time, current phase, state |
| PUT | `/attempts/:id/responses/:questionId/` | Validated, versioned response |
| POST | `/attempts/:id/submit/` | Empty body; final-phase submission, idempotent terminal state |

Response mutation body: `selected_option` (UUID or null), `numeric_answer` (decimal text
or empty), `marked_for_review` (boolean), `mutation_version` (positive safe integer).
Unknown fields, client times, JSON-number numeric answers and oversized versions are rejected.
Blank responses represent visits/clears. At most 12 integer / 8 decimal digits are accepted;
scientific notation, NaN, fractions and comma notation are not accepted.

409 codes distinguish not-started, closed, wrong phase, invalid response and stale mutation.
403 access denial never creates entitlement. An attempt owned by another student is 404.
Final submission contains no answers. A response blocked by submission/deadline cannot be
rescued by retrying its version. Retry an unknown submission outcome to read its terminal state.

## Deadline reconciliation / incident handling

Run from `backend` with the target environment configured:

```bash
python manage.py reconcile_expired_attempts --batch-size 200
```

No daemon/Redis/Celery is necessary for correctness. The command also invalidates unfinished
attempts on cancelled mocks. It scans in bounded batches and locks each row briefly. It is
safe to run repeatedly or concurrently with exam traffic. Submission time for expiry is
the fixed global end, even if reconciliation runs later. IN_PROGRESS rows can physically
lag while no request/command observes them; every write still checks the actual deadline.

Owner Admin exposes read-only Attempts and StudentResponses. Attempt inspection reconciles
first. Do not bypass domain services with direct SQL or manually reopen attempts. Preserve
transaction history and investigate IDs in logs; never paste credentials or response bodies
into logs/support channels. For platform outages, follow the approved refund policy; this
phase provides neither time extensions nor retrospective offline-answer acceptance.

`result_release_at` remains an earliest-publication guard. No scoring or publication action
is added. Phase 5 will implement result behavior; do not attempt to calculate it here.

## Before paid launch: manual checks

- Actual Android Chrome and iOS Safari: small screens, keyboard/decimal input, diagram and
  formula rendering, modal focus, sleep/wake, low memory and private/storage-full behavior.
- Real 30-second and five-minute network outages, including crossing CET and exam end.
  Automated duration tests use accelerated timers; they do not prove carrier/OS behavior.
- Force-close/reopen the browser with its real profile, and restart all application workers
  during active saves. Confirm only acknowledged/persisted responses survive.
- Real Google expiry/refresh/re-authentication, cookie/CSRF/SameSite on production domains.
- Actual 500-student multi-process deployment load, CPU/DB/connection monitoring, mixed
  heartbeats and autosaves, image hosting, TLS, network jitter and long-duration soak.
- Owner-approved legal copy, Razorpay test smoke, official-rule revalidation and launch approval
  are still required. Live payments remain disabled by Phase 3 safeguards.
