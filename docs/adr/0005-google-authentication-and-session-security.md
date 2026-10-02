# ADR 0005: Google authentication and session security

- Status: Accepted
- Date: 2026-10-02

## Context

Phase 1 requires Google-only student authentication, a durable local identity, first-login
onboarding, and browser sessions that do not expose a long-lived credential to JavaScript. Email
cannot be the durable Google identity because a verified Google account email may change.

## Decision

The React application uses Google Identity Services to obtain an ID token. Django verifies the
token signature, audience, issuer, expiry, and verified-email claim independently with Google's
supported verification library. The verified Google `sub` is the durable external identity.

The local user has a UUID primary key and unique `google_sub` and email fields. A repeated login
for the same `sub` may update that user's Google name and an unclaimed verified email. If the new
email belongs to another local user, or a different `sub` presents an existing email, login fails
with an identity conflict. Accounts are never silently merged. Inactive users are rejected.

The API issues:

- a five-minute access JWT returned in the response body and held only in React memory;
- a seven-day rotating refresh JWT in an HttpOnly cookie scoped to `/api/v1/auth/`;
- blacklist-backed revocation of rotated and logged-out refresh tokens.

Refresh and logout are CSRF-protected. A public same-origin/CORS-restricted CSRF bootstrap endpoint
returns Django's CSRF token and sets its cookie before a cookie-authenticated mutation. Production
forces Secure cookies. SameSite and cookie-domain values remain configurable so deployment can use
same-site subdomains or an explicitly reviewed cross-site setup.

The frontend restores a session by obtaining a CSRF token, rotating the refresh cookie, and then
calling `/auth/me/` with the new access token. It does not use `localStorage` or `sessionStorage`
for authentication tokens.

Initial platform-owner status is assigned by a management command that requires both the verified
email and Google `sub`, refuses mismatched identities, and creates no usable password. This phase
does not add a password login or a separate admin authentication product.

## Consequences

- Compromise of an access token has a short exposure window, while refresh credentials remain
  inaccessible to frontend JavaScript.
- Refresh rotation and the blacklist add database writes and retain token revocation records.
- Production must configure the same Google OAuth web client ID in Django and the frontend build.
- Cross-origin deployments must deliberately align CORS, trusted origins, SameSite, Secure, and
  cookie-domain settings; arbitrary unrelated frontend/API sites are not a safe default.
- Administrators need the Google `sub` for the explicit bootstrap command. No identity is inferred
  or merged by email alone.
