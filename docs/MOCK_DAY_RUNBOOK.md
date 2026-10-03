# Mock-day runbook

Owner: sole bootstrapped GrowthSathi Admin. All times below are relative to the
configured mock start; student displays use IST. Server/database timestamps remain UTC.
No paid mock proceeds until [LAUNCH_CHECKLIST.md](LAUNCH_CHECKLIST.md) is signed off.
Deployment/backup commands: [DEPLOYMENT.md](DEPLOYMENT.md). Rehearsal: [REHEARSAL.md](REHEARSAL.md).

## T-24h: freeze and verify

- Recheck current official NTA/CET Cell rules, record URL/edition/date and review notes
  on each mock. Seeds are not proof of current rules. Create a new scheme if required.
- Validate complete 75/150-question papers against the configured scheme, preview diagrams,
  independently check answer keys/explanations, fixed start/end and earliest release.
- Check offer amounts, exact combo contents, paid entitlement samples and sales windows.
- Take a DB backup, verify its checksum and the most recent successful isolated restore.
- Check Google/Razorpay/provider status and account capture/webhook configuration.
- Freeze feature/config/schema/dependency changes for **24 hours before start until all
  attempts are reconciled and the post-exam backup completes**. Disable automatic deploys.
- Record known-good deployment IDs, owner/support contact route, monitoring view, backup
  reference and incident record location. Do not introduce a new notification system.

## T-2h: operational smoke

- HTTPS liveness and readiness return 200 without cached responses; HTTP redirects to HTTPS.
- Check DB connections, storage, backup status, clock synchronization, CPU/RAM and worker count.
- Perform real Google login, onboarding/return login, reload and logout on Android Chrome
  and desktop Chrome using controlled accounts. Check exact cookie origin/SameSite behavior.
- Verify frontend deep links, API URL, current assets and official Google button.
- Confirm a known paid TEST order and correct access grant. Check no unexplained CREATED,
  old PENDING or `review_required` orders. Do not create real charges as an unapproved check.
- Confirm Razorpay webhook delivery and capture evidence from rehearsal; legal/live gate
  remains separate. Check test/live account mode deliberately, never infer it from UI color.
- Open owner Admin, confirm the scheduled mocks are SCHEDULED with correct fixed times;
  REGISTRATION_OPEN alone does not authorize exam start.
- Start monitoring and verify alert delivery. Have the incident/recovery guide available.

## T-30m: final go/no-go

- Stop all deployments and configuration changes, including provider auto-deploy and DB maintenance.
- Confirm readiness, no payment/access backlog, paper validation and owner availability.
- Check the launch checklist: unresolved critical/high blocker means postpone paid launch.
- Emergency fix only with explicit owner incident decision, focused verification and a
  tested rollback. Never rush a feature or paper edit into an operational mock.

## LIVE

- Watch starts, 4xx reason/429 rates, 5xx, save latency, health, CPU/RAM and DB connections/locks.
- Compare expected participation with starts; investigate patterns without reading answer payloads.
- Students use one browser/device. Keep the existing tab and local queue during reconnect;
  do not instruct them to clear storage. Server clock and global phase/end deadlines remain final.
- No deployment, key rotation, scoring or manual SQL while students are taking the mock.
- Record incident timestamps and request IDs. Never request tokens, passwords, UPI PIN or card data.

## POST-EXAM

1. Confirm server time is after the common end. Close the mock via Mock operations.
2. Run `python manage.py reconcile_expired_attempts --batch-size 200`; rerun to confirm
   idempotency. Inspect submitted/auto-submitted/invalid counts and exclusions.
3. Take a post-exam backup before result operations. Record backup timestamp/checksum.
4. Independently verify the answer key; use **Result operations -> Verify answer key / prepare run**
   and record notes. Calculate the selected run and inspect participant counts, score samples,
   ties, ranks and Mock Percentiles. Do not change result rows by hand.
5. Publish only after earliest release time and inspection. Verify report, leaderboard masking,
   answer review and previous same-exam comparison from a controlled student session.
6. Back up the published state. Reconcile payment exceptions and document the incident outcome.

## Incident actions

### A. Backend unavailable during exam

Confirm from two networks; inspect readiness/liveness and provider events. Check worker health,
recent releases and CPU/memory, then restore the known-good compatible backend if a release
caused failure. Preserve PostgreSQL and queues. Verify reconnect/save/accepted response state
before resuming normal operations. Do not extend individual clocks or bypass server deadlines.
Owner records platform impact and decides cancellation/refund through approved policy.

### B. Database unavailable

Check managed DB status, network/TLS, connection limits and storage. Stop heavy admin/report
jobs. Use provider recovery/failover; do not switch to SQLite. Readiness must stay 503 until
queries work. After recovery, verify recent accepted responses and reconcile attempts. A stale
backup restore may lose accepted answers/payments: follow DEPLOYMENT recovery approval and
reconciliation steps before a cutover; never restore a pre-exam dump onto the live database.

### C. Razorpay unavailable

Stop inviting new payments; deactivate affected offers if needed. Keep existing paid exam access
working. Preserve uncertain CREATED receipts; do not create another order blindly or promise
payment failed because a request timed out. Check provider receipt/capture, use `link-order` if
needed, then `reconcile-payment`, and replay signed webhooks. Investigate duplicate captures.

### D. Google login unavailable

Check Google status, browser origin errors, exact client IDs and frontend release values.
Existing local refresh sessions may continue; avoid logging those students out. Restore a bad
configuration only with validation. Do not add student passwords, accept unverified tokens or
bypass onboarding. Record students affected before fixed start for owner incident handling.

### E. Student cannot access a purchased mock

Use local order UUID/request ID and verified provider reference, not screenshots alone.
Inspect order owner, amount/currency, gateway order, CAPTURED payment and ACTIVE grant to the
correct mock; check cancellation/refund/revocation and profile completion. If delivery was missed:

```sh
python manage.py commerce_operation reconcile-payment ORDER_UUID --owner OWNER_EMAIL --reference pay_PROVIDER_ID
```

The command fetches provider payment/order state and reuses the idempotent reconciler; it never
charges/captures money. For an unlinked receipt use `link-order` first with the verified order ID.
Recheck Admin and the student's dashboard. Do not fabricate a paid flag/grant with SQL. A revoked
or refunded grant must not reappear from replay; investigate its recorded owner reason.

### F. Question/answer-key error

Before registration: fix DRAFT content and revalidate. After the paper is operational, do not
edit content, marks or timings in place. Record impact for owner cancellation/policy decision.
For a key error after close use **Correct answer key with audit reason**, then verify/calculate
a new generation. Published results first require explicit withdrawal with a reason.

### G. Result publication error

Inspect run/mock status after timeout before retrying. Failed transactions must not have partial
published results. Withdraw an incorrect published generation through Result operations, record
reason, audit correction, reverify/recalculate, inspect all changed ranks/percentiles, republish.
Old immutable runs remain for audit. Already downloaded answers cannot be recalled.

### H. Deployment rollback

Use DEPLOYMENT's previous immutable frontend/backend release steps. Check API compatibility,
cookies, health and preserved response versions. Keep the current DB; do not reverse migrations
blindly. Capture the failure and verification in the incident record before lifting the freeze.

## Incident record

Record: IST and UTC start/end, affected mock IDs, deployment IDs, symptoms/request IDs, accepted
data affected, provider evidence, actions/operator, verification, refund/cancellation decision,
follow-up owner/date. Store privately. Exclude answer contents and secrets from general logs.
