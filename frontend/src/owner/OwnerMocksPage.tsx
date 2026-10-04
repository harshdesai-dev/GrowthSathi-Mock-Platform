import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { price } from "../api/commerce";
import { useAuth } from "../auth/auth-context";
import {
  MOCK_STATUSES,
  ownerMocksApi,
  type OwnerMockFilters,
  type OwnerMockStatus,
  type OwnerMockSummary,
} from "./api";

const initialFilters: OwnerMockFilters = {
  search: "",
  examType: "",
  status: "",
};

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

type MocksState =
  | { status: "loading" }
  | { status: "success"; mocks: OwnerMockSummary[] }
  | { status: "error" };

function dateTime(value: string) {
  return `${dateTimeFormatter.format(new Date(value))} IST`;
}

function StatusBadge({ mock }: { mock: OwnerMockSummary }) {
  const className = mock.status.toLowerCase().replaceAll("_", "-");
  return (
    <span className={`owner-status-badge owner-status-badge--${className}`}>
      {statusLabels[mock.status]}
    </span>
  );
}

function RulesVerification({ mock }: { mock: OwnerMockSummary }) {
  return mock.rules_verified_at ? (
    <span className="owner-rule-state owner-rule-state--verified">
      Verified <small>{dateTime(mock.rules_verified_at)}</small>
    </span>
  ) : (
    <span className="owner-rule-state owner-rule-state--missing">
      Not verified
    </span>
  );
}

function MockViewLink({ mock }: { mock: OwnerMockSummary }) {
  return (
    <Link className="owner-view-link" to={`/owner/mocks/${mock.id}`}>
      View
    </Link>
  );
}

