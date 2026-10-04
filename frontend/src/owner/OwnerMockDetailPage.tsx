import { useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { price } from "../api/commerce";
import { useAuth } from "../auth/auth-context";
import {
  ownerMockDetailApi,
  validateOwnerPaperApi,
  verifyOwnerRulesApi,
  type OwnerPaperValidationResult,
  type OwnerMockDetail,
  type OwnerMockStatus,
} from "./api";

const statusLabels: Record<OwnerMockStatus, string> = {
  DRAFT: "Draft",
  REGISTRATION_OPEN: "Registration open",
  SCHEDULED: "Scheduled",
  LIVE: "Live",
  CLOSED: "Closed",
  RESULTS_PUBLISHED: "Results published",
  CANCELLED: "Cancelled",
};

const dateTimeFormatter = new Intl.DateTimeFormat("en-IN", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Asia/Kolkata",
});

type DetailState =
  | { status: "loading" }
  | { status: "success"; mockId: string; mock: OwnerMockDetail }
  | { status: "error"; mockId: string };

type PaperValidationState =
  | { status: "loading"; mockId: string }
  | { status: "success"; mockId: string; result: OwnerPaperValidationResult }
  | { status: "error"; mockId: string };

type RulesVerificationState =
  | { status: "saving"; mockId: string }
  | { status: "error"; mockId: string; message: string }
  | { status: "saved"; mockId: string };

function dateTime(value: string) {
  return `${dateTimeFormatter.format(new Date(value))} IST`;
}

