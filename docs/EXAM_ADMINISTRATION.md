# Phase 2: Exam administration

## Setup

Use Python 3.13 and PostgreSQL 18 with the existing `DATABASE_URL` setup in README. From `backend`:

```powershell
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python manage.py migrate
.venv/Scripts/python manage.py seed_exam_schemes
```

The only new runtime dependencies are `openpyxl` (XLSX) and `defusedxml` (safe XML parsing).
The seed command is idempotent and never overwrites an existing scheme. An existing invalid
baseline makes it fail with a message, rather than silently repairing/changing historical rules.

Seeds are `JEE_MAIN` and `MHT_CET_PCM`, each with version `spec-v1.1-baseline`, effective baseline
date 2026-10-02. They encode SPEC sections 9-10 only. **They are not verified official 2027 rules.**
Before each real mock, check the latest official NTA JEE Main and Maharashtra CET Cell materials,
including duration, distribution, marking and phase navigation. Create a new scheme version if
anything changes. Record the official URL, edition/date and review notes for that specific mock.

## Owner workflow

1. Sign into `/admin/` using the owner account configured in README.
2. Inspect the seeded scheme, or create a new ExamScheme. Enter version, source notes, totals and
   effective date. Add SchemePhases with contiguous order/offsets. Open each SchemePhase to add
   its subject/type/count/marking rules. The ExamScheme list shows derived VALID/INVALID status.
3. Create a DRAFT MockTest with the matching exam type and scheme, a unique slug, UTC schedule,
   earliest result-release time and paise price. Admin generates its phases from the scheme.
   Duration must match the scheme before becoming operational. Price is metadata only in Phase 2.
4. Author questions manually with inline A-D options, or follow **Import questions**. Both
   methods store Markdown/LaTeX as source text. Question and option image URLs are optional;
   no storage credentials are needed to store URLs and no URL is fetched by the importer.
5. Use **Validate / verify rules / transition** to run full-paper validation and see each error.
6. Record the latest official-rule verification through the same page. This stores the owner,
   timestamp and source notes; entering notes is a human attestation, not an automated rule check.
7. Only a valid paper with recorded verification can enter REGISTRATION_OPEN or SCHEDULED.
   DRAFT can also be cancelled; REGISTRATION_OPEN can schedule/cancel; SCHEDULED can go live/cancel;
   LIVE can close. These are manual operations, with no clock scheduler or student attempts.
8. After CLOSED, the Question page exposes **Correct answer key with audit reason**. Supply only
   the matching answer type and a reason. Changes are append-only audit events. Content and marks
   stay frozen. RESULTS_PUBLISHED is reserved and blocked until Phase 5 implements calculations
   and publication checks, even after `result_release_at`.

Per authoritative SPEC section 11, a scheme and its rules become immutable on the **first mock
reference**, including DRAFT. Finish scheme configuration first. Mock-to-scheme bindings cannot
change later. All paper/schedule edits are restricted to DRAFT; published/operational papers do
not become invalid through ordinary edits. Live questions receive LOCKED status.

Draft questions may be incomplete while authoring, but the Admin inline form always requires
four valid A-D options and exactly one correct MCQ answer. READY questions require explanations.
Numericals require an accepted decimal value, nonnegative tolerance (default **0**) and no options.
Question numbers are global within a mock, starting at 1. The finished paper must be contiguous.

## Import templates and confirmation

From a mock's Import page, download the CSV or XLSX template. Template routes require owner access:

- `/admin/exams/mocktest/template/csv/`
- `/admin/exams/mocktest/template/xlsx/`

Use these exact headers and order:

```text
question_number,phase,subject,question_type,question_text_md,question_image_url,option_a,option_b,option_c,option_d,correct_option,numeric_answer,numeric_tolerance,positive_marks,negative_marks,explanation_md
```