function MockTable({ mocks }: { mocks: OwnerMockSummary[] }) {
  return (
    <div className="owner-mock-table-wrap">
      <table className="owner-mock-table">
        <thead>
          <tr>
            <th scope="col">Mock</th>
            <th scope="col">Exam</th>
            <th scope="col">Date/time</th>
            <th scope="col">Status</th>
            <th scope="col">Questions</th>
            <th scope="col">Rules verification</th>
            <th scope="col">Price</th>
            <th scope="col">Operational action</th>
          </tr>
        </thead>
        <tbody>
          {mocks.map((mock) => (
            <tr key={mock.id}>
              <th className="owner-mock-identity" scope="row">
                <strong>{mock.title}</strong>
                <small>{mock.slug}</small>
              </th>
              <td>
                <strong>{mock.exam_type.name}</strong>
                <small>
                  {mock.exam_scheme.name} · {mock.exam_scheme.version}
                </small>
              </td>
              <td>
                <span>Starts {dateTime(mock.starts_at)}</span>
                <small>Ends {dateTime(mock.ends_at)}</small>
              </td>
              <td>
                <StatusBadge mock={mock} />
              </td>
              <td>
                {mock.question_count.toLocaleString("en-IN")} /{" "}
                {mock.exam_scheme.total_question_count.toLocaleString("en-IN")}
              </td>
              <td>
                <RulesVerification mock={mock} />
              </td>
              <td>{price(mock.price_paise)}</td>
              <td>
                <MockViewLink mock={mock} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MockCards({ mocks }: { mocks: OwnerMockSummary[] }) {
  return (
    <div className="owner-mock-cards">
      {mocks.map((mock) => (
        <article className="owner-mock-card" key={mock.id}>
          <div className="owner-mock-card__heading">
            <div>
              <p className="eyebrow">{mock.slug}</p>
              <h3>{mock.title}</h3>
            </div>
            <StatusBadge mock={mock} />
          </div>
          <dl className="owner-mock-card__details">
            <div>
              <dt>Exam</dt>
              <dd>
                {mock.exam_type.name} · {mock.exam_scheme.version}
              </dd>
            </div>
            <div>
              <dt>Date/time</dt>
              <dd>Starts {dateTime(mock.starts_at)}</dd>
              <dd>Ends {dateTime(mock.ends_at)}</dd>
            </div>
            <div>
              <dt>Questions</dt>
              <dd>
                {mock.question_count} / {mock.exam_scheme.total_question_count}
              </dd>
            </div>
            <div>
              <dt>Rules verification</dt>
              <dd>
                <RulesVerification mock={mock} />
              </dd>
            </div>
            <div>
              <dt>Price</dt>
              <dd>{price(mock.price_paise)}</dd>
            </div>
          </dl>
          <MockViewLink mock={mock} />
        </article>
      ))}
    </div>
  );
}

export function OwnerMocksPage() {
  const { withAccess } = useAuth();
  const [filters, setFilters] = useState(initialFilters);
  const [retryKey, setRetryKey] = useState(0);
  const [state, setState] = useState<MocksState>({ status: "loading" });
  const hasFilters = Boolean(
    filters.search.trim() || filters.examType || filters.status,
  );

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const timer = window.setTimeout(
      () => {
        setState({ status: "loading" });
        void ownerMocksApi(withAccess, filters, controller.signal)
          .then(({ results }) => {
            if (active) setState({ status: "success", mocks: results });
          })
          .catch(() => {
            if (active) setState({ status: "error" });
          });
      },
      filters.search ? 250 : 0,
    );

    return () => {
      active = false;
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [filters, retryKey, withAccess]);

  const updateFilter = <K extends keyof OwnerMockFilters>(
    key: K,
    value: OwnerMockFilters[K],
  ) => setFilters((current) => ({ ...current, [key]: value }));

  return (
    <section className="owner-mocks-page">
      <header className="owner-mocks-heading">
        <div>
          <p className="eyebrow">Operations</p>
          <h2>Mocks</h2>
          <p>
            Review mock schedules, lifecycle state, paper counts, and rules
            verification.
          </p>
        </div>
      </header>

      <div aria-label="Mock filters" className="owner-mock-filters">
        <label className="owner-mock-search">
          <span>Search by title</span>
          <input
            autoComplete="off"
            onChange={(event) => updateFilter("search", event.target.value)}
            placeholder="Search mocks"
            type="search"
            value={filters.search}
          />
        </label>
        <label>
          <span>Exam type</span>
          <select
            onChange={(event) => updateFilter("examType", event.target.value)}
            value={filters.examType}
          >
            <option value="">All exam types</option>
            <option value="JEE_MAIN">JEE Main</option>
            <option value="MHT_CET_PCM">MHT-CET PCM</option>
          </select>
        </label>
        <label>
          <span>Status</span>
          <select
            onChange={(event) =>
              updateFilter("status", event.target.value as OwnerMockStatus | "")
            }
            value={filters.status}
          >
            <option value="">All statuses</option>
            {MOCK_STATUSES.map((status) => (
              <option key={status} value={status}>
                {statusLabels[status]}
              </option>
            ))}
          </select>
        </label>
        <button
          className="secondary-button owner-mock-clear"
          disabled={!hasFilters}
          onClick={() => setFilters(initialFilters)}
          type="button"
        >
          Clear filters
        </button>
      </div>

      {state.status === "loading" ? (
        <div
          aria-busy="true"
          aria-label="Loading mocks"
          className="owner-mocks-state"
          role="status"
        >
          Loading mock operations…
        </div>
      ) : state.status === "error" ? (
        <div
          className="owner-mocks-state owner-mocks-state--error"
          role="alert"
        >
          <h3>Mocks unavailable</h3>
          <p>We couldn&apos;t load the mock list. Please try again.</p>
          <button
            className="primary-button"
            onClick={() => setRetryKey((key) => key + 1)}
            type="button"
          >
            Try again
          </button>
        </div>
      ) : state.mocks.length === 0 ? (
        <div className="owner-mocks-state" role="status">
          {hasFilters ? (
            <>
              <h3>No mocks match these filters</h3>
              <p>Try changing your search or clearing the filters.</p>
            </>
          ) : (
            <>
              <h3>No mocks yet</h3>
              <p>
                Mocks will appear here when they are available in the platform.
              </p>
            </>
          )}
        </div>
      ) : (
        <>
          <p className="owner-mock-result-count" aria-live="polite">
            {state.mocks.length.toLocaleString("en-IN")}{" "}
            {state.mocks.length === 1 ? "mock" : "mocks"}
          </p>
          <MockTable mocks={state.mocks} />
          <MockCards mocks={state.mocks} />
        </>
      )}
    </section>
  );
}
