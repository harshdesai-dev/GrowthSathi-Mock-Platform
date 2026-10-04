import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";

import { price } from "../api/commerce";
import { useAuth } from "../auth/auth-context";
import {
  calculateOwnerResultsApi,
  correctOwnerAnswerApi,
  ownerMockResultsApi,
  ownerPaymentDetailApi,
  ownerPaymentsApi,
  ownerResultsApi,
  ownerStudentDetailApi,
  ownerStudentsApi,
  publishOwnerResultsApi,
  reconcileOwnerPaymentApi,
  reconcileOwnerResultsApi,
  verifyOwnerResultsApi,
  type OwnerOrderDetail,
  type OwnerOrderSummary,
  type OwnerPage,
  type OwnerResultMock,
  type OwnerStudentDetail,
  type OwnerStudentSummary,
} from "./api";

const dateTime = (value: string | null) =>
  value
    ? new Intl.DateTimeFormat("en-IN", {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: "Asia/Kolkata",
      }).format(new Date(value))
    : "—";

function StatePanel({ children }: { children: ReactNode }) {
  return <section className="owner-mocks-state">{children}</section>;
}

function ErrorMessage({ error }: { error: unknown }) {
  return (
    <p className="owner-operation-error" role="alert">
      {error instanceof Error
        ? error.message
        : "The operation could not be completed."}
    </p>
  );
}

