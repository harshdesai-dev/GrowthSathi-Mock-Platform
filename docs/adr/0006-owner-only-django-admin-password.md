# ADR 0006: Owner-only Django Admin password

- Status: Accepted
- Date: 2026-10-02
- Supersedes: The no-usable-password bootstrap detail in ADR 0005 for the sole platform owner only

## Context

Student authentication remains Google-only. Phase 2, however, requires the platform owner to use
Django Admin operationally for mocks, questions, imports, and validation. The Phase 1 owner role
could be marked staff/superuser but deliberately had an unusable password, leaving no interactive
Admin authentication path.

## Decision

Allow Django's standard password authentication only at `/admin/` for the explicitly bootstrapped
platform owner. A trusted management command may set or reset a password only when the supplied
email and Google `sub` identify the same active user and that user is already both staff and
superuser.

The command prompts without echo by default. Automation may name an environment variable that
contains the password; plaintext command-line password arguments are not supported. Django's
password validators and `set_password()` hashing are mandatory.

Student users continue to receive unusable passwords. No password login, signup, reset, session,
or token endpoint is added to the student product. DRF product APIs continue to accept JWT
authentication only, so a Django password session cannot authenticate to `/api/v1/` endpoints.
The owner's Google `sub` remains their durable external identity.

## Consequences

- The owner can use the standard Django Admin without adding a second public authentication flow.
- Protecting and rotating the internal Admin password becomes an operational responsibility.
- Compromise of the password grants owner-level Admin access, so production must enforce HTTPS and
  use a strong unique password stored in an approved password manager.
- Additional administrators, delegated roles, public password recovery, and team management remain
  out of scope.
