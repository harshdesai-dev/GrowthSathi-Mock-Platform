# ADR 0001 System architecture

- Status: Accepted
- Date: 2026-10-02

## Context

GrowthSathi needs a reliable mobile-first paid mock-test platform for JEE Main and MHT-CET PCM. The initial target is approximately 500 simultaneous students. Exam timing, response durability, payments and answer secrecy are more important than adding features.

## Decision

Use a monorepo containing:

- a React and TypeScript single-page application built with Vite and Tailwind CSS
- a Django and Django REST Framework modular monolith
- PostgreSQL as the authoritative business datastore
- an OpenAPI contract for the versioned `/api/v1/` API
- S3-compatible media storage when question images are introduced

Backend modules are separated into `common`, `accounts`, `exams`, `commerce`, `attempts`, and `results`. This is code-level separation within one deployable backend, not distributed services.

The frontend uses feature modules. TanStack Query owns remote state. Zustand may own transient exam-interface state in Phase 4. IndexedDB will own the durable local response queue in Phase 4.

All persistent timestamps use UTC. Student-facing times display in Asia/Kolkata.

## Consequences

- Transactions and database constraints can protect payment, attempt and publication invariants.
- One backend deployment is simpler to rehearse and operate than microservices.
- Modules must communicate through explicit service interfaces to avoid a tightly coupled monolith.
- No screenshot-only artwork or product behavior becomes part of the architecture.
