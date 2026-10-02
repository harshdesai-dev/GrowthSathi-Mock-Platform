# GrowthSathi Mock Platform

_Codex Implementation Specification - v1.1_

## 1. Product objective

Build a production-ready, recurring paid competitive mock-test platform under the GrowthSathi brand for:

- JEE Main
- MHT-CET PCM

This is one permanent platform, not an 11 October-specific website.

Initial planned mock dates:

- 11 October 2026
- 25 October 2026
- afterwards approximately two mocks per month

Exact future dates and times must always be configurable by Admin.

Primary device: mobile.

Also fully support:

- laptop
- desktop
- tablet

The system must prioritize:

exam reliability > correctness > mobile usability > design polish > additional features.

## 2. Product scope

Pricing

| Product          | Price |
| ---------------- | ----- |
| JEE Main mock    | ₹29   |
| MHT-CET PCM mock | ₹29   |
| JEE + CET combo  | ₹50   |

Prices must be stored in the backend in paise, never trusted from frontend values.

Admin should be able to change prices for future mocks without code changes.

## 3. Authentication

Student authentication:

Google Sign-In only.

Do NOT build:

- email/password authentication
- phone OTP authentication
- separate login/signup systems

Google provides:

- name
- email
- Google account identifier

For first login, show onboarding.

Collect:

- Full name — prefilled
- Email — prefilled/read-only
- Phone number
- Class:
  - 11th
  - 12th
  - Dropper
- Preparing for:
  - JEE
  - MHT-CET
  - Both

For V1, phone numbers must be valid Indian mobile numbers. Normalize stored values to `+91XXXXXXXXXX`. Phone numbers are not unique.

Returning users go directly to Dashboard.

## 4. Roles

There are only two roles.

Student

Can:

- sign in
- complete profile
- browse mocks
- purchase CET/JEE/combo
- access purchased mocks
- attempt exam
- view released results
- view leaderboard
- review answers
- view previous mocks

Admin

Only the platform owner has Admin privileges.

Admin can:

- create mocks
- edit schedules
- configure exam rules
- add/edit questions
- import questions
- validate question papers
- manage pricing
- inspect students
- inspect orders/payments
- inspect attempts
- inspect submissions
- calculate/publish results
- view basic revenue and mock statistics

Do not build multi-admin teams, staff roles or institute management.

## 5. Explicitly out of scope

Codex must NOT invent or implement any of the following unless SPEC.md is later changed:

- NEET
- MHT-CET PCB/Biology
- AI tutor
- AI analysis
- chapter analysis
- weak-topic detection
- subject-wise performance dashboard
- study plans
- video lectures
- notes
- study resources
- friends
- student social network
- local community
- discussion forums
- doubt solving
- subscriptions
- streak systems
- gamification
- achievements
- referral systems
- SMS alerts
- WhatsApp alerts
- heavy anti-cheating
- webcam monitoring
- tab-switch monitoring
- mobile app

These appeared in some AI-generated reference images but are not product requirements.

## 6. Core student journey

Landing Page

    ↓

Continue with Google

    ↓

First login?

    ├── Yes → Complete Profile

    └── No

    ↓

Student Dashboard

    ↓

View Upcoming Mock

    ↓

Choose:

JEE ₹29 / CET ₹29 / Combo ₹50

    ↓

Payment

    ↓

Purchase confirmed

    ↓

Mock unlocked

    ↓

Countdown / Waiting screen

    ↓

Exam Instructions

    ↓

Scheduled Start Time

    ↓

Start Mock

    ↓

Attempt Exam

    ↓

Autosave

    ↓

Submit / Auto-submit

    ↓

Result unavailable until test closes

    ↓

Results Published

    ↓

Score + Rank + Mock Percentile + Report Card

    ↓

Leaderboard / Answer Review

    ↓

Return for next mock

## 7. Fixed-time exam behaviour

Students do not receive their own personal three-hour window.

Mocks have global:

starts_at

ends_at

result_release_at

`result_release_at` is an earliest-publication guard. It does not automatically publish results. Admin publishes results manually only after the answer key and calculations have been verified.