| Column | Meaning |
| --- | --- |
| question_number | Positive integer, unique within the mock, at most the scheme total |
| phase | The generated phase's 1-based order (JEE: 1; CET: 1 or 2) |
| subject | PHYSICS, CHEMISTRY or MATHEMATICS, allowed in that phase |
| question_type | MCQ_SINGLE or NUMERICAL, allowed by that subject's rule |
| question_text_md | Required Markdown/LaTeX source text |
| question_image_url | Optional valid URL; no remote fetch during import |
| option_a through option_d | Four required MCQ text values; empty for numericals |
| correct_option | Exactly one uppercase A/B/C/D for MCQ; empty for numericals |
| numeric_answer | Required finite decimal for numericals; empty for MCQ |
| numeric_tolerance | Nonnegative decimal; blank explicitly defaults to 0; MCQ must be 0/blank |
| positive_marks | Must equal the scheme rule |
| negative_marks | Nonnegative penalty magnitude: JEE baseline 1, CET baseline 0 |
| explanation_md | Required Markdown/LaTeX source text |

Upload -> parse -> validate every row -> escaped preview with original row numbers -> explicitly
check confirmation -> atomic insert. Preview does not create questions, options or staging records.
Its signed token expires after 30 minutes and is bound to the owner and mock. Commit revalidates
against current database state under a mock row lock. An invalid row, changed state, duplicate
question, replay or insert failure rolls back the whole batch.

Imports append; they never overwrite an existing question. Partial batches are accepted with an
incomplete-paper warning, permitting manual/imported content to be combined. Excess subject/type
counts are errors. A partial paper cannot pass the operational transition gate. Duplicate question
numbers and identical subject/text/image content within the batch or existing paper are rejected.

CSV must be UTF-8 (BOM accepted). XLSX must have one worksheet and no formulas/error cells. Limits:
2 MiB upload, 1000 data rows, 16 columns, 20 MiB expanded XLSX. Blank rows are skipped, but malformed
nonblank rows are errors. Formula-like CSV strings are stored/displayed as text, never evaluated.
Quote CSV fields containing commas or newlines using normal CSV quoting. Preserve LaTeX backslashes.

## Validation and data boundaries

The validator derives validity from scheme structure, phases/order/duration, subjects and type
counts, contiguous numbering, answer completeness, four MCQ options/one correct option, numerical
shape/tolerance, explanations, marks/penalties, maximum marks and timestamps. It uses prefetched
rule maps and options to avoid per-question reads on full papers.

Database constraints cover unique scheme versions, phase order, mock question numbers, option
label/order, timestamp ordering and core numeric/answer shape. Model guards and transactional
services enforce cross-table consistency and immutability. Public ORM bulk writes are rejected.
Private validated import insertion and lifecycle status locking are the only bulk-write paths.
Direct database administrators can bypass application guards; restrict those credentials.

There are no new REST/student APIs. Custom views live inside Django Admin and require an active
staff superuser. POST actions use Django CSRF protection. Students cannot access paper content or
answer keys through these workflows. No scoring, payments, offers, attempts or workers are included.

## Verification

From `backend`, using the configured virtualenv:

```powershell
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m ruff format --check .
.venv/Scripts/python -m pytest -p no:cacheprovider
.venv/Scripts/python manage.py check
.venv/Scripts/python manage.py check --deploy --settings=config.settings.production
.venv/Scripts/python manage.py makemigrations --check --dry-run
.venv/Scripts/python manage.py spectacular --validate --file openapi-check.yml
```

The production check requires the documented production environment variables (secret key,
database URL, Google client ID and JWT key). The local suite defaults to SQLite when `DATABASE_URL`
is absent. Set `DATABASE_URL` to a dedicated PostgreSQL test database and rerun the entire suite;
the PostgreSQL-only concurrent-import test then runs instead of being skipped. The test role needs
permission to create/drop pytest's temporary database. Do not point verification at production.

Verify fresh migration with an empty dedicated database and `manage.py migrate --noinput`.
Verify upgrade using a separate database at the committed Phase 1.5 schema, then apply the same
command and inspect `showmigrations exams`. No earlier committed migration was edited.

From `frontend`: `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm test`,
`npm run build`. From the repository root: `git diff --check`.
