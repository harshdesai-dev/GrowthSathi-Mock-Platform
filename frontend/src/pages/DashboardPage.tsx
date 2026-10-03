import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import {
  dashboardApi,
  type DashboardData,
  type DashboardMock,
} from "../api/dashboard";
import growthSathiLogo from "../assets/brand/growthsathi-logo.png";
import { useAuth } from "../auth/auth-context";
import { difference, marks } from "../results/format";
import "../styles/dashboard.css";

const labels: Record<DashboardMock["lifecycle_state"], string> = {
  UPCOMING: "Upcoming",
  STARTING_SOON: "Starting soon",
  LIVE: "Live now",
  ATTEMPT_IN_PROGRESS: "Attempt in progress",
  SUBMITTED: "Submitted",
  RESULT_PENDING: "Result pending",
  RESULTS_PUBLISHED: "Results published",
  CANCELLED: "Cancelled",
};

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "Asia/Kolkata",
  }).format(new Date(value));
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat("en-IN", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
    timeZone: "Asia/Kolkata",
  }).format(new Date(value));
}

function useCountdown(target: string, serverTime: string) {
  const [remaining, setRemaining] = useState(() =>
    Math.max(0, Date.parse(target) - Date.parse(serverTime)),
  );
  useEffect(() => {
    const server = Date.parse(serverTime);
    const baseline = performance.now();
    const interval = window.setInterval(() => {
      setRemaining(
        Math.max(
          0,
          Date.parse(target) - (server + performance.now() - baseline),
        ),
      );
    }, 1000);
    return () => window.clearInterval(interval);
  }, [serverTime, target]);
  const seconds = Math.floor(remaining / 1000);
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return remaining
    ? days
      ? `${days}d ${hours}h ${minutes}m`
      : `${hours}h ${minutes}m`
    : "Starting now";
}

function DashboardAction({ mock }: { mock: DashboardMock }) {
  if (mock.lifecycle_state === "CANCELLED") return null;
  if (mock.attempt_status === "IN_PROGRESS" && mock.attempt_id)
    return (
      <Link className="primary-button" to={`/exam/${mock.attempt_id}`}>
        Continue Test
      </Link>
    );
  if (mock.access_state !== "PURCHASED")
    return (
      <Link className="secondary-button" to="/mocks">
        Get access
      </Link>
    );
  if (mock.can_start)
    return (
      <Link className="primary-button" to={`/mocks/${mock.id}/instructions`}>
        Start Test
      </Link>
    );
  return (
    <Link className="secondary-button" to={`/mocks/${mock.id}/instructions`}>
      {mock.attempt_status ? "View status" : "Instructions"}
    </Link>
  );
}

function MockCard({
  mock,
  serverTime,
  next = false,
}: {
  mock: DashboardMock;
  serverTime: string;
  next?: boolean;
}) {
  const countdown = useCountdown(mock.starts_at, serverTime);
  return (
    <article className={`dashboard-mock${next ? " dashboard-mock--next" : ""}`}>
      <div className="dashboard-mock__meta">
        <span
          className={`dashboard-state dashboard-state--${mock.lifecycle_state.toLowerCase()}`}
        >
          {labels[mock.lifecycle_state]}
        </span>
        <span>
          {mock.access_state === "PURCHASED"
            ? "Access purchased"
            : mock.access_state === "CANCELLED"
              ? "Access unavailable"
              : "Not purchased"}
        </span>
      </div>
      <p className="eyebrow">{mock.exam}</p>
      <h2>{mock.title}</h2>
      <dl className="dashboard-mock__schedule">
        <div>
          <dt>Date</dt>
          <dd>
            <time dateTime={mock.starts_at}>{formatDate(mock.starts_at)}</time>
          </dd>
        </div>
        <div>
          <dt>Time</dt>
          <dd>
            <time dateTime={mock.starts_at}>
              {formatTime(mock.starts_at)} IST
            </time>
          </dd>
        </div>
      </dl>
      {(mock.lifecycle_state === "UPCOMING" ||
        mock.lifecycle_state === "STARTING_SOON") && (
        <p className="dashboard-countdown" aria-live="polite">
          <span>Starts in</span>
          <strong>{countdown}</strong>
        </p>
      )}
      <DashboardAction mock={mock} />
    </article>
  );
}

