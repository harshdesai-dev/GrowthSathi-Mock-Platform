import {
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type PropsWithChildren,
} from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useAuth } from "../auth/auth-context";
import logo from "../assets/brand/growthsathi-logo.png";
import {
  examApi,
  type Answer,
  type ExamInfo,
  type Question,
} from "../exam/api";
import { ExamEngine } from "../exam/engine";
import { displayedAnswer, type LocalAnswer } from "../exam/storage";
import { Markdown } from "../exam/Markdown";
import { safeImage } from "../exam/urls";
import "../styles/exam.css";

function time(value: number) {
  return `${Math.floor(value / 3600)
    .toString()
    .padStart(2, "0")}:${Math.floor((value % 3600) / 60)
    .toString()
    .padStart(2, "0")}:${(value % 60).toString().padStart(2, "0")}`;
}
function date(value: string) {
  return `${new Date(value).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })} IST`;
}
function Brand() {
  return (
    <div className="exam-brand">
      <img src={logo} width="40" height="40" alt="GrowthSathi" />
      <span>
        GrowthSathi<span className="exam-brand-label">MOCK PLATFORM</span>
      </span>
    </div>
  );
}
function Dialog({
  title,
  close,
  children,
  drawer = false,
}: PropsWithChildren<{ title: string; close: () => void; drawer?: boolean }>) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className={`exam-dialog${drawer ? " exam-drawer" : ""}`}
      aria-label={title}
      onCancel={(event) => {
        event.preventDefault();
        close();
      }}
    >
      <header>
        <h2>{title}</h2>
        <button type="button" onClick={close} aria-label="Close dialog">
          ×
        </button>
      </header>
      {children}
    </dialog>
  );
}

export function ExamInstructionsPage() {
  const { mockId = "" } = useParams();
  const { withAccess } = useAuth();
  const navigate = useNavigate();
  const api = useMemo(() => examApi(withAccess), [withAccess]);
  const [info, setInfo] = useState<ExamInfo>();
  const [error, setError] = useState("");
  const [accepted, setAccepted] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    const refresh = () =>
      void api
        .info(mockId)
        .then((data) => {
          if (active) {
            setInfo(data);
            setError("");
          }
        })
        .catch((error: unknown) => {
          if (active)
            setError(
              error instanceof Error ? error.message : "Unable to connect.",
            );
        });
    refresh();
    const timer = setInterval(refresh, 30000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [api, mockId]);
  const start = async () => {
    setBusy(true);
    try {
      const state = await api.start(mockId);
      navigate(`/exam/${state.attempt_id}`);
    } catch (error) {
      setError(
        error instanceof Error ? error.message : "Unable to start. Retry.",
      );
    } finally {
      setBusy(false);
    }
  };
  return (
    <main className="exam-welcome">
      <Brand />
      <Link to="/dashboard">← My account</Link>
      <p className="eyebrow">Before you begin</p>
      <h1>{info?.title ?? "Preparing your mock"}</h1>
      {error && (
        <p role="alert" className="exam-warning">
          {error}
        </p>
      )}
      {info && (
        <>
          <div className="exam-schedule">
            <div>
              <span>Global start</span>
              <strong>{date(info.starts_at)}</strong>
            </div>
            <div>
              <span>Global end</span>
              <strong>{date(info.ends_at)}</strong>
            </div>
          </div>
          <h2>One schedule. Everyone together.</h2>
          <p>
            Joining late gives you only the time remaining. Refreshing or
            reopening your browser never resets the clock.
          </p>
          <ol>
            {info.phases.map((phase) => (
              <li key={phase.order}>
                {phase.name}: minute {phase.start_offset_minutes}–
                {phase.start_offset_minutes + phase.duration_minutes} from the
                global start.
              </li>
            ))}
          </ol>
          {info.phases.length > 1 && (
            <p>
              Physics/Chemistry closes at minute 90. Mathematics unlocks then,
              even if you started late. You cannot return to a closed phase or
              unlock Mathematics early.
            </p>
          )}
          <Markdown text={info.instructions_md} />
          <ul>
            <li>
              Answers are saved on this device first, then synchronized to the
              server.
            </li>
            <li>
              Only answers accepted by the server before their phase deadline
              count. Offline answers arriving later are not accepted.
            </li>
            <li>
              Use one tab and one device. Do not clear browser storage during
              your exam.
            </li>
            <li>
              Allow a stable connection and keep this page open. If your session
              expires, sign in again and return here.
            </li>
          </ul>
          {info.attempt_id ? (
            <Link className="primary-button" to={`/exam/${info.attempt_id}`}>
              {info.attempt_status === "IN_PROGRESS"
                ? "Resume exam"
                : "View submission status"}
            </Link>
          ) : (
            <>
              <label className="exam-consent">
                <input
                  type="checkbox"
                  checked={accepted}
                  onChange={(event) => setAccepted(event.target.checked)}
                />{" "}
                I understand the schedule and server-save rules.
              </label>
              <button
                className="primary-button"
                disabled={!accepted || !info.can_start || busy}
                onClick={() => void start()}
              >
                {busy ? "Starting securely…" : "Start exam"}
              </button>
              {!info.can_start && (
                <p role="status">
                  The server has not opened this exam for starting, or its
                  window has ended. Availability refreshes every 30 seconds.
                </p>
              )}
            </>
          )}
        </>
      )}
    </main>
  );
}