export function OwnerMockDetailPage() {
  const { mockId = "" } = useParams();
  const { withAccess } = useAuth();
  const [retryKey, setRetryKey] = useState(0);
  const [state, setState] = useState<DetailState>({ status: "loading" });
  const [paperValidation, setPaperValidation] =
    useState<PaperValidationState | null>(null);
  const [rulesDraft, setRulesDraft] = useState<{
    mockId: string;
    notes: string;
  } | null>(null);
  const [confirmedMockId, setConfirmedMockId] = useState<string | null>(null);
  const [rulesOperation, setRulesOperation] =
    useState<RulesVerificationState | null>(null);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    void ownerMockDetailApi(withAccess, mockId, controller.signal)
      .then((mock) => {
        if (active) setState({ status: "success", mockId, mock });
      })
      .catch(() => {
        if (active) setState({ status: "error", mockId });
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [mockId, retryKey, withAccess]);

  if (state.status === "loading" || state.mockId !== mockId) {
    return (
      <section
        aria-busy="true"
        aria-label="Loading mock details"
        className="owner-mocks-state"
        role="status"
      >
        Loading mock details…
      </section>
    );
  }

  if (state.status === "error") {
    return (
      <section
        className="owner-mocks-state owner-mocks-state--error"
        role="alert"
      >
        <p className="eyebrow">Connection issue</p>
        <h2>Mock details unavailable</h2>
        <p>We couldn&apos;t load this mock. Please try again.</p>
        <button
          className="primary-button"
          onClick={() => {
            setState({ status: "loading" });
            setRetryKey((key) => key + 1);
          }}
          type="button"
        >
          Try again
        </button>
      </section>
    );
  }

  const { mock } = state;
  const statusClass = mock.status.toLowerCase().replaceAll("_", "-");
  const validation =
    paperValidation?.mockId === mock.id ? paperValidation : null;
  const rulesNotes =
    rulesDraft?.mockId === mock.id ? rulesDraft.notes : mock.rules_source_notes;
  const rulesConfirmed = confirmedMockId === mock.id;
  const currentRulesOperation =
    rulesOperation?.mockId === mock.id ? rulesOperation : null;

  async function runPaperValidation() {
    setPaperValidation({ status: "loading", mockId: mock.id });
    try {
      const result = await validateOwnerPaperApi(withAccess, mock.id);
      setPaperValidation({ status: "success", mockId: mock.id, result });
    } catch {
      setPaperValidation({ status: "error", mockId: mock.id });
    }
  }

  async function recordRulesVerification(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setRulesOperation({ status: "saving", mockId: mock.id });
    try {
      const verified = await verifyOwnerRulesApi(
        withAccess,
        mock.id,
        rulesNotes,
        rulesConfirmed,
      );
      setState((current) =>
        current.status === "success" && current.mockId === mock.id
          ? { ...current, mock: { ...current.mock, ...verified } }
          : current,
      );
      setRulesDraft({ mockId: mock.id, notes: verified.rules_source_notes });
      setConfirmedMockId(null);
      setRulesOperation({ status: "saved", mockId: mock.id });
    } catch (error) {
      setRulesOperation({
        status: "error",
        mockId: mock.id,
        message:
          error instanceof Error
            ? error.message
            : "Verification could not be recorded. Please try again.",
      });
    }
  }

  return (
    <section className="owner-mock-detail">
      <Link className="owner-back-link" to="/owner/mocks">
        ← All mocks
      </Link>
      <header className="owner-mock-detail__heading">
        <div>
          <p className="eyebrow">Read-only mock record</p>
          <h2>{mock.title}</h2>
          <p className="owner-mock-detail__slug">{mock.slug}</p>
        </div>
        <div className="owner-mock-detail__actions">
          <Link
            className="secondary-button"
            to={`/owner/mocks/${mock.id}/questions`}
          >
            Questions
          </Link>
          {mock.status === "DRAFT" && (
            <Link
              className="primary-button owner-mock-edit"
              to={`/owner/mocks/${mock.id}/edit`}
            >
              Edit
            </Link>
          )}
          <span
            className={`owner-status-badge owner-status-badge--${statusClass}`}
          >
            {statusLabels[mock.status]}
          </span>
        </div>
      </header>

      <section aria-label="Mock operations" className="owner-mock-facts">
        <article>
          <h3>Exam and scheme</h3>
          <dl>
            <div>
              <dt>Exam type</dt>
              <dd>{mock.exam_type.name}</dd>
            </div>
            <div>
              <dt>Scheme</dt>
              <dd>
                {mock.exam_scheme.name} · {mock.exam_scheme.version}
              </dd>
            </div>
            <div>
              <dt>Scheme state</dt>
              <dd>{mock.exam_scheme.active ? "Active" : "Inactive"}</dd>
            </div>
            <div>
              <dt>Questions</dt>
              <dd>
                <Link to={`/owner/mocks/${mock.id}/questions`}>
                  {mock.question_count.toLocaleString("en-IN")} /{" "}
                  {mock.exam_scheme.total_question_count.toLocaleString(
                    "en-IN",
                  )}
                </Link>
              </dd>
            </div>
            <div>
              <dt>Price</dt>
              <dd>{price(mock.price_paise)}</dd>
            </div>
          </dl>
        </article>

        <article>
          <h3>Schedule</h3>
          <dl>
            <div>
              <dt>Starts</dt>
              <dd>{dateTime(mock.starts_at)}</dd>
            </div>
            <div>
              <dt>Ends</dt>
              <dd>{dateTime(mock.ends_at)}</dd>
            </div>
            <div>
              <dt>Results release</dt>
              <dd>{dateTime(mock.result_release_at)}</dd>
            </div>
            <div>
              <dt>Official rules</dt>
              <dd>
                {mock.rules_verified_at
                  ? `Verified ${dateTime(mock.rules_verified_at)}`
                  : "Not verified"}
              </dd>
            </div>
          </dl>
        </article>
      </section>

      <section aria-label="Mock checks" className="owner-operations-grid">
        <article
          aria-labelledby="owner-paper-validation-heading"
          className="owner-operation-panel"
        >
          <div className="owner-operation-panel__heading">
            <div>
              <p className="eyebrow">On-demand check</p>
              <h3 id="owner-paper-validation-heading">Paper validation</h3>
            </div>
            <button
              className="primary-button"
              disabled={validation?.status === "loading"}
              onClick={() => void runPaperValidation()}
              type="button"
            >
              {validation?.status === "loading"
                ? "Validating..."
                : validation?.status === "success"
                  ? "Validate again"
                  : "Validate paper"}
            </button>
          </div>
          <p className="owner-operation-panel__help">
            Runs the existing paper checks now. This result is shown for this
            page view only and is not saved.
          </p>
          {validation?.status === "loading" && (
            <p aria-live="polite" role="status">
              Validating the current paper...
            </p>
          )}
          {validation?.status === "error" && (
            <div className="owner-operation-error" role="alert">
              <p>Paper validation could not be completed.</p>
              <button
                className="secondary-button"
                onClick={() => void runPaperValidation()}
                type="button"
              >
                Retry validation
              </button>
            </div>
          )}
          {validation?.status === "success" && (
            <div
              aria-label="Paper validation result"
              className={
                "owner-paper-result " +
                (validation.result.valid
                  ? "owner-paper-result--valid"
                  : "owner-paper-result--invalid")
              }
              role="status"
            >
              <h4>{validation.result.valid ? "Valid" : "Invalid"}</h4>
              <dl className="owner-paper-result__summary">
                <div>
                  <dt>Questions</dt>
                  <dd>
                    {validation.result.actual_question_count} /{" "}
                    {validation.result.expected_question_count}
                  </dd>
                </div>
                <div>
                  <dt>Positive marks</dt>
                  <dd>
                    {validation.result.marks_summary.actual} /{" "}
                    {validation.result.marks_summary.expected}
                  </dd>
                </div>
              </dl>
              <div className="owner-paper-result__messages">
                <h5>Validation errors</h5>
                {validation.result.errors.length > 0 ? (
                  <ul>
                    {validation.result.errors.map((error, index) => (
                      <li key={index}>{error}</li>
                    ))}
                  </ul>
                ) : (
                  <p>No validation errors were returned.</p>
                )}
                <h5>Warnings</h5>
                {validation.result.warnings.length > 0 ? (
                  <ul>
                    {validation.result.warnings.map((warning, index) => (
                      <li key={index}>{warning}</li>
                    ))}
                  </ul>
                ) : (
                  <p>
                    The existing validator does not return separate warnings.
                  </p>
                )}
              </div>
            </div>
          )}
        </article>

        <article
          aria-labelledby="owner-rules-verification-heading"
          className="owner-operation-panel"
        >
          <div className="owner-operation-panel__heading">
            <div>
              <p className="eyebrow">Official source review</p>
              <h3 id="owner-rules-verification-heading">Official rules</h3>
            </div>
            <span
              className={
                "owner-rules-badge " +
                (mock.rules_verified_at
                  ? "owner-rules-badge--verified"
                  : "owner-rules-badge--unverified")
              }
            >
              {mock.rules_verified_at ? "Verified" : "Not verified"}
            </span>
          </div>
          {mock.rules_verified_at && (
            <div className="owner-rules-verification-metadata">
              <p>Verified {dateTime(mock.rules_verified_at)}</p>
              {mock.rules_source_notes && (
                <p className="owner-rules-source-notes">
                  {mock.rules_source_notes}
                </p>
              )}
            </div>
          )}
          {mock.status === "DRAFT" ? (
            <form
              className="owner-rules-verification-form"
              onSubmit={(event) => void recordRulesVerification(event)}
            >
              <p className="owner-operation-panel__help">
                Record the official source, edition or version, checked date,
                and checks performed. The verification time is set by the
                server.
              </p>
              {mock.rules_verified_at && (
                <p className="owner-rules-reverification-note">
                  Recording again replaces the current notes and verification
                  timestamp.
                </p>
              )}
              <label htmlFor="owner-rules-source-notes">
                Source and verification notes
              </label>
              <textarea
                id="owner-rules-source-notes"
                onChange={(event) => {
                  setRulesDraft({ mockId: mock.id, notes: event.target.value });
                  setConfirmedMockId(null);
                  setRulesOperation(null);
                }}
                placeholder="Official source, edition/version, checked date, and checks performed"
                required
                rows={5}
                value={rulesNotes}
              />
              <label className="owner-rules-confirm">
                <input
                  checked={rulesConfirmed}
                  onChange={(event) =>
                    setConfirmedMockId(event.target.checked ? mock.id : null)
                  }
                  type="checkbox"
                />
                I reviewed the official source and confirm recording this
                verification.
              </label>
              <button
                className="primary-button"
                disabled={
                  !rulesNotes.trim() ||
                  !rulesConfirmed ||
                  currentRulesOperation?.status === "saving"
                }
                type="submit"
              >
                {currentRulesOperation?.status === "saving"
                  ? "Recording..."
                  : "Record verification"}
              </button>
              {currentRulesOperation?.status === "error" && (
                <p className="owner-operation-error" role="alert">
                  {currentRulesOperation.message}
                </p>
              )}
              {currentRulesOperation?.status === "saved" && (
                <p className="owner-operation-success" role="status">
                  Official-rules verification recorded.
                </p>
              )}
            </form>
          ) : (
            <p className="owner-operation-panel__help">
              Official rules can be verified only while this mock is in DRAFT.
            </p>
          )}
        </article>
      </section>

      <section
        aria-labelledby="owner-mock-phases-heading"
        className="owner-mock-phases"
      >
        <div className="owner-mock-section-heading">
          <div>
            <p className="eyebrow">Schedule structure</p>
            <h3 id="owner-mock-phases-heading">Phases</h3>
          </div>
          <span>{mock.phases.length} total</span>
        </div>
        {mock.phases.length ? (
          <ol className="owner-mock-phase-list">
            {mock.phases.map((phase) => (
              <li key={phase.order}>
                <span className="owner-mock-phase-list__order">
                  {String(phase.order).padStart(2, "0")}
                </span>
                <div>
                  <h4>{phase.name}</h4>
                  <p>
                    Starts {phase.start_offset_minutes} minutes into the mock ·{" "}
                    {phase.duration_minutes} minutes · {phase.question_count}{" "}
                    {phase.question_count === 1 ? "question" : "questions"}
                  </p>
                  <small>
                    Question sequence{" "}
                    {phase.sequence_locked ? "locks" : "does not lock"} at phase
                    end
                  </small>
                </div>
              </li>
            ))}
          </ol>
        ) : (
          <p className="owner-mock-empty-phases">No generated phases.</p>
        )}
      </section>

      {mock.operational_warnings.length > 0 && (
        <section
          aria-labelledby="owner-mock-warnings-heading"
          className="owner-mock-warnings"
          role="status"
        >
          <h3 id="owner-mock-warnings-heading">Operational warnings</h3>
          <ul>
            {mock.operational_warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </section>
      )}

      <p className="owner-mock-validation-note">
        Paper validation uses the existing domain checks. Its result is not
        saved to the mock.
      </p>
    </section>
  );
}
