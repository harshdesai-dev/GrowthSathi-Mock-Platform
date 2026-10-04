import { useCallback, useEffect, useState } from "react";

import { useAuth } from "../auth/auth-context";
import { ownerOverviewApi, type OwnerOverview } from "./api";

const metrics = [
  { key: "total_students", label: "Total students", kind: "count" },
  { key: "upcoming_mocks", label: "Upcoming mocks", kind: "count" },
  { key: "completed_mocks", label: "Completed mocks", kind: "count" },
  { key: "paid_orders", label: "Paid orders", kind: "count" },
  { key: "total_revenue_paise", label: "Revenue", kind: "currency" },
  { key: "failed_payments", label: "Payment failures", kind: "count" },
] as const;

const countFormatter = new Intl.NumberFormat("en-IN");
const currencyFormatter = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
});

type OverviewState =
  | { status: "loading" }
  | { status: "success"; data: OwnerOverview }
  | { status: "error" };

function metricValue(
  metric: (typeof metrics)[number],
  data: OwnerOverview,
): string {
  const value = data[metric.key];
  return metric.kind === "currency"
    ? currencyFormatter.format(value / 100)
    : countFormatter.format(value);
}

export function OwnerOverviewPage() {
  const { withAccess } = useAuth();
  const [state, setState] = useState<OverviewState>({ status: "loading" });
  const fetchOverview = useCallback(
    () => ownerOverviewApi(withAccess),
    [withAccess],
  );

  useEffect(() => {
    let active = true;
    void fetchOverview()
      .then((data) => {
        if (active) setState({ status: "success", data });
      })
      .catch(() => {
        if (active) setState({ status: "error" });
      });
    return () => {
      active = false;
    };
  }, [fetchOverview]);

  const retry = () => {
    setState({ status: "loading" });
    void fetchOverview()
      .then((data) => setState({ status: "success", data }))
      .catch(() => setState({ status: "error" }));
  };

  return (
    <>
      <header className="owner-overview__intro">
        <p className="eyebrow">Operations</p>
        <h2>Owner overview</h2>
        <p>
          Current totals across student profiles, mock lifecycle, and reconciled
          payments.
        </p>
      </header>
      {state.status === "loading" ? (
        <section
          aria-busy="true"
          aria-label="Loading overview metrics"
          className="owner-metrics"
          role="status"
        >
          {metrics.map((metric) => (
            <article
              aria-hidden="true"
              className="owner-metric-card owner-metric-card--loading"
              key={metric.key}
            >
              <div className="owner-metric-card__topline">
                <span>Platform metric</span>
              </div>
              <h3>{metric.label}</h3>
              <span className="owner-metric-card__skeleton" />
            </article>
          ))}
        </section>
      ) : state.status === "error" ? (
        <section className="owner-overview-error" role="alert">
          <p className="eyebrow">Connection issue</p>
          <h3>Overview unavailable</h3>
          <p>We couldn&apos;t load the platform metrics. Please try again.</p>
          <button className="primary-button" onClick={retry} type="button">
            Try again
          </button>
        </section>
      ) : (
        <section
          aria-label="Platform metrics"
          className="owner-metrics"
          aria-live="polite"
        >
          {metrics.map((metric) => (
            <article className="owner-metric-card" key={metric.key}>
              <div className="owner-metric-card__topline">
                <span>Platform metric</span>
                <span aria-hidden="true">•</span>
              </div>
              <h3>{metric.label}</h3>
              <p className="owner-metric-card__value">
                {metricValue(metric, state.data)}
              </p>
            </article>
          ))}
        </section>
      )}
    </>
  );
}