function DashboardContent({
  data,
  name,
}: {
  data: DashboardData;
  name: string;
}) {
  const result = data.latest_result;
  const otherMocks = data.upcoming_mocks.slice(1);
  return (
    <>
      <header className="dashboard-heading">
        <p className="eyebrow">Student dashboard</p>
        <h1>Welcome, {name}.</h1>
        <h2>Your next step, clearly.</h2>
        <p>
          Mock schedules and exam access are confirmed by GrowthSathi servers.
        </p>
      </header>
      <section aria-labelledby="next-mock-title">
        <div className="dashboard-section-heading">
          <div>
            <p className="eyebrow">Next mock</p>
            <h2 id="next-mock-title">Ready when the global window opens</h2>
          </div>
          <Link to="/mocks">All mocks</Link>
        </div>
        {data.next_mock ? (
          <MockCard mock={data.next_mock} serverTime={data.server_time} next />
        ) : (
          <div className="dashboard-empty">
            <h2>No upcoming mocks right now.</h2>
            <p>
              New GrowthSathi mocks will appear here once their schedule is
              published.
            </p>
            <Link className="secondary-button" to="/mocks">
              Browse mocks
            </Link>
          </div>
        )}
      </section>
      {result ? (
        <section
          className="dashboard-result"
          aria-labelledby="latest-result-title"
        >
          <div className="dashboard-section-heading">
            <div>
              <p className="eyebrow">Latest published result</p>
              <h2 id="latest-result-title">{result.mock_title}</h2>
            </div>
            <Link to={`/results/${result.mock_id}`}>View result</Link>
          </div>
          <dl className="dashboard-result__metrics">
            <div className="dashboard-result__score">
              <dt>Score</dt>
              <dd>
                {marks(result.score)}
                <small> / {marks(result.maximum_score)}</small>
              </dd>
            </div>
            <div>
              <dt>Rank</dt>
              <dd>#{result.rank}</dd>
            </div>
            <div>
              <dt>Mock Percentile</dt>
              <dd>{result.percentile}</dd>
            </div>
            <div>
              <dt>Previous</dt>
              <dd>
                {result.previous_score === null
                  ? "First mock"
                  : marks(result.previous_score)}
              </dd>
            </div>
            <div>
              <dt>Change</dt>
              <dd
                className={
                  result.score_difference && Number(result.score_difference) < 0
                    ? "dashboard-negative"
                    : "dashboard-positive"
                }
              >
                {result.score_difference === null
                  ? "—"
                  : `${difference(result.score_difference)} marks`}
              </dd>
            </div>
          </dl>
          <div className="dashboard-result__actions">
            <Link
              className="secondary-button"
              to={`/results/${result.mock_id}/leaderboard`}
            >
              Leaderboard
            </Link>
            <Link
              className="secondary-button"
              to={`/results/${result.mock_id}/review`}
            >
              Review Answers
            </Link>
          </div>
        </section>
      ) : (
        <section className="dashboard-empty">
          <p className="eyebrow">Latest result</p>
          <h2>Your first mock result will appear here.</h2>
          <p>
            Complete a mock and wait for its verified results to be published.
          </p>
        </section>
      )}
      <section className="dashboard-history" aria-labelledby="history-title">
        <div className="dashboard-section-heading">
          <div>
            <p className="eyebrow">Previous mocks</p>
            <h2 id="history-title">Published result history</h2>
          </div>
          {data.history.length ? <Link to="/results">View all</Link> : null}
        </div>
        {data.history.length ? (
          <ul>
            {data.history.slice(0, 4).map((item) => (
              <li key={item.mock_id}>
                <div>
                  <h3>{item.mock_title}</h3>
                  <p>
                    {item.exam} · {formatDate(item.starts_at)}
                  </p>
                </div>
                <dl>
                  <div>
                    <dt>Score</dt>
                    <dd>
                      {marks(item.score)} / {marks(item.maximum_score)}
                    </dd>
                  </div>
                  <div>
                    <dt>Rank</dt>
                    <dd>#{item.rank}</dd>
                  </div>
                  <div>
                    <dt>Mock Percentile</dt>
                    <dd>{item.percentile}</dd>
                  </div>
                </dl>
                <Link to={`/results/${item.mock_id}`}>View Result</Link>
              </li>
            ))}
          </ul>
        ) : (
          <p className="dashboard-empty dashboard-empty--compact">
            No published results yet.
          </p>
        )}
      </section>
      {otherMocks.length ? (
        <section
          className="dashboard-upcoming"
          aria-labelledby="upcoming-title"
        >
          <div className="dashboard-section-heading">
            <div>
              <p className="eyebrow">Upcoming mocks</p>
              <h2 id="upcoming-title">What&apos;s ahead</h2>
            </div>
          </div>
          <div className="dashboard-upcoming__grid">
            {otherMocks.map((mock) => (
              <MockCard
                key={mock.id}
                mock={mock}
                serverTime={data.server_time}
              />
            ))}
          </div>
        </section>
      ) : null}
    </>
  );
}

export function DashboardPage() {
  const { user, logout, withAccess } = useAuth();
  const navigate = useNavigate();
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [data, setData] = useState<DashboardData>();
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const load = useMemo(() => () => dashboardApi(withAccess), [withAccess]);

  const refresh = () => {
    setLoading(true);
    setFailed(false);
    void load()
      .then(setData)
      .catch(() => setFailed(true))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    let active = true;
    void load()
      .then((response) => {
        if (active) setData(response);
      })
      .catch(() => {
        if (active) setFailed(true);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [load]);

  const handleLogout = async () => {
    setIsLoggingOut(true);
    try {
      await logout();
      navigate("/auth", { replace: true });
    } catch {
      setIsLoggingOut(false);
    }
  };

  return (
    <main className="dashboard-shell">
      <nav className="dashboard-nav" aria-label="Student navigation">
        <div className="brand-lockup brand-lockup--small">
          <img src={growthSathiLogo} alt="GrowthSathi" width="52" height="52" />
          <span>GrowthSathi</span>
        </div>
        <button
          className="secondary-button"
          onClick={handleLogout}
          disabled={isLoggingOut}
        >
          {isLoggingOut ? "Signing out…" : "Sign out"}
        </button>
      </nav>
      <div className="dashboard-content">
        {loading ? (
          <section
            className="dashboard-skeleton"
            aria-label="Loading dashboard"
            role="status"
          >
            <h1>
              Welcome, {user?.full_name || user?.first_name || "Student"}.
            </h1>
            <span />
            <span />
            <span />
          </section>
        ) : failed ? (
          <section className="dashboard-empty" role="alert">
            <h1>Dashboard unavailable</h1>
            <p>
              We couldn&apos;t load your dashboard. Check your connection and
              try again.
            </p>
            <button className="primary-button" onClick={refresh}>
              Try again
            </button>
          </section>
        ) : data ? (
          <DashboardContent
            data={data}
            name={user?.full_name || user?.first_name || "Student"}
          />
        ) : null}
      </div>
    </main>
  );
}
