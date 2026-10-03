# ADR 0012: Production configuration and launch evidence

Date: 2026-10-03. Status: accepted within Phase 8 hardening scope.

Keep the existing monolith, Google ID-token authentication, TEST-only Razorpay boundary,
fixed timing and PostgreSQL authority. No schema change, worker or product feature.

Production startup requires explicit safe hosts/origins, independent signing secrets,
Google and TEST payment configuration, PostgreSQL TLS and an acknowledged trusted proxy.
API cookies stay host-only. Same-site frontend/API custom domains are recommended;
cross-site cookie behavior remains a real-device launch gate. Google login now requires
CSRF, like refresh/logout; the browser bootstraps CSRF before exchanging its ID token.
Refresh/revocation serialize on the existing user row to prevent concurrent token reuse.

WhiteNoise serves immutable collected Admin assets; local production media writes are
disabled. Existing question image URLs must use durable owner-controlled HTTPS storage.
Gunicorn is the Linux runtime; its initial 3-process/4-thread sizing is a measurement
candidate. Deployment selection and purchases remain with the owner; no deployment exists.

Separate process-local auth/read/payment/start throttles supplement the preserved exam
save allowance. Provider edge controls and verified client-IP handling are still needed.
Payload-free correlation/event logs, generic production API errors and no-store API/Admin
responses improve operations without logging answer content, tokens or student PII.

Owner `reconcile-payment` fetches provider payment/order state and invokes the existing
transactional reconciler. It never creates charges, captures or refunds; no student API
is added. Local signature/idempotency/race tests are not real checkout/webhook evidence.

Paid launch requires an actual deployed, credentialed JEE/CET rehearsal, actual devices,
load/soak, managed restore, capture/webhook verification and approved legal copy. Test
success cannot replace any of these. Live keys continue to be rejected with no enable flag.
See DEPLOYMENT, REHEARSAL, MOCK_DAY_RUNBOOK and LAUNCH_CHECKLIST for owner steps.