All stored internally in UTC.

UI displays times in:

Asia/Kolkata / IST

A student cannot begin before starts_at.

If a student starts late:

they receive only the remaining time until the common test/phase deadline.

Do not give them a new full-duration timer.

The server clock is authoritative.

Never trust the client's system clock.

## 8. Exam architecture

Do not create separate hard-coded JEE and CET applications.

Use:

Exam Type

    ↓

Mock Test

    ↓

Mock Phase(s)

    ↓

Questions

    ↓

Attempt

    ↓

Responses

    ↓

Result

This allows future exam-rule changes without rebuilding the application.

Exam schemes must be versioned and configurable. A mock references an immutable exam-scheme version so later rule changes do not alter historical or scheduled mocks.

Before every mock, Admin must revalidate the configured JEE Main or MHT-CET PCM scheme against the latest official rules. Any required change creates a new scheme version.

## 9. Initial exam configurations

JEE Main

The following is the current seed baseline. Revalidate it against the latest official JEE Main rules before every mock and create a new scheme version when rules change:

Duration: 180 minutes

Subjects:

- Physics

- Chemistry

- Mathematics

Questions:

25 / subject

75 total

Per subject:

20 MCQ

5 Numerical

MCQ:

Correct +4

Incorrect -1

Unanswered 0

Numerical:

Correct +4

Incorrect -1

Unanswered 0

Maximum score: 300

Navigation:

All three subjects available throughout test.

Numerical questions must support:

- integer response
- configurable accepted answer
- configurable tolerance if required later

Do not expose answers to frontend during exam.

## 10. MHT-CET PCM configuration

The following is the current seed baseline. Revalidate it against the latest official MHT-CET PCM rules before every mock and create a new scheme version when rules change:

Total duration: 180 minutes

Total questions: 150

Maximum marks: 200

Physics:

50 questions

1 mark each

Chemistry:

50 questions

1 mark each

Mathematics:

50 questions

2 marks each

Negative marking:

None

Phases:

PHASE 1

0–90 minutes

Physics + Chemistry

At 90 minutes:

Phase automatically locks.

PHASE 2

90–180 minutes

Mathematics

Once Phase 1 closes:

- student cannot return to Physics
- student cannot return to Chemistry
- existing responses remain saved
- Mathematics automatically becomes active

Phase handling must be enforced by backend, not only frontend.

## 11. Data model

Use UUID primary keys for primary business entities.

User

id

email

google_sub

first_name

last_name

is_active

is_staff

created_at

updated_at

Email unique.

Google subject ID unique.

StudentProfile

id

user

full_name

phone

class_level

target_exam

onboarding_completed

created_at

updated_at

Enums:

class_level:

11

12

DROPPER

target_exam:

JEE

CET

BOTH

ExamType

id

code

name

active

created_at

Initial:

JEE_MAIN

MHT_CET_PCM

MockTest

id

exam_type

title

slug

description

starts_at

ends_at

result_release_at

price_paise

status

instructions_md

created_at

updated_at

Statuses:

DRAFT

REGISTRATION_OPEN

SCHEDULED

LIVE

CLOSED

RESULTS_PUBLISHED

CANCELLED

MockPhase

id

mock_test

name

order

start_offset_minutes

duration_minutes

sequence_locked

Example CET:

Phase 1

start_offset = 0

duration = 90

Phase 2

start_offset = 90

duration = 90

JEE:

Phase 1

start_offset = 0

duration = 180

Question

id

mock_test

phase

subject

question_number

question_type

question_text_md

question_image_url

positive_marks

negative_marks

correct_numeric_answer

numeric_tolerance

explanation_md

status

created_at

updated_at

Types:

MCQ_SINGLE

NUMERICAL

Question text and explanations must support:

- Markdown
- mathematical notation
- LaTeX/KaTeX
- optional images

QuestionOption

For MCQs:

id

question

label

option_text_md

option_image_url

is_correct

order

ExamScheme

id

exam_type

version

name

active

created_at

