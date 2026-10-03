# Architecture decision records

Architecture decisions are numbered and immutable after acceptance. If a decision changes, add a superseding ADR instead of silently rewriting the system architecture.

- [ADR 0001](0001-system-architecture.md) - modular monolith and SPA
- [ADR 0002](0002-exam-schemes-offers-and-results.md) - versioned schemes, explicit offers and result rules
- [ADR 0003](0003-deadline-enforcement-without-worker.md) - PostgreSQL/Django source of truth without a Phase 0 worker
- [ADR 0004](0004-refund-policy.md) - V1 refund eligibility
- [ADR 0005](0005-google-authentication-and-session-security.md) - Google identity and secure browser sessions
- [ADR 0006](0006-owner-only-django-admin-password.md) - internal owner-only Django Admin password
- [ADR 0007](0007-exam-authoring-and-import-boundaries.md) - versioned exam authoring and atomic imports
- [ADR 0008](0008-offers-payments-and-access.md) - explicit offers, verified sandbox payments and access entitlements
- [ADR 0009](0009-reliable-live-exam-engine.md) - server-timed attempts, phase locks, durable responses and recovery