function Palette({
  questions,
  entries,
  current,
  choose,
}: {
  questions: Question[];
  entries: LocalAnswer[];
  current: string;
  choose: (id: string) => void;
}) {
  const groups = [...new Set(questions.map((q) => q.subject))];
  return (
    <>
      <h2>Question palette</h2>
      {groups.map((subject) => (
        <section key={subject}>
          <h3>{subject.replaceAll("_", " ")}</h3>
          <div className="exam-palette">
            {questions
              .filter((q) => q.subject === subject)
              .map((q) => {
                const entry = entries.find(
                  (e) => e.answer.question_id === q.id,
                );
                const answer = displayedAnswer(entry, q.id);
                const status = answer.marked_for_review
                  ? "review"
                  : answer.selected_option || answer.numeric_answer
                    ? "answered"
                    : entry
                      ? "visited"
                      : "unvisited";
                return (
                  <button
                    key={q.id}
                    className={`palette-${status}`}
                    aria-label={`Question ${q.question_number}, ${status}${entry?.pending ? ", not synchronized" : ""}`}
                    aria-current={current === q.id ? "true" : undefined}
                    onClick={() => choose(q.id)}
                  >
                    {q.question_number}
                    {entry?.pending && <span aria-hidden="true">•</span>}
                  </button>
                );
              })}
          </div>
        </section>
      ))}
      <div className="exam-legend">
        <span>○ Not visited</span>
        <span>◑ Visited, unanswered</span>
        <span className="legend-answered">● Answered</span>
        <span className="legend-review">◆ Marked for review</span>
        <span>• Device-only change</span>
      </div>
    </>
  );
}

function QuestionBody({
  question,
  answer: persisted,
  disabled,
  change,
}: {
  question: Question;
  answer: Answer;
  disabled: boolean;
  change: (answer: Answer) => Promise<void>;
}) {
  const [optimistic, setOptimistic] = useState<Answer | null>(null);
  const editSequence = useRef(0);
  const answer = optimistic ?? persisted;
  const edit = (next: Answer) => {
    const sequence = ++editSequence.current;
    setOptimistic(next);
    void change(next).finally(() => {
      if (editSequence.current === sequence) setOptimistic(null);
    });
  };
  return (
    <>
      <Markdown text={question.question_text_md} />
      {safeImage(question.question_image_url) && (
        <img
          className="exam-diagram"
          loading="lazy"
          src={safeImage(question.question_image_url)}
          alt={`Diagram for question ${question.question_number}`}
          referrerPolicy="no-referrer"
        />
      )}
      {question.question_type === "MCQ_SINGLE" ? (
        <fieldset className="exam-options" disabled={disabled}>
          <legend className="sr-only">Choose one answer</legend>
          {question.options.map((option) => (
            <label
              key={option.id}
              className={
                answer.selected_option === option.id ? "option-selected" : ""
              }
            >
              <input
                type="radio"
                name={`question-${question.id}`}
                value={option.id}
                checked={answer.selected_option === option.id}
                onChange={() => edit({ ...answer, selected_option: option.id })}
              />
              <span className="option-letter">{option.label}</span>
              <div>
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
            </label>
          ))}
        </fieldset>
      ) : (
        <label className="exam-numeric">
          Numerical answer
          <input
            type="text"
            inputMode="decimal"
            autoComplete="off"
            maxLength={32}
            disabled={disabled}
            value={answer.numeric_answer}
            onChange={(event) =>
              edit({ ...answer, numeric_answer: event.target.value })
            }
            aria-describedby="numeric-help"
          />
          <span id="numeric-help">
            Use decimal notation, not fractions or scientific notation. Up to 12
            integer and 8 decimal digits.
          </span>
        </label>
      )}
      <div className="exam-secondary-actions">
        <button
          disabled={disabled}
          onClick={() =>
            edit({ ...answer, selected_option: null, numeric_answer: "" })
          }
        >
          Clear response
        </button>
        <button
          disabled={disabled}
          aria-pressed={answer.marked_for_review}
          onClick={() =>
            edit({ ...answer, marked_for_review: !answer.marked_for_review })
          }
        >
          {answer.marked_for_review ? "Unmark review" : "Mark for review"}
        </button>
      </div>
    </>
  );
}

