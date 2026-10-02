# ADR 0004 Refund policy

- Status: Accepted
- Date: 2026-10-02

## Decision

A payment is eligible for refund only for:

- a cancelled mock
- a duplicate verified payment
- a confirmed GrowthSathi platform failure

A no-show, late arrival, or student-side device or internet issue after the exam starts is not eligible.

Refund execution must be authorized by Admin, associated with the original verified payment and recorded with a reason and gateway reference. The detailed operational flow will be implemented with commerce in Phase 3.

## Consequences

- Legal policy copy must match this decision before production payments are enabled.
- Frontend claims never directly change payment or access state.