An ExamScheme is immutable after a MockTest references it. Versioned phase, subject, question-count, question-type and marking rules must be configurable and available to mock validation.

MockOffer

id

name

offer_type

price_paise

status

created_at

updated_at

Offer type:

JEE

CET

COMBO

MockOfferItem

id

offer

mock_test

A JEE or CET offer links exactly one matching mock. A COMBO offer links exactly one JEE Main mock and exactly one MHT-CET PCM mock. Enforce this in backend validation and database-safe service logic.

Order

id

student

total_amount_paise

offer

status

gateway_order_id

created_at

paid_at

Statuses:

CREATED

PENDING

PAID

FAILED

REFUNDED

OrderItem

id

order

mock_test

price_paise_snapshot

Combo creates two OrderItems:

JEE mock

CET mock

Total charged:

₹50.

Order and OrderItem prices are snapshots calculated from the selected MockOffer by the backend. Frontend amounts are never accepted as authoritative.

Payment

id

order

gateway

gateway_payment_id

gateway_signature

amount_paise

status

metadata_json

created_at

Never store:

- card number
- CVV
- UPI PIN

Attempt

id

student

mock_test

started_at

submitted_at

last_heartbeat_at

status

created_at

Statuses:

IN_PROGRESS

SUBMITTED

AUTO_SUBMITTED

INVALID

Database constraint:

UNIQUE(student, mock_test)

One purchased mock = maximum one attempt.

StudentResponse

id

attempt

question

selected_option

numeric_answer

marked_for_review

first_visited_at

updated_at

Constraint:

UNIQUE(attempt, question)

This table also lets us distinguish:

- not visited
- visited but unanswered
- answered
- marked for review

Result

id

attempt

score

correct_count

incorrect_count

attempted_count

unattempted_count

rank

percentile

published_at

created_at

No subject-analysis fields required.

## 12. Ranking rules

Ranking is per mock test, not overall lifetime ranking.

Valid participants are:

- every SUBMITTED attempt
- an AUTO_SUBMITTED attempt only when it contains at least one successfully saved response

Exclude INVALID attempts, users who never started, and empty AUTO_SUBMITTED attempts.

Use:

rank = 1 + number of valid results having score > current score

Therefore identical scores receive identical ranks.

Do not use completion speed as a tie breaker in V1.

## 13. Percentile

This platform does not claim to reproduce official NTA/CET percentile normalization.

Call it:

Mock Percentile

Use:

percentile =

100 ×