export function OwnerResultsPage() {
  const { withAccess } = useAuth();
  const [state, setState] = useState<
    | { status: "loading" }
    | { status: "error" }
    | { status: "ready"; rows: OwnerResultMock[] }
  >({ status: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    void ownerResultsApi(withAccess, controller.signal)
      .then(({ results }) => setState({ status: "ready", rows: results }))
      .catch(() => setState({ status: "error" }));
    return () => controller.abort();
  }, [withAccess]);

  if (state.status === "loading")
    return <StatePanel>Loading result operations…</StatePanel>;
  if (state.status === "error")
    return <StatePanel>Result operations are unavailable.</StatePanel>;
  return (
    <section className="owner-operation-page">
      <header className="owner-list-heading">
        <div>
          <p className="eyebrow">Closed mocks</p>
          <h2>Results</h2>
        </div>
      </header>
      {state.rows.length === 0 ? (
        <StatePanel>
          No closed mocks are ready for result operations.
        </StatePanel>
      ) : (
        <div className="owner-data-list">
          {state.rows.map((mock) => (
            <article className="owner-data-card" key={mock.id}>
              <div>
                <h3>{mock.title}</h3>
                <p>{mock.status.replaceAll("_", " ")}</p>
              </div>
              <dl>
                <div>
                  <dt>Attempts</dt>
                  <dd>{mock.attempt_count}</dd>
                </div>
                <div>
                  <dt>Key verification</dt>
                  <dd>{mock.verification_state}</dd>
                </div>
                <div>
                  <dt>Calculation</dt>
                  <dd>{mock.calculation_state}</dd>
                </div>
                <div>
                  <dt>Publication</dt>
                  <dd>{mock.publication_state}</dd>
                </div>
                <div>
                  <dt>Release</dt>
                  <dd>{dateTime(mock.result_release_at)}</dd>
                </div>
              </dl>
              <Link
                className="primary-button"
                to={`/owner/mocks/${mock.id}/results`}
              >
                Operate results
              </Link>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

export function OwnerMockResultsPage() {
  const { mockId = "" } = useParams();
  const { withAccess } = useAuth();
  const [data, setData] = useState<OwnerResultMock | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [notes, setNotes] = useState("");
  const [correction, setCorrection] = useState({
    question: "",
    reason: "",
    kind: "MCQ",
    answer: "",
    tolerance: "",
  });

  useEffect(() => {
    const controller = new AbortController();
    void ownerMockResultsApi(withAccess, mockId, controller.signal)
      .then((result) => {
        setData(result);
        setError(null);
      })
      .catch(setError);
    return () => controller.abort();
  }, [mockId, refresh, withAccess]);

  async function operate(action: () => Promise<unknown>, message: string) {
    if (!window.confirm(message)) return;
    setBusy(true);
    setError(null);
    try {
      await action();
      setRefresh((value) => value + 1);
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  if (!data && !error) return <StatePanel>Loading result workflow…</StatePanel>;
  if (!data)
    return (
      <StatePanel>
        <ErrorMessage error={error} />
      </StatePanel>
    );
  const run = data.latest_run;
  return (
    <section className="owner-operation-page">
      <Link className="owner-back-link" to="/owner/results">
        ← All results
      </Link>
      <header className="owner-list-heading">
        <div>
          <p className="eyebrow">Result workflow</p>
          <h2>{data.title}</h2>
        </div>
        <span className="owner-status-badge">{data.status}</span>
      </header>
      {error !== null && <ErrorMessage error={error} />}
      {data.operational_warnings.map((warning) => (
        <p className="owner-warning" key={warning}>
          {warning}
        </p>
      ))}
      <div className="owner-operations-grid">
        <article className="owner-operation-panel">
          <h3>1. Reconcile attempts</h3>
          <p className="owner-operation-panel__help">
            Auto-submits expired attempts through the existing result service.
          </p>
          <button
            className="secondary-button"
            disabled={busy || data.status !== "CLOSED"}
            onClick={() =>
              void operate(
                () => reconcileOwnerResultsApi(withAccess, data.id),
                "Reconcile expired attempts for this mock?",
              )
            }
            type="button"
          >
            Reconcile attempts
          </button>
        </article>
        <article className="owner-operation-panel">
          <h3>2. Verify answer key</h3>
          <textarea
            onChange={(event) => setNotes(event.target.value)}
            placeholder="What was checked against the verified answer key?"
            value={notes}
          />
          <button
            className="primary-button"
            disabled={busy || !notes.trim() || data.status !== "CLOSED"}
            onClick={() =>
              void operate(
                () => verifyOwnerResultsApi(withAccess, data.id, notes),
                "Record this answer-key verification and prepare a result batch?",
              )
            }
            type="button"
          >
            Verify and prepare
          </button>
        </article>
        <article className="owner-operation-panel">
          <h3>3. Calculate</h3>
          <p className="owner-operation-panel__help">
            Current batch: {run?.status ?? "None"}. Participants:{" "}
            {run?.participant_count ?? 0}.
          </p>
          <button
            className="primary-button"
            disabled={
              busy || !run || !["VERIFIED", "COMPLETE"].includes(run.status)
            }
            onClick={() =>
              run &&
              void operate(
                () => calculateOwnerResultsApi(withAccess, data.id, run.id),
                "Calculate this verified result batch?",
              )
            }
            type="button"
          >
            Calculate results
          </button>
        </article>
        <article className="owner-operation-panel">
          <h3>4. Publish</h3>
          <p className="owner-operation-panel__help">
            Publication respects release timing and makes verified results
            visible to students.
          </p>
          <button
            className="primary-button"
            disabled={busy || run?.status !== "COMPLETE"}
            onClick={() =>
              run &&
              void operate(
                () => publishOwnerResultsApi(withAccess, data.id, run.id),
                "Publish verified results to students? This will make results visible.",
              )
            }
            type="button"
          >
            Publish verified results
          </button>
        </article>
      </div>
      {data.status === "CLOSED" && (
        <form
          className="owner-operation-panel owner-correction-form"
          onSubmit={(event) => {
            event.preventDefault();
            const input =
              correction.kind === "MCQ"
                ? {
                    question_id: correction.question,
                    reason: correction.reason,
                    correct_option: correction.answer,
                  }
                : {
                    question_id: correction.question,
                    reason: correction.reason,
                    numeric_answer: correction.answer,
                    numeric_tolerance: correction.tolerance || undefined,
                  };
            void operate(
              () => correctOwnerAnswerApi(withAccess, data.id, input),
              "Correct this answer key? Existing result drafts will be invalidated.",
            );
          }}
        >
          <h3>Audited answer-key correction</h3>
          <p className="owner-operation-panel__help">
            Use only after close and before publication. This does not enable
            broad question editing.
          </p>
          <input
            aria-label="Question ID"
            onChange={(event) =>
              setCorrection({ ...correction, question: event.target.value })
            }
            placeholder="Question UUID"
            required
            value={correction.question}
          />
          <select
            aria-label="Answer type"
            onChange={(event) =>
              setCorrection({
                ...correction,
                kind: event.target.value,
                answer: "",
              })
            }
            value={correction.kind}
          >
            <option value="MCQ">MCQ option</option>
            <option value="NUMERIC">Numerical answer</option>
          </select>
          <input
            aria-label="Correct answer"
            onChange={(event) =>
              setCorrection({ ...correction, answer: event.target.value })
            }
            placeholder={
              correction.kind === "MCQ"
                ? "A, B, C or D"
                : "Correct numerical answer"
            }
            required
            value={correction.answer}
          />
          {correction.kind === "NUMERIC" && (
            <input
              aria-label="Numeric tolerance"
              onChange={(event) =>
                setCorrection({ ...correction, tolerance: event.target.value })
              }
              placeholder="Tolerance (optional)"
              value={correction.tolerance}
            />
          )}
          <textarea
            aria-label="Correction reason"
            onChange={(event) =>
              setCorrection({ ...correction, reason: event.target.value })
            }
            placeholder="Reason for correction"
            required
            value={correction.reason}
          />
          <button className="secondary-button" disabled={busy} type="submit">
            Record correction
          </button>
        </form>
      )}
      <section className="owner-operation-panel">
        <h3>Batch history</h3>
        {data.runs.length ? (
          <ul className="owner-history-list">
            {data.runs.map((item) => (
              <li key={item.id}>
                <strong>{item.status}</strong>
                <span>
                  {dateTime(item.started_at)} · {item.participant_count}{" "}
                  participants
                </span>
                {item.errors && <small>{item.errors}</small>}
              </li>
            ))}
          </ul>
        ) : (
          <p>No batches yet.</p>
        )}
      </section>
    </section>
  );
}

function Pager({
  page,
  result,
  onPage,
}: {
  page: number;
  result: OwnerPage<unknown>;
  onPage: (page: number) => void;
}) {
  return (
    <div className="owner-pager">
      <button
        className="secondary-button"
        disabled={!result.previous}
        onClick={() => onPage(page - 1)}
        type="button"
      >
        Previous
      </button>
      <span>
        Page {page} · {result.count} records
      </span>
      <button
        className="secondary-button"
        disabled={!result.next}
        onClick={() => onPage(page + 1)}
        type="button"
      >
        Next
      </button>
    </div>
  );
}

export function OwnerStudentsPage() {
  const { withAccess } = useAuth();
  const [draft, setDraft] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<OwnerPage<OwnerStudentSummary> | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    void ownerStudentsApi(withAccess, search, page, controller.signal)
      .then((result) => {
        setData(result);
        setError(false);
      })
      .catch(() => setError(true));
    return () => controller.abort();
  }, [page, search, withAccess]);
  return (
    <section className="owner-operation-page">
      <header className="owner-list-heading">
        <div>
          <p className="eyebrow">Read-only operations</p>
          <h2>Students</h2>
        </div>
      </header>
      <form
        className="owner-inline-filters"
        onSubmit={(event) => {
          event.preventDefault();
          setPage(1);
          setSearch(draft);
        }}
      >
        <input
          aria-label="Search students"
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Name, email or phone"
          value={draft}
        />
        <button className="primary-button">Search</button>
      </form>
      {error ? (
        <StatePanel>Students could not be loaded.</StatePanel>
      ) : !data ? (
        <StatePanel>Loading students…</StatePanel>
      ) : (
        <>
          <div className="owner-data-list">
            {data.results.map((student) => (
              <article className="owner-data-card" key={student.id}>
                <div>
                  <h3>{student.name || "Onboarding incomplete"}</h3>
                  <p>{student.email}</p>
                </div>
                <dl>
                  <div>
                    <dt>Target</dt>
                    <dd>{student.exam_target || "—"}</dd>
                  </div>
                  <div>
                    <dt>Purchased mocks</dt>
                    <dd>{student.purchased_mocks_count}</dd>
                  </div>
                  <div>
                    <dt>Attempts</dt>
                    <dd>{student.attempts_count}</dd>
                  </div>
                </dl>
                <Link
                  className="secondary-button"
                  to={`/owner/students/${student.id}`}
                >
                  View student
                </Link>
              </article>
            ))}
          </div>
          <Pager page={page} result={data} onPage={setPage} />
        </>
      )}
    </section>
  );
}

export function OwnerStudentDetailPage() {
  const { studentId = "" } = useParams();
  const { withAccess } = useAuth();
  const [data, setData] = useState<OwnerStudentDetail | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    void ownerStudentDetailApi(withAccess, studentId, controller.signal)
      .then(setData)
      .catch(() => setError(true));
    return () => controller.abort();
  }, [studentId, withAccess]);
  if (error)
    return <StatePanel>Student details could not be loaded.</StatePanel>;
  if (!data) return <StatePanel>Loading student…</StatePanel>;
  return (
    <section className="owner-operation-page">
      <Link className="owner-back-link" to="/owner/students">
        ← All students
      </Link>
      <header className="owner-list-heading">
        <div>
          <p className="eyebrow">Read-only student record</p>
          <h2>{data.name || data.email}</h2>
          <p>
            {data.email} · {data.phone || "No phone"}
          </p>
        </div>
      </header>
      <div className="owner-operations-grid">
        <History
          title="Purchases"
          empty="No purchases."
          rows={data.orders.map(
            (row) =>
              `${row.offer} · ${row.status} · ${price(row.amount_paise)}`,
          )}
        />
        <History
          title="Mock access"
          empty="No access grants."
          rows={data.access.map((row) => `${row.mock_title} · ${row.status}`)}
        />
      </div>
      <History
        title="Attempts and results"
        empty="No attempts."
        rows={data.attempts.map(
          (row) =>
            `${row.mock_title} · ${row.status}${row.result ? ` · Score ${row.result.score} · Rank ${row.result.rank}` : ""}`,
        )}
      />
    </section>
  );
}

function History({
  title,
  rows,
  empty,
}: {
  title: string;
  rows: string[];
  empty: string;
}) {
  return (
    <section className="owner-operation-panel">
      <h3>{title}</h3>
      {rows.length ? (
        <ul className="owner-history-list">
          {rows.map((row, index) => (
            <li key={`${row}-${index}`}>{row}</li>
          ))}
        </ul>
      ) : (
        <p>{empty}</p>
      )}
    </section>
  );
}

export function OwnerPaymentsPage() {
  const { withAccess } = useAuth();
  const [filters, setFilters] = useState({
    search: "",
    orderStatus: "",
    paymentStatus: "",
  });
  const [applied, setApplied] = useState(filters);
  const [page, setPage] = useState(1);
  const [data, setData] = useState<OwnerPage<OwnerOrderSummary> | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    void ownerPaymentsApi(withAccess, applied, page, controller.signal)
      .then((result) => {
        setData(result);
        setError(false);
      })
      .catch(() => setError(true));
    return () => controller.abort();
  }, [applied, page, withAccess]);
  return (
    <section className="owner-operation-page">
      <header className="owner-list-heading">
        <div>
          <p className="eyebrow">Provider-backed records</p>
          <h2>Payments</h2>
        </div>
      </header>
      <form
        className="owner-inline-filters"
        onSubmit={(event) => {
          event.preventDefault();
          setPage(1);
          setApplied(filters);
        }}
      >
        <input
          aria-label="Search payments"
          onChange={(event) =>
            setFilters({ ...filters, search: event.target.value })
          }
          placeholder="Student, order or gateway ID"
          value={filters.search}
        />
        <select
          aria-label="Order status"
          onChange={(event) =>
            setFilters({ ...filters, orderStatus: event.target.value })
          }
          value={filters.orderStatus}
        >
          <option value="">All order states</option>
          {["CREATED", "PENDING", "PAID", "FAILED", "REFUNDED"].map((value) => (
            <option key={value}>{value}</option>
          ))}
        </select>
        <select
          aria-label="Payment status"
          onChange={(event) =>
            setFilters({ ...filters, paymentStatus: event.target.value })
          }
          value={filters.paymentStatus}
        >
          <option value="">All payment states</option>
          {["AUTHORIZED", "CAPTURED", "FAILED", "REFUNDED"].map((value) => (
            <option key={value}>{value}</option>
          ))}
        </select>
        <button className="primary-button">Apply</button>
      </form>
      {error ? (
        <StatePanel>Payments could not be loaded.</StatePanel>
      ) : !data ? (
        <StatePanel>Loading payments…</StatePanel>
      ) : (
        <>
          <div className="owner-data-list">
            {data.results.map((order) => (
              <article
                className={`owner-data-card ${order.review_required ? "owner-data-card--warning" : ""}`}
                key={order.id}
              >
                <div>
                  <h3>{order.student.name || order.student.email}</h3>
                  <p>
                    {order.offer} · {dateTime(order.created_at)}
                  </p>
                </div>
                <dl>
                  <div>
                    <dt>Amount</dt>
                    <dd>{price(order.amount_paise)}</dd>
                  </div>
                  <div>
                    <dt>Order</dt>
                    <dd>{order.order_status}</dd>
                  </div>
                  <div>
                    <dt>Payment</dt>
                    <dd>{order.payment_status ?? "None"}</dd>
                  </div>
                </dl>
                {order.review_required && (
                  <p className="owner-warning">
                    Review required: {order.review_note}
                  </p>
                )}
                <Link
                  className="secondary-button"
                  to={`/owner/payments/${order.id}`}
                >
                  Inspect order
                </Link>
              </article>
            ))}
          </div>
          <Pager page={page} result={data} onPage={setPage} />
        </>
      )}
    </section>
  );
}

export function OwnerPaymentDetailPage() {
  const { orderId = "" } = useParams();
  const { withAccess } = useAuth();
  const [data, setData] = useState<OwnerOrderDetail | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [refresh, setRefresh] = useState(0);
  const [kind, setKind] = useState<"ORDER" | "PAYMENT">("PAYMENT");
  const [reference, setReference] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    void ownerPaymentDetailApi(withAccess, orderId, controller.signal)
      .then(setData)
      .catch(setError);
    return () => controller.abort();
  }, [orderId, refresh, withAccess]);
  if (!data && error)
    return (
      <StatePanel>
        <ErrorMessage error={error} />
      </StatePanel>
    );
  if (!data) return <StatePanel>Loading payment…</StatePanel>;
  const order = data;
  async function reconcile(event: FormEvent) {
    event.preventDefault();
    if (
      !window.confirm(
        "Fetch and verify this reference with the payment provider? No payment will be manually marked paid.",
      )
    )
      return;
    setBusy(true);
    setError(null);
    try {
      await reconcileOwnerPaymentApi(withAccess, order.id, kind, reference);
      setReference("");
      setRefresh((value) => value + 1);
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="owner-operation-page">
      <Link className="owner-back-link" to="/owner/payments">
        ← All payments
      </Link>
      <header className="owner-list-heading">
        <div>
          <p className="eyebrow">Order {order.id}</p>
          <h2>{order.offer}</h2>
          <p>
            {order.student.name || order.student.email} ·{" "}
            {price(order.amount_paise)}
          </p>
        </div>
        <span className="owner-status-badge">{order.order_status}</span>
      </header>
      {order.review_required && (
        <p className="owner-warning">Review required: {order.review_note}</p>
      )}
      {error !== null && <ErrorMessage error={error} />}
      <div className="owner-operations-grid">
        <History
          title="Payment attempts"
          empty="No payment attempts recorded."
          rows={order.payments.map(
            (row) =>
              `${row.gateway_payment_id} · ${row.status} · ${price(row.amount_paise)}`,
          )}
        />
        <History
          title="Access grants"
          empty="No access grants."
          rows={order.access_grants.map(
            (row) => `${row.mock_title} · ${row.status}`,
          )}
        />
      </div>
      <form
        className="owner-operation-panel owner-reconcile-form"
        onSubmit={(event) => void reconcile(event)}
      >
        <h3>Provider reconciliation</h3>
        <p className="owner-operation-panel__help">
          Fetches provider truth through the existing reconciliation service. It
          never trusts a frontend success message.
        </p>
        <select
          onChange={(event) =>
            setKind(event.target.value as "ORDER" | "PAYMENT")
          }
          value={kind}
        >
          <option value="PAYMENT">Gateway payment reference</option>
          <option value="ORDER">Gateway order reference</option>
        </select>
        <input
          onChange={(event) => setReference(event.target.value)}
          placeholder={kind === "PAYMENT" ? "pay_…" : "order_…"}
          required
          value={reference}
        />
        <button className="primary-button" disabled={busy} type="submit">
          {busy ? "Reconciling…" : "Reconcile with provider"}
        </button>
      </form>
    </section>
  );
}