export function ExamPage() {
  const { attemptId = "" } = useParams();
  const { user, withAccess } = useAuth();
  const engine = useMemo(
    () => new ExamEngine(attemptId, user?.id ?? "", examApi(withAccess)),
    [attemptId, user?.id, withAccess],
  );
  const snapshot = useSyncExternalStore(engine.subscribe, engine.getSnapshot);
  const { state, questions, entries } = snapshot;
  const [selected, setSelected] = useState("");
  const [drawer, setDrawer] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [serverOnly, setServerOnly] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [, tick] = useState(0);
  const question = questions.find((q) => q.id === selected) ?? questions[0];
  const remaining = engine.clock.remaining(state?.phase_ends_at ?? null);
  const pending = entries.filter((e) => e.pending).length;
  const blocked = entries.filter((e) => e.pending && e.blocked).length;
  const disabled =
    !remaining || submitting || confirm || snapshot.storageFailed;
  useEffect(() => {
    engine.start();
    const interval = setInterval(() => {
      tick((v) => v + 1);
    }, 1000);
    const heartbeat = setInterval(() => {
      void engine.poll().then(() => engine.flush());
    }, 30000);
    const reconnect = () => {
      if (document.visibilityState === "visible")
        void engine.poll().then(() => engine.flush());
    };
    window.addEventListener("online", reconnect);
    window.addEventListener("pageshow", reconnect);
    document.addEventListener("visibilitychange", reconnect);
    return () => {
      engine.stop();
      clearInterval(interval);
      clearInterval(heartbeat);
      window.removeEventListener("online", reconnect);
      window.removeEventListener("pageshow", reconnect);
      document.removeEventListener("visibilitychange", reconnect);
    };
  }, [engine]);
  useEffect(() => {
    if (state?.status === "IN_PROGRESS" && remaining === 0) {
      void engine.poll();
      const timer = setInterval(() => void engine.poll(), 5000);
      return () => clearInterval(timer);
    }
  }, [engine, remaining, state?.status]);
  useEffect(() => {
    if (!question) return;
    const existing = engine.snapshot.entries.find(
      (e) => e.answer.question_id === question.id,
    );
    if (!existing)
      void engine.edit(question, displayedAnswer(undefined, question.id));
  }, [engine, question]);
  useEffect(() => {
    if (!pending) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [pending]);
  const retry = () => void engine.poll().then(() => engine.flush());
  const choose = (id: string) => {
    setSelected(id);
    setDrawer(false);
  };
  const submit = async (onlySaved = false) => {
    setSubmitting(true);
    const ok = await engine.submit(onlySaved);
    if (ok) {
      setConfirm(false);
      setServerOnly(false);
    } else setServerOnly(true);
    setSubmitting(false);
  };
  const palette = question && (
    <Palette
      questions={questions}
      entries={entries}
      current={question.id}
      choose={choose}
    />
  );
  if (state && state.status !== "IN_PROGRESS")
    return (
      <main className="exam-welcome">
        <Brand />
        <p className="eyebrow">Exam closed</p>
        <h1>
          {state.status === "INVALID"
            ? "Attempt unavailable"
            : state.status === "AUTO_SUBMITTED"
              ? "Time is up. Attempt closed."
              : "Your attempt is submitted."}
        </h1>
        <p>{state.mock_title}</p>
        <p>Server status: {state.status}</p>
        <p>
          {state.answered_count} answered · {state.saved_response_count} visited
          responses saved on the server.
        </p>
        <p>
          Only answers accepted before their phase deadline were retained.
          Results are not available here.
        </p>
        {pending > 0 && (
          <p className="exam-warning">
            {pending} device-only changes were not accepted. They cannot be
            added after closure.
          </p>
        )}
        <Link to="/dashboard" className="primary-button">
          Back to my account
        </Link>
      </main>
    );
  return (
    <main className="exam-shell">
      <header className="exam-topbar">
        <Brand />
        <div className="exam-title">
          <strong>{state?.mock_title ?? "Connecting to your exam"}</strong>
          <span>{state?.current_phase?.name ?? "Restoring server state"}</span>
        </div>
        <div className="exam-clock">
          <span>PHASE TIME LEFT</span>
          <strong role="timer" aria-label="Phase time remaining">
            {state ? time(remaining) : "--:--:--"}
          </strong>
          <small>Server synchronized</small>
        </div>
      </header>
      <div className="exam-sync" role="status">
        <span
          className={snapshot.connected ? "sync-dot" : "sync-dot offline"}
        />
        {snapshot.syncing
          ? "Synchronizing…"
          : !snapshot.connected
            ? "Connection interrupted"
            : pending
              ? `${pending} change${pending === 1 ? "" : "s"} saved on device, not on server`
              : "All changes saved on server"}
        <button onClick={retry}>Retry sync</button>
        <span className="exam-user">{user?.full_name}</span>
      </div>
      {snapshot.message && (
        <div className="exam-warning" role="alert">
          {snapshot.message}
          {snapshot.message.startsWith("Session expired") && (
            <>
              {" "}
              <Link to="/auth" target="_blank">
                Sign in again
              </Link>
            </>
          )}
        </div>
      )}
      {blocked > 0 && (
        <div className="exam-warning" role="alert">
          {blocked} change(s) could not be accepted. Closed-phase changes cannot
          be resent. For an active-phase conflict, select your answer again
          after checking the server answer shown.
        </div>
      )}
      {state && !remaining && (
        <div className="exam-warning" role="status">
          This phase's time has elapsed. Checking the server for the next phase
          or final closure…
        </div>
      )}
      <div className="exam-layout">
        <section className="exam-main">
          {question ? (
            <>
              <nav className="exam-subjects" aria-label="Active subjects">
                {[...new Set(questions.map((q) => q.subject))].map(
                  (subject) => (
                    <button
                      key={subject}
                      aria-current={
                        question.subject === subject ? "page" : undefined
                      }
                      onClick={() =>
                        choose(questions.find((q) => q.subject === subject)!.id)
                      }
                    >
                      {subject.replaceAll("_", " ")}
                    </button>
                  ),
                )}
              </nav>
              <div className="exam-question-heading">
                <div>
                  <p className="eyebrow">
                    {question.question_type === "MCQ_SINGLE"
                      ? "Single correct option"
                      : "Numerical response"}
                  </p>
                  <h1>Question {question.question_number}</h1>
                </div>
                <button
                  className="mobile-palette-toggle"
                  onClick={() => setDrawer(true)}
                >
                  Questions ▦
                </button>
              </div>
              <article className="exam-question">
                <QuestionBody
                  key={question.id}
                  question={question}
                  answer={displayedAnswer(
                    entries.find((e) => e.answer.question_id === question.id),
                    question.id,
                  )}
                  disabled={disabled}
                  change={(answer) => engine.edit(question, answer)}
                />
                {entries.find((e) => e.answer.question_id === question.id)
                  ?.blocked && (
                  <p role="alert" className="exam-warning">
                    {
                      entries.find((e) => e.answer.question_id === question.id)
                        ?.blocked
                    }
                  </p>
                )}
              </article>
              <footer className="exam-actions">
                <button
                  disabled={questions.indexOf(question) === 0}
                  onClick={() =>
                    choose(questions[questions.indexOf(question) - 1].id)
                  }
                >
                  ← Previous
                </button>
                <button
                  className="primary-button"
                  onClick={() => {
                    void engine.flush();
                    choose(
                      questions[
                        (questions.indexOf(question) + 1) % questions.length
                      ].id,
                    );
                  }}
                >
                  Save &amp; next →
                </button>
              </footer>
            </>
          ) : (
            <p className="exam-loading">
              {snapshot.message || "Loading the current phase securely…"}
            </p>
          )}
          <div className="exam-submit-area">
            <p>
              {state?.can_submit
                ? "Finished? Submission is final. Check your sync status first."
                : "Final submission becomes available in the final phase. The global schedule cannot be advanced."}
            </p>
            <button
              className="secondary-button"
              disabled={!state?.can_submit || !remaining || submitting}
              onClick={() => {
                setConfirm(true);
                setServerOnly(false);
              }}
            >
              Submit exam
            </button>
          </div>
        </section>
        <aside className="exam-sidebar">
          {palette}
          <p>Only this phase is available. Closed phases cannot be reopened.</p>
        </aside>
      </div>
      {drawer && (
        <Dialog title="Questions" drawer close={() => setDrawer(false)}>
          {palette}
        </Dialog>
      )}
      {confirm && (
        <Dialog
          title="Submit your exam?"
          close={() => {
            if (!submitting) setConfirm(false);
          }}
        >
          <p>
            Submission is final. We will first try to synchronize all pending
            responses.
          </p>
          <p>
            {pending} pending device changes. Only server-accepted answers will
            be submitted.
          </p>
          {serverOnly && (
            <p className="exam-warning">
              Synchronization or submission could not be confirmed. You can
              retry, keep working, or submit only the responses already on the
              server. The deadline is unchanged.
            </p>
          )}
          <div className="exam-dialog-actions">
            <button disabled={submitting} onClick={() => setConfirm(false)}>
              Keep working
            </button>
            <button
              className="primary-button"
              disabled={submitting}
              onClick={() => void submit()}
            >
              {submitting ? "Confirming with server…" : "Sync & submit"}
            </button>
            {serverOnly && (
              <button disabled={submitting} onClick={() => void submit(true)}>
                Submit server-saved answers only
              </button>
            )}
          </div>
        </Dialog>
      )}
    </main>
  );
}
