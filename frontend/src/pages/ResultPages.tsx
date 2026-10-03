import { useEffect, useMemo, useState, type PropsWithChildren } from "react";
import { Link, useParams } from "react-router-dom";
import { resultsApi, type ReviewQuestion } from "../api/results";
import { useAuth } from "../auth/auth-context";
import logo from "../assets/brand/growthsathi-logo.png";
import { Markdown } from "../exam/Markdown";
import { safeImage } from "../exam/urls";
import "../styles/results.css";
import { difference, marks } from "../results/format";
function date(value: string) {
  return new Date(value).toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "Asia/Kolkata",
  });
}
function Shell({ children }: PropsWithChildren) {
  return (
    <main className="results-shell">
      <nav className="results-nav" aria-label="Results navigation">
        <Link to="/dashboard" className="results-brand">
          <img src={logo} alt="GrowthSathi" width="44" height="44" />
          <span>
            GrowthSathi<small>MOCK PLATFORM</small>
          </span>
        </Link>
        <Link to="/results">Result history</Link>
      </nav>
      {children}
      <footer>
        Mock Percentile compares participants in this mock only. It is not
        official NTA or CET normalization.
      </footer>
    </main>
  );
}
function useResultData<T>(load: () => Promise<T>) {
  const [state, setState] = useState<{
    data?: T;
    error?: string;
    loading: boolean;
  }>({ loading: true });
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    void load()
      .then((data) => {
        if (active) setState({ data, loading: false });
      })
      .catch((error: unknown) => {
        if (active)
          setState({
            error:
              error instanceof Error
                ? error.message
                : "Results could not be loaded.",
            loading: false,
          });
      });
    return () => {
      active = false;
    };
  }, [load, retry]);
  return {
    ...state,
    retry: () => {
      setState({ loading: true });
      setRetry((value) => value + 1);
    },
  };
}
function Status({
  loading,
  error,
  retry,
}: {
  loading: boolean;
  error?: string;
  retry: () => void;
}) {
  if (loading)
    return (
      <p className="results-empty" role="status">
        Loading published results…
      </p>
    );
  if (error)
    return (
      <section className="results-empty">
        <h1>Results unavailable</h1>
        <p role="alert">{error}</p>
        <p>
          Results, rankings and answers appear only after Admin publishes the
          verified batch.
        </p>
        <button className="secondary-button" onClick={retry}>
          Check again
        </button>
        <Link to="/dashboard">Back to my account</Link>
      </section>
    );
  return null;
}
function useApi() {
  const { withAccess } = useAuth();
  return useMemo(() => resultsApi(withAccess), [withAccess]);
}
export function ResultPage() {
  const { mockId = "" } = useParams();
  return <ReportContent key={mockId} mockId={mockId} />;
}
function ReportContent({ mockId }: { mockId: string }) {
  const api = useApi();
  const load = useMemo(() => () => api.report(mockId), [api, mockId]);
  const state = useResultData(load);
  const result = state.data;
  return (
    <Shell>
      <Status {...state} />
      {result && (
        <>
          <header className="results-heading">
            <p className="eyebrow">Your mock report card</p>
            <h1>{result.mock_title}</h1>
            <p>
              {result.exam} <span aria-hidden="true">·</span>{" "}
              {date(result.starts_at)} IST
            </p>
            <p className="results-student">{result.student_name}</p>
          </header>
          <section className="results-score" aria-label="Score and standing">
            <div className="results-main-score">
              <p>Your score</p>
              <strong>
                {marks(result.score)}
                <span> / {marks(result.maximum_score)}</span>
              </strong>
              <small>marks</small>
            </div>
            <dl>
              <div>
                <dt>Rank</dt>
                <dd>#{result.rank}</dd>
              </div>
              <div>
                <dt>Mock Percentile</dt>
                <dd>{result.percentile}</dd>
              </div>
            </dl>
          </section>
          <dl className="results-counts">
            <div>
              <dt>Correct</dt>
              <dd>{result.correct_count}</dd>
            </div>
            <div>
              <dt>Incorrect</dt>
              <dd>{result.incorrect_count}</dd>
            </div>
            <div>
              <dt>Attempted</dt>
              <dd>{result.attempted_count}</dd>
            </div>
            <div>
              <dt>Unattempted</dt>
              <dd>{result.unattempted_count}</dd>
            </div>
          </dl>
          <section className="results-comparison">
            <h2>Your previous score</h2>
            {result.previous_score !== null &&
            result.score_difference !== null ? (
              <>
                <p>Most recent earlier published {result.exam} mock</p>
                <dl>
                  <div>
                    <dt>Previous score</dt>
                    <dd>{marks(result.previous_score)}</dd>
                  </div>
                  <div>
                    <dt>Current score</dt>
                    <dd>{marks(result.score)}</dd>
                  </div>
                  <div>
                    <dt>Difference</dt>
                    <dd>{difference(result.score_difference)} marks</dd>
                  </div>
                </dl>
              </>
            ) : (
              <p>
                This is your first published result for this exam. Your next
                published mock can be compared here.
              </p>
            )}
          </section>
          <div className="results-actions">
            <Link className="primary-button" to={`/results/${mockId}/review`}>
              Review Answers <span aria-hidden="true">↗</span>
            </Link>
            <Link
              className="secondary-button"
              to={`/results/${mockId}/leaderboard`}
            >
              View Leaderboard
            </Link>
          </div>
        </>
      )}
    </Shell>
  );
}
export function LeaderboardPage() {
  const { mockId = "" } = useParams();
  return <LeaderboardContent key={mockId} mockId={mockId} />;
}
function LeaderboardContent({ mockId }: { mockId: string }) {
  const api = useApi();
  const load = useMemo(() => () => api.leaderboard(mockId), [api, mockId]);
  const state = useResultData(load);
  return (
    <Shell>
      <Status {...state} />
      {state.data && (
        <>
          <header className="results-heading">
            <p className="eyebrow">Published standings</p>
            <h1>Mock leaderboard</h1>
            <p>{state.data.mock_title}</p>
            <Link to={`/results/${mockId}`}>Back to my report card</Link>
          </header>
          <div className="results-table-wrap">
            <table className="results-table">
              <caption>Competition ranks · tied scores share a rank</caption>
              <thead>
                <tr>
                  <th scope="col">Rank</th>
                  <th scope="col">Student</th>
                  <th scope="col">Score</th>
                  <th scope="col">Mock Percentile</th>
                </tr>
              </thead>
              <tbody>
                {state.data.rows.map((row, index) => (
                  <tr key={index}>
                    <td>#{row.rank}</td>
                    <td>{row.name}</td>
                    <td>{marks(row.score)}</td>
                    <td>{row.percentile}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {state.data.rows.length === 0 && (
              <p className="results-empty">
                No eligible participants in this mock.
              </p>
            )}
          </div>
        </>
      )}
    </Shell>
  );
}
function Answer({
  question,
  correct = false,
}: {
  question: ReviewQuestion;
  correct?: boolean;
}) {
  if (question.question_type === "NUMERICAL")
    return (
      <p className="results-numeric">
        {(correct
          ? question.correct_numeric_answer
          : question.numeric_answer) || "Not answered"}
        {correct && (
          <small>Absolute tolerance: {question.numeric_tolerance}</small>
        )}
      </p>
    );
  const option = question.options.find(
    (item) =>
      item.id ===
      (correct ? question.correct_option : question.selected_option),
  );
  return option ? (
    <div>
      <strong>Option {option.label}</strong>
      <Markdown text={option.option_text_md} />
      {safeImage(option.option_image_url) && (
        <img
          src={safeImage(option.option_image_url)}
          alt={`Option ${option.label} diagram`}
          loading="lazy"
          referrerPolicy="no-referrer"
        />
      )}
    </div>
  ) : (
    <p>Not answered</p>
  );
}
export function ReviewPage() {
  const { mockId = "" } = useParams();
  return <ReviewContent key={mockId} mockId={mockId} />;
}
function ReviewContent({ mockId }: { mockId: string }) {
  const api = useApi();
  const load = useMemo(() => () => api.review(mockId), [api, mockId]);
  const state = useResultData(load);
  return (
    <Shell>
      <Status {...state} />
      {state.data && (
        <>
          <header className="results-heading">
            <p className="eyebrow">Published answer review</p>
            <h1>Review your answers</h1>
            <p>{state.data.mock_title}</p>
            <Link to={`/results/${mockId}`}>Back to report card</Link>
          </header>
          <div className="results-review-list">
            {state.data.questions.map((question) => (
              <article className="results-review" key={question.id}>
                <header>
                  <h2>Question {question.question_number}</h2>
                  <span
                    className={`results-outcome results-outcome--${question.outcome.toLowerCase()}`}
                  >
                    {question.outcome} · {marks(question.marks)} marks
                  </span>
                </header>
                <Markdown text={question.question_text_md} />
                {safeImage(question.question_image_url) && (
                  <img
                    src={safeImage(question.question_image_url)}
                    alt={`Question ${question.question_number} diagram`}
                    loading="lazy"
                    referrerPolicy="no-referrer"
                  />
                )}
                <div className="results-answer-grid">
                  <section>
                    <h3>Your answer</h3>
                    <Answer question={question} />
                  </section>
                  <section>
                    <h3>Correct answer</h3>
                    <Answer question={question} correct />
                  </section>
                </div>
                <section className="results-explanation">
                  <h3>Explanation</h3>
                  <Markdown
                    text={
                      question.explanation_md ||
                      "No explanation has been supplied."
                    }
                  />
                </section>
              </article>
            ))}
          </div>
        </>
      )}
    </Shell>
  );
}
export function ResultHistoryPage() {
  const api = useApi();
  const state = useResultData(api.history);
  return (
    <Shell>
      <Status {...state} />
      {state.data && (
        <>
          <header className="results-heading">
            <p className="eyebrow">Your published mocks</p>
            <h1>Result history</h1>
            <p>Private report cards from your completed mocks.</p>
          </header>
          {state.data.length === 0 ? (
            <p className="results-empty">
              No published results yet. Completed mocks will appear after Admin
              publishes their results.
            </p>
          ) : (
            <ul className="results-history">
              {state.data.map((result) => (
                <li key={result.mock_id}>
                  <div>
                    <p className="eyebrow">
                      {result.exam} · {date(result.starts_at)}
                    </p>
                    <h2>
                      <Link to={`/results/${result.mock_id}`}>
                        {result.mock_title}
                      </Link>
                    </h2>
                    <p>
                      Rank #{result.rank} · Mock Percentile {result.percentile}
                    </p>
                  </div>
                  <strong>
                    {marks(result.score)}
                    <small> / {marks(result.maximum_score)}</small>
                  </strong>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </Shell>
  );
}
