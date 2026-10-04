import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { price } from "../api/commerce";
import { useAuth } from "../auth/auth-context";
import {
  ownerMockDetailApi,
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

function dateTime(value: string) {
  return `${dateTimeFormatter.format(new Date(value))} IST`;
}

export function OwnerMockDetailPage() {
  const { mockId = "" } = useParams();
  const { withAccess } = useAuth();
  const [retryKey, setRetryKey] = useState(0);
  const [state, setState] = useState<DetailState>({ status: "loading" });

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
        Full paper validation is not run on this page. Use the on-demand mock
        validation operation in Django Admin when a full paper check is needed.
      </p>
    </section>
  );
}
