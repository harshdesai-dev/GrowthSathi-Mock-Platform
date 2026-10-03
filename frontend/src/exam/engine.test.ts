import "fake-indexeddb/auto";
import { ApiError } from "../api/errors";
import { ExamEngine, ServerClock } from "./engine";
import { examDB } from "./storage";
import {
  blankAnswer,
  type AttemptState,
  type ExamApi,
  type Question,
} from "./api";

const state: AttemptState = {
  attempt_id: "a",
  mock_id: "m",
  mock_title: "JEE",
  status: "IN_PROGRESS",
  server_time: "2026-01-01T10:00:00Z",
  started_at: "2026-01-01T10:00:00Z",
  mock_starts_at: "2026-01-01T10:00:00Z",
  mock_ends_at: "2026-01-01T13:00:00Z",
  submitted_at: null,
  current_phase: { id: "p", name: "All subjects", order: 1 },
  phase_starts_at: "2026-01-01T10:00:00Z",
  phase_ends_at: "2026-01-01T13:00:00Z",
  can_submit: true,
  responses: [],
  saved_response_count: 0,
  answered_count: 0,
  question_count: 75,
};
const q: Question = {
  id: "q",
  phase_id: "p",
  question_number: 1,
  subject: "PHYSICS",
  question_type: "NUMERICAL",
  question_text_md: "Question",
  question_image_url: "",
  options: [],
};
function api(): ExamApi {
  return {
    info: vi.fn(),
    start: vi.fn(),
    state: vi.fn().mockResolvedValue(state),
    heartbeat: vi.fn().mockResolvedValue(state),
    paper: vi.fn().mockResolvedValue({ state, questions: [q] }),
    save: vi.fn().mockImplementation(async (_, answer) => ({
      response: answer,
      server_time: state.server_time,
      acknowledgement: "saved",
    })),
    submit: vi.fn().mockResolvedValue({
      ...state,
      status: "SUBMITTED",
      current_phase: null,
      responses: [],
    }),
  };
}
beforeEach(async () => {
  await (await examDB()).clear("answers");
});
afterEach(() => vi.restoreAllMocks());

test("server clock ignores browser wall-clock changes", () => {
  vi.spyOn(performance, "now").mockReturnValue(1000);
  const clock = new ServerClock();
  clock.sync(state.server_time, 900);
  vi.spyOn(Date, "now").mockReturnValue(0);
  vi.mocked(performance.now).mockReturnValue(2000);
  expect(clock.remaining(state.phase_ends_at)).toBe(10799);
});

test("failed network save remains durable and retries after reconnect", async () => {
  const backend = api();
  const engine = new ExamEngine("a", "u", backend);
  await engine.poll();
  vi.mocked(backend.save).mockRejectedValue(new TypeError("offline"));
  await engine.edit(q, { ...blankAnswer("q"), numeric_answer: "4" });
  await engine.flush();
  expect((await engine.store.list())[0].pending).toBe(true);
  engine.stop();
  const recovered = new ExamEngine("a", "u", api());
  await recovered.poll();
  await recovered.flush();
  expect(recovered.snapshot.entries[0].pending).toBe(false);
  recovered.stop();
});

test("stale write is not automatically rebased, later phase does not send closed queue", async () => {
  const backend = api();
  const engine = new ExamEngine("a", "u", backend);
  await engine.poll();
  vi.mocked(backend.save).mockRejectedValue(
    new ApiError(409, {
      error: { code: "stale_mutation", message: "Conflicting server answer" },
    }),
  );
  await engine.edit(q, { ...blankAnswer("q"), numeric_answer: "4" });
  await engine.flush();
  expect(engine.snapshot.entries[0].blocked).toContain("Conflicting");
  expect(backend.save).toHaveBeenCalledTimes(1);
  const math = {
    ...state,
    current_phase: { id: "math", name: "Math", order: 2 },
  };
  vi.mocked(backend.heartbeat).mockResolvedValue(math);
  vi.mocked(backend.paper).mockResolvedValue({ state: math, questions: [] });
  await engine.poll();
  await engine.flush();
  expect(backend.save).toHaveBeenCalledTimes(1);
  engine.stop();
});

test("submit flushes pending writes first and requires explicit fallback when offline", async () => {
  const backend = api();
  const engine = new ExamEngine("a", "u", backend);
  await engine.poll();
  await engine.store.edit("q", "p", {
    ...blankAnswer("q"),
    numeric_answer: "4",
  });
  vi.mocked(backend.save).mockRejectedValue(new TypeError("offline"));
  expect(await engine.submit()).toBe(false);
  expect(backend.submit).not.toHaveBeenCalled();
  expect(await engine.submit(true)).toBe(true);
  expect(engine.snapshot.state?.status).toBe("SUBMITTED");
  // A late IN_PROGRESS heartbeat cannot undo terminal state.
  await engine.poll();
  expect(engine.snapshot.state?.status).toBe("SUBMITTED");
  engine.stop();
});

test("storage failure is visible, never reported as saved", async () => {
  const backend = api();
  const engine = new ExamEngine("a", "u", backend);
  await engine.poll();
  vi.spyOn(engine.store, "edit").mockRejectedValue(new Error("QuotaExceeded"));
  await engine.edit(q, blankAnswer("q"));
  expect(engine.snapshot.storageFailed).toBe(true);
  expect(backend.save).not.toHaveBeenCalled();
  engine.stop();
});

test("hydrated pending answers and paper are published atomically on reopen", async () => {
  const engine = new ExamEngine("a", "u", api());
  await engine.store.edit("q", "p", {
    ...blankAnswer("q"),
    numeric_answer: "42",
  });
  const seen: string[] = [];
  const off = engine.subscribe(() => {
    if (engine.snapshot.questions.length)
      seen.push(engine.snapshot.entries[0]?.answer.numeric_answer ?? "MISSING");
  });
  await engine.poll();
  expect(seen).toEqual(["42"]);
  off();
  engine.stop();
});

test.each([30000, 300000])(
  "retains responses through a simulated %d ms network outage",
  async (duration) => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "performance"] });
    const backend = api();
    const engine = new ExamEngine("a", "u", backend);
    try {
      await engine.poll();
      vi.mocked(backend.save).mockRejectedValue(new TypeError("offline"));
      vi.mocked(backend.heartbeat).mockRejectedValue(new TypeError("offline"));
      await engine.edit(q, { ...blankAnswer("q"), numeric_answer: "7" });
      await engine.flush();
      await vi.advanceTimersByTimeAsync(duration);
      expect((await engine.store.list())[0].answer.numeric_answer).toBe("7");
      const recovered = {
        ...state,
        server_time: new Date(
          Date.parse(state.server_time) + duration,
        ).toISOString(),
      };
      vi.mocked(backend.heartbeat).mockResolvedValue(recovered);
      vi.mocked(backend.save).mockImplementation(async (_, answer) => ({
        response: answer,
        server_time: recovered.server_time,
        acknowledgement: "saved",
      }));
      await engine.poll();
      await engine.flush();
      expect(engine.snapshot.entries[0].pending).toBe(false);
      expect(engine.clock.remaining(state.phase_ends_at)).toBe(
        10800 - duration / 1000,
      );
    } finally {
      engine.stop();
      vi.useRealTimers();
    }
  },
);