(number of valid participants with score <= student's score)

/ total valid participants

Round to two decimals.

UI must never label this as:

Official JEE Percentile

or:

Official CET Percentile

## 14. Improvement calculation

Find student's most recent earlier published result for the same exam type.

Display:

Previous score

Current score

Difference

Examples:

126 → 151

+25 marks

or

151 → 143

-8 marks

Do not add AI interpretations.

## 15. Report card

Private to authenticated student.

Display only:

Student name

Exam

Mock title/date

Score

Maximum score

Rank

Mock Percentile

Correct

Incorrect

Attempted

Unattempted

Previous score

Score difference

Actions:

Review Answers

View Leaderboard

Do not display:

- chapter analytics
- weak areas
- AI recommendations
- subject performance graphs

## 16. Leaderboard

Leaderboard is per MockTest.

Display:

Rank

Masked student name

Score

Mock Percentile

Name format:

Harsh D.

Rahul P.

Sneha M.

Never expose:

- full surname
- email
- phone
- Google ID

## 17. Answer review

Available only when:

mock.status == RESULTS_PUBLISHED

Each question displays:

Question

Student answer

Correct answer

Correct / Incorrect / Unattempted

Marks received

Explanation

Answers and explanations must never be present in the exam payload before result publication.

## 18. Question import

Support both:

Manual creation

and

CSV / XLSX import

Provide a downloadable import template.

Columns:

question_number

phase

subject

question_type

question_text_md

question_image_url

option_a

option_b

option_c

option_d

correct_option

numeric_answer

numeric_tolerance

positive_marks

negative_marks

explanation_md

Before importing:

- parse file
- validate every row
- show preview
- show errors with row numbers
- require confirmation
- insert atomically

Validation includes:

- missing question
- duplicate question number
- invalid subject
- invalid phase
- incorrect question type
- missing correct option
- multiple correct options
- missing numerical answer
- invalid marks
- incorrect expected question count

Never partially import a failed paper.

## 19. Mock validation

Admin should see:

VALID / INVALID

before publishing.

Validate:

- expected number of questions
- expected subject distribution
- question numbering
- marks
- negative marks
- phases
- correct answers
- explanations
- schedule
- result release time

Do not allow an invalid mock to become LIVE.

## 20. Question locking

Once a mock becomes LIVE:

Question content and answer keys should become locked.

After exam closes but before results are published:

Admin may fix an incorrect answer key.

If this happens:

- record the change
- recalculate affected scores
- calculate ranks again
- only then publish results

## 21. Payment integration

Default gateway:

Razorpay

All payment logic lives in backend.

Flow:

Student chooses offer

↓

Frontend requests order

↓

Backend calculates amount

↓

Backend creates Razorpay Order

↓

Frontend launches Razorpay Checkout

↓

Payment completed

↓

Backend verifies signature

↓

Webhook confirms payment

↓

Order status = PAID

↓

OrderItems grant mock access

Never grant access based only on frontend success callback.

Webhook handling must be idempotent.

Refund eligibility is limited to:

- a cancelled mock
- a duplicate verified payment
- a confirmed GrowthSathi platform failure

No refund is due for a no-show, late arrival, or student-side device or internet issue after the exam has started. Refund processing must be auditable and must not be inferred from an unverified frontend claim.

## 22. Exam access control

Start Attempt endpoint checks:

Authenticated?

Profile complete?

Mock purchased?

Payment paid?

Already attempted?

Mock started?

Mock ended?

Only then create attempt.

## 23. Autosave architecture

Critical requirement.

When student selects/changes an answer:

Browser

Immediately save locally to:

IndexedDB

Then asynchronously sync to API.

If network request fails:

- keep unsynced response locally
- retry automatically
- use exponential backoff

Student should not lose answers due to:

- refresh
- browser crash
- temporary connection loss

API uses upsert, making requests idempotent.

## 24. Heartbeat

While exam is open:

Frontend sends heartbeat approximately every 30 seconds.

Backend responds:

{

"server_time": "...",

"mock_end_at": "...",

"active_phase": "...",

"phase_end_at": "..."

}

Timer corrects itself using server time.

## 25. Exam timer

Never implement timer as:

180 minutes since page load

Correct:

remaining_time =

server_phase_end_at - server_current_time

Therefore refresh does not reset timer.

## 26. Submission

Manual Submit:

- flush pending answers
- confirm with student
- backend locks attempt
- no further responses accepted
- attempt becomes SUBMITTED

At deadline:

Backend rejects further modifications.

Any unfinished attempt is treated as:

AUTO_SUBMITTED

using all successfully saved responses.

## 27. Exam payload security

When exam begins, frontend may receive:

- question IDs
- question content
- options
- images
- marks
- phase information

It must NOT receive:

- correct answer
- explanation
- hidden answer metadata

Do not rely on CSS/JavaScript to hide answers.

Backend must omit them entirely.

## 28. Exam UI

Desktop

Structure:

Top bar

- GrowthSathi

- Exam name

- Timer

Subject/phase navigation

Main question area

Right question palette

Bottom actions:

Previous

Clear Response

Mark for Review

Save & Next

Submit Test

Mobile

Use:

- sticky timer header
- large readable question text
- full-width options
- sticky navigation buttons
- question palette inside bottom sheet/drawer
- no tiny clickable controls

Primary student experience is mobile.

## 29. UI/UX source of truth

Use the approved reference design language only:

Black / charcoal base

Lime green accents

Silver / white typography

Premium exam-tech feel

High contrast

Minimal clutter

Strong score/rank numbers

Soft green glows used sparingly

Rounded cards

Subtle borders

Use real GrowthSathi logo.

Create central design tokens.

Suggested starting palette:

--bg-primary: #070A08;

--bg-surface: #0D120F;

--bg-elevated: #121815;

--brand-lime: #B7FF00;

--brand-lime-hover: #A4E600;

--text-primary: #F5F7F5;

--text-secondary: #A7B0AA;

--text-muted: #717B75;

--border: #27302A;

--success: #59D987;

--danger: #FF5B5B;

--warning: #FFC857;

Adjust lime to match logo asset visually.

Do not switch to:

- blue SaaS
- pastel UI
- white dashboard theme

## 30. Design references

Repository:

/docs/design-references/

Store:

Growthsathi_main_logo.png

landing.png

login.png

student-dashboard.png

exam-interface.png

result-report-card.png

Use the actual approved GrowthSathi logo asset in the product. Do not crop or reconstruct it from the reference screenshots.

These references define:

- visual tone
- hierarchy
- spacing direction
- branding

They do not define product functionality.

Ignore incorrect text/features that may appear inside AI-generated reference images.

Do not reproduce screenshot-only people, mountain artwork, slogans, analytics, gamification, or other out-of-scope material. The screenshots are visual references only.

SPEC.md always overrides screenshots.

## 31. Frontend routes

/

/auth

/onboarding

/mocks

/mocks/:slug

/checkout

/dashboard

/waiting/:mockId

/instructions/:mockId

/exam/:attemptId

/results/:mockId

/leaderboard/:mockId

/review/:mockId

/history

/privacy

/terms

/refund-policy

Admin can initially use:

/admin/

plus a lightweight branded admin console later if required.

## 32. Backend APIs

Prefix:

/api/v1/

Authentication

POST /auth/google/

POST /auth/refresh/

POST /auth/logout/

GET /auth/me/

Profile

GET /profile/

PATCH /profile/

Mocks

GET /mocks/

GET /mocks/:id/

GET /mocks/:id/access/

Orders

POST /orders/

GET /orders/:id/

POST /payments/verify/

POST /payments/webhook/

Attempts

POST /mocks/:id/start/

GET /attempts/:id/

POST /attempts/:id/heartbeat/

PUT /attempts/:id/responses/:questionId/

POST /attempts/:id/submit/

Results

GET /mocks/:id/result/

GET /mocks/:id/leaderboard/

GET /mocks/:id/review/

GET /results/history/

Admin

POST /admin/mocks/

PATCH /admin/mocks/:id/

POST /admin/mocks/:id/validate/

POST /admin/mocks/:id/publish/

POST /admin/questions/import/preview/

POST /admin/questions/import/commit/

GET /admin/students/

GET /admin/orders/

GET /admin/payments/

GET /admin/attempts/

## 33. Recommended technology stack

Frontend

React

TypeScript

Vite

Tailwind CSS

React Router

TanStack Query

React Hook Form

Zod

Zustand

KaTeX

IndexedDB helper library

Avoid unnecessary UI frameworks that make the branding generic.

Build custom GrowthSathi components.

Backend

Python

Django

Django REST Framework

PostgreSQL

django-cors-headers

SimpleJWT

google-auth

drf-spectacular

Razorpay SDK

openpyxl

psycopg

Gunicorn

pytest / pytest-django

Use current stable supported versions at implementation time.

## 34. Repository structure

growthsathi-mock-platform/

├── frontend/

│ ├── src/

│ │ ├── api/

│ │ ├── assets/

│ │ ├── components/

│ │ │ ├── brand/

│ │ │ ├── common/

│ │ │ ├── exam/

│ │ │ └── results/

│ │ ├── features/

│ │ │ ├── auth/

│ │ │ ├── profile/

│ │ │ ├── mocks/

│ │ │ ├── payments/

│ │ │ ├── attempts/

│ │ │ └── results/

│ │ ├── layouts/

│ │ ├── pages/

│ │ ├── routes/

│ │ ├── stores/

│ │ ├── styles/

│ │ ├── types/

│ │ └── utils/

│

├── backend/

│ ├── config/

│ ├── apps/

│ │ ├── common/

│ │ ├── accounts/

│ │ ├── exams/

│ │ ├── commerce/

│ │ ├── attempts/

│ │ └── results/

│ ├── tests/

│ └── manage.py

│

├── docs/

│ ├── SPEC.md

│ ├── adr/

│ └── design-references/

│

├── infra/

├── .github/workflows/

├── compose.yaml

│

├── .env.example

├── README.md

└── .gitignore

## 35. Security requirements

Required:

- HTTPS production only
- secure authentication
- short-lived access tokens
- protected refresh mechanism
- strict CORS
- Admin-only endpoints
- Razorpay signature validation
- webhook validation
- API throttling
- input validation
- sanitize rendered Markdown
- prevent XSS
- never expose correct answers early
- never trust frontend pricing
- never trust frontend timer
- never expose student PII
- PostgreSQL backups

All secrets through environment variables.

Never commit secrets.

## 36. Environment variables

Example:

DJANGO_SECRET_KEY=

DJANGO_DEBUG=

DATABASE_URL=

FRONTEND_URL=

GOOGLE_CLIENT_ID=

GOOGLE_CLIENT_SECRET=

RAZORPAY_KEY_ID=

RAZORPAY_KEY_SECRET=

RAZORPAY_WEBHOOK_SECRET=

JWT_SECRET=

MEDIA_STORAGE_CONFIG=

Provide .env.example.

Never provide actual secrets.

## 37. Deployment

Recommended:

Frontend

Vercel

Backend

Render or Railway

Database

Managed PostgreSQL

Do not run the paid live mock on infrastructure that sleeps when idle.

Backend must be always-on during examination windows.

Store DB timestamps in UTC.

Display India time in IST.

## 38. Performance target

Design initial architecture for approximately:

up to 500 simultaneous students

without redesign.

Avoid an API request for every page/question load.

At attempt start:

fetch the paper structure/question content once.

Then question navigation occurs primarily client-side.

Only send:

- response saves
- heartbeat
- submission

Lazy-load large question images.

For the initial architecture, PostgreSQL and Django are the source of truth. Do not introduce Redis or Celery in Phase 0. Deadline rules must be enforced lazily and authoritatively by backend services on every relevant request. Keep deadline and reconciliation interfaces modular so a worker can be added later only if load or reliability testing demonstrates the need.

## 39. Reliability testing

Before paid launch simulate:

- page refresh
- browser close/reopen
- 30-second internet loss
- five-minute internet loss
- late exam start
- timer expiry
- CET 90-minute transition
- duplicate submit
- duplicate payment webhook
- server restart
- failed answer sync
- accidental double click
- expired JWT during test

Student answers must survive wherever realistically possible.

## 40. Core acceptance tests

The product is not ready until all of these pass.

Authentication

Google user can sign in.

New user sees onboarding.

Returning user does not see onboarding again.

Payment

₹29 JEE payment unlocks JEE only.

₹29 CET payment unlocks CET only.

₹50 combo unlocks both.

Frontend cannot manipulate price.

Duplicate webhook does not create duplicate purchase.

Exam access

Unpaid student cannot start.

Paid student cannot start early.

Student cannot create second attempt.

Late student receives only remaining time.

JEE scoring

Correct MCQ → +4.

Incorrect MCQ → −1.

Correct numerical → +4.

Incorrect numerical → −1.

Unattempted → 0.

CET scoring

Physics correct → +1.

Chemistry correct → +1.

Mathematics correct → +2.

Incorrect answer → 0.

No negative score.

CET phases

Before 90 minutes:

Physics/Chemistry accessible.

Mathematics unavailable.

After 90 minutes:

Physics/Chemistry locked.

Mathematics accessible.

Autosave

Answer remains after refresh.

Answer remains after reconnect.

Timer does not reset.

Submission

Manual submission locks responses.

Expired exam auto-submits.

No modification after submission.

Results

Results inaccessible before publication.

Correct counts calculated.

Rank calculated correctly.

Mock percentile calculated correctly.

Leaderboard masks surnames.

Student only sees their private report card.

Review

Correct answers hidden before result publication.

Correct answers available after publication.

Explanation displayed after publication.

## 41. Admin launch workflow

Before every mock:

Create Mock

↓

Set Date/Time

↓

Set Price

↓

Import Questions

↓

Review Questions

↓

Run Mock Validation

↓

Fix Errors

↓

Open Registration

↓

Collect Payments

↓

Monitor Live Test

↓

Close Test

↓

Verify Answer Key

↓

Calculate Results

↓

Publish Results

## 42. UI screens

Public:

Landing

Google Login

Mock Details/Pricing

Student:

Dashboard

Checkout

Countdown

Instructions

Exam

Report Card

Leaderboard

Answer Review

Previous Mocks

Admin:

Dashboard

Mock Management

Question Management / Import

Students / Payments / Attempts

## 43. Build phases

Phase 0 — Foundation

Create:

- monorepo
- frontend
- backend
- PostgreSQL configuration
- environment files
- CI basics
- design tokens
- shared error handling
- README
- health endpoint

No product features yet.

Commit.

Phase 1 — Authentication

Build:

- Google authentication
- JWT/session handling
- StudentProfile
- onboarding
- protected routes

Tests.

Commit.

Phase 2 — Exam administration

Build:

- ExamType
- MockTest
- MockPhase
- Questions
- Options
- Django Admin
- CSV/XLSX import
- validation system

Seed JEE and CET configs.

Tests.

Commit.

Phase 3 — Registration and payment

Build:

- mock listing
- mock details
- JEE/CET/combo selection
- Razorpay test mode
- Order
- Payment
- OrderItem
- MockOffer
- MockOfferItem
- access control

Tests.

Commit.

Phase 4 — Exam engine

Build:

- countdown
- instructions
- start attempt
- question interface
- server timer
- JEE navigation
- CET phase transition
- response saving
- IndexedDB
- retry queue
- heartbeat
- submit
- auto-submit

This is the highest-risk phase.

Extensive tests required.

Commit.

Phase 5 — Results

Build:

- scoring service
- rank service
- percentile service
- result publication
- report card
- leaderboard
- answer review
- previous-score comparison

Tests.

Commit.

Phase 6 — Student dashboard

Build:

- upcoming mock
- purchased access
- countdown
- previous results
- latest score
- rank
- percentile
- improvement

Do not add analytics outside specification.

Commit.

Phase 7 — UI polish

Match approved GrowthSathi references.

Test:

360px

390px

430px

768px

1024px

1440px

Accessibility and contrast check.

Commit.

Phase 8 — Production hardening

Run:

- backend tests
- frontend unit tests
- end-to-end tests
- payment sandbox tests
- load tests
- security review
- migrations
- production deployment
- backup verification
- evaluate whether measured reliability or load results require a background worker

Then run a private end-to-end rehearsal before allowing paid students.

## 44. Codex working rules

Codex must:

- Treat SPEC.md as authoritative.
- Never invent product features.
- Work one implementation phase at a time.
- Run relevant tests before declaring a phase complete.
- Do not silently change architecture.
- Do not hard-code exam dates/prices.
- Do not hard-code exam rules into UI components.
- Use migrations for schema changes.
- Keep code modular and typed.
- Update README when setup changes.
- Maintain .env.example.
- Preserve existing working functionality when adding features.
- Report:
  - files changed
  - migrations created
  - tests run
  - test results
  - unresolved risks
- Stop and ask before making a product decision not covered by this specification.

## 45. Definition of Done

The platform is ready for its first paid public mock only when:

Google login works

Payment works

Access control works

Question paper validated

Timer tested

Autosave tested

Reconnect tested

CET section switch tested

JEE scoring tested

CET scoring tested

Auto-submit tested

Results gating tested

Ranking tested

Percentile tested

Answer review tested

Mobile interface tested

Backend load tested

Production DB backed up

Production backend always-on

One full rehearsal successfully completed

## 46. Primary product principle

When choosing between:

more features

and

a reliable exam

always choose:

a reliable exam.
