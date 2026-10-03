import { ApiError } from "../api/errors";
import {
  type AnswerInput,
  type AttemptState,
  type ExamApi,
  type Question,
} from "./api";
import { AnswerStore, type LocalAnswer } from "./storage";

export class ServerClock {
  private server = 0;
  private received = 0;
  sync(iso: string, requestStarted: number) {
    this.received = performance.now();
    // Full RTT is deliberately conservative: it may disable slightly early, never grants time.
    this.server = Date.parse(iso) + Math.max(0, this.received - requestStarted);
  }
  now() {
    return this.server + Math.max(0, performance.now() - this.received);
  }
  remaining(deadline: string | null) {
    return deadline
      ? Math.max(0, Math.ceil((Date.parse(deadline) - this.now()) / 1000))
      : 0;
  }
}
export interface ExamSnapshot {
  state?: AttemptState;
  questions: Question[];
  entries: LocalAnswer[];
  message: string;
  syncing: boolean;
  storageFailed: boolean;
  connected: boolean;
}

export class ExamEngine {
  readonly clock = new ServerClock();
  readonly store: AnswerStore;
  snapshot: ExamSnapshot = {
    questions: [],
    entries: [],
    message: "Connecting to exam server…",
    syncing: false,
    storageFailed: false,
    connected: false,
  };
  private listeners = new Set<() => void>();
  private flushing?: Promise<boolean>;
  private polling?: Promise<void>;
  private retry?: ReturnType<typeof setTimeout>;
  private failures = 0;
  private stopped = false;
  private editing: Promise<void> = Promise.resolve();
  constructor(
    readonly id: string,
    user: string,
    private api: ExamApi,
  ) {
    this.store = new AnswerStore(`${user}/${id}`);
  }
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  getSnapshot = () => this.snapshot;
  private publish(next: Partial<ExamSnapshot>) {
    this.snapshot = { ...this.snapshot, ...next };
    this.listeners.forEach((listener) => listener());
  }
  private async local() {
    this.publish({ entries: await this.store.list() });
  }
  private fail(error: unknown) {
    const auth = error instanceof ApiError && error.status === 401;
    this.publish({
      connected: false,
      message: auth
        ? "Session expired. Sign in again in another tab, then retry. Device answers are retained."
        : error instanceof ApiError && error.status < 500
          ? error.message
          : "Connection interrupted. Device answers will retry; only server-accepted answers count.",
    });
  }
  private schedule() {
    if (this.stopped || this.retry) return;
    const delay =
      Math.min(30000, 1000 * 2 ** Math.min(this.failures++, 5)) +
      Math.random() * 500;
    this.retry = setTimeout(() => {
      this.retry = undefined;
      void this.poll().then(() => this.flush());
    }, delay);
  }
  private async apply(
    state: AttemptState,
    requested: number,
    questions?: Question[],
  ) {
    const previous = this.snapshot.state;
    if (
      previous &&
      previous.status !== "IN_PROGRESS" &&
      state.status === "IN_PROGRESS"
    )
      return;
    if (
      previous?.current_phase &&
      state.current_phase &&
      previous.current_phase.order > state.current_phase.order
    )
      return;
    this.clock.sync(state.server_time, requested);
    const phase = state.current_phase?.id ?? null;
    for (const answer of state.responses)
      await this.store.accept(answer, phase ?? "");
    await this.store.closeOtherPhases(phase);
    const changed = phase !== this.snapshot.state?.current_phase?.id;
    // Publish paper and hydrated IndexedDB state together. Otherwise the visit effect
    // can mistake a recovering queued answer for an unvisited question and clear it.
    const entries = await this.store.list();
    this.publish({
      state,
      entries,
      questions: questions ?? (changed ? [] : this.snapshot.questions),
      connected: true,
      message: "",
    });
  }
  poll = (): Promise<void> => {
    if (this.polling) return this.polling;
    this.polling = this.pollOnce().finally(() => {
      this.polling = undefined;
    });
    return this.polling;
  };
  private async pollOnce() {
    try {
      let requested = performance.now();
      let state = await this.api.heartbeat(this.id);
      let questions: Question[] | undefined;
      if (
        state.status === "IN_PROGRESS" &&
        (!this.snapshot.questions.length ||
          state.current_phase?.id !== this.snapshot.state?.current_phase?.id)
      ) {
        requested = performance.now();
        const paper = await this.api.paper(this.id);
        state = paper.state;
        questions = paper.questions;
      }
      await this.apply(state, requested, questions);
      this.failures = 0;
    } catch (error) {
      this.fail(error);
      this.schedule();
    }
  }
  async edit(question: Question, input: AnswerInput) {
    if (
      this.snapshot.state?.status !== "IN_PROGRESS" ||
      !this.clock.remaining(this.snapshot.state.phase_ends_at)
    )
      return;
    this.editing = this.editing.then(async () => {
      try {
        await this.store.edit(question.id, question.phase_id, input);
        await this.local();
        this.publish({ storageFailed: false });
      } catch {
        this.publish({
          storageFailed: true,
          message:
            "Device storage failed. Answers are NOT safely saved. Free storage or use a supported browser, then retry.",
        });
      }
    });
    await this.editing;
    void this.flush();
  }
  flush = (): Promise<boolean> => {
    if (this.flushing) return this.flushing;
    this.flushing = this.flushOnce().finally(() => {
      this.flushing = undefined;
      this.publish({ syncing: false });
    });
    return this.flushing;
  };
  private async flushOnce() {
    this.publish({ syncing: true });
    try {
      // Re-read after each acknowledgement so edits made during an in-flight save are sent next.
      while (!this.stopped) {
        await this.editing;
        const entries = await this.store.list();
        const phase = this.snapshot.state?.current_phase?.id;
        const next = entries.find(
          (entry) => entry.pending && !entry.blocked && entry.phase === phase,
        );
        if (!next) {
          await this.local();
          return !entries.some((entry) => entry.pending);
        }
        if (!this.clock.remaining(this.snapshot.state?.phase_ends_at ?? null)) {
          await this.poll();
          return false;
        }
        if (
          next.answer.numeric_answer &&
          !/^[+-]?(?:\d{1,12}(?:\.\d{0,8})?|\.\d{1,8})$/.test(
            next.answer.numeric_answer,
          )
        ) {
          await this.store.block(
            next.answer.question_id,
            next.answer.mutation_version,
            "Finish entering a valid decimal (12 integer / 8 decimal digits maximum).",
          );
          await this.local();
          continue;
        }
        try {
          const saved = await this.api.save(this.id, next.answer);
          await this.store.acknowledge(next.answer, saved.response, next.phase);
          this.publish({ connected: true, message: "" });
          this.failures = 0;
        } catch (error) {
          if (
            error instanceof ApiError &&
            [400, 403, 404, 409].includes(error.status)
          ) {
            await this.store.block(
              next.answer.question_id,
              next.answer.mutation_version,
              error.message,
            );
            await this.poll();
          } else {
            this.fail(error);
            this.schedule();
            return false;
          }
        }
        await this.local();
      }
    } catch {
      this.publish({
        storageFailed: true,
        message:
          "Cannot read device storage. Do not close this page; retry after checking browser storage.",
      });
    }
    return false;
  }
  async submit(serverOnly = false) {
    await this.editing;
    if (!serverOnly && !(await this.flush())) return false;
    if (
      !serverOnly &&
      (this.snapshot.storageFailed ||
        (await this.store.list()).some((entry) => entry.pending))
    )
      return false;
    const requested = performance.now();
    try {
      const state = await this.api.submit(this.id);
      await this.apply(state, requested);
      return true;
    } catch (error) {
      this.fail(error);
      await this.poll();
      return false;
    }
  }
  start() {
    this.stopped = false;
    void this.poll().then(() => this.flush());
  }
  stop() {
    this.stopped = true;
    if (this.retry) clearTimeout(this.retry);
    this.retry = undefined;
  }
}
