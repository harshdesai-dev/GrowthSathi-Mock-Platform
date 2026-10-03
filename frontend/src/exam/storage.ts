import { openDB, type DBSchema } from "idb";
import { blankAnswer, type Answer, type AnswerInput } from "./api";

export interface LocalAnswer {
  key: string;
  scope: string;
  phase: string;
  answer: Answer;
  server?: Answer;
  pending: boolean;
  blocked: string;
}
interface ExamDB extends DBSchema {
  answers: { key: string; value: LocalAnswer; indexes: { scope: string } };
}
export const examDB = () =>
  openDB<ExamDB>("growthsathi-exam-v1", 1, {
    upgrade(db) {
      db.createObjectStore("answers", { keyPath: "key" }).createIndex(
        "scope",
        "scope",
      );
    },
  });

export const sameAnswer = (a: Answer, b: Answer) =>
  a.mutation_version === b.mutation_version &&
  a.selected_option === b.selected_option &&
  a.numeric_answer === b.numeric_answer &&
  a.marked_for_review === b.marked_for_review;

export class AnswerStore {
  // Identity namespace prevents a subsequent account on a shared device reading this queue.
  constructor(readonly scope: string) {}
  private key(id: string) {
    return `${this.scope}/${id}`;
  }
  async list() {
    const db = await examDB();
    return db.getAllFromIndex("answers", "scope", this.scope);
  }
  async edit(
    id: string,
    phase: string,
    input: AnswerInput,
  ): Promise<LocalAnswer> {
    const db = await examDB();
    // IndexedDB readwrite transactions serialize version allocation across tabs.
    const tx = db.transaction("answers", "readwrite");
    const previous = await tx.store.get(this.key(id));
    const version =
      Math.max(
        previous?.answer.mutation_version ?? 0,
        previous?.server?.mutation_version ?? 0,
      ) + 1;
    if (!Number.isSafeInteger(version))
      throw new Error("Answer version limit reached. Contact support.");
    const entry: LocalAnswer = {
      key: this.key(id),
      scope: this.scope,
      phase,
      answer: { ...input, question_id: id, mutation_version: version },
      server: previous?.server,
      pending: true,
      blocked: "",
    };
    await tx.store.put(entry);
    await tx.done;
    return entry;
  }
  async accept(server: Answer, phase: string) {
    const db = await examDB();
    const tx = db.transaction("answers", "readwrite");
    const key = this.key(server.question_id);
    const entry = await tx.store.get(key);
    // A delayed heartbeat/ack must not roll back an already acknowledged version.
    if (
      entry &&
      (entry.server?.mutation_version ?? 0) > server.mutation_version
    ) {
      await tx.done;
      return;
    }
    if (
      entry?.pending &&
      entry.answer.mutation_version > server.mutation_version
    ) {
      await tx.store.put({ ...entry, server });
    } else if (entry?.pending && !sameAnswer(entry.answer, server)) {
      await tx.store.put({
        ...entry,
        server,
        blocked:
          "Conflicting server answer. Select your answer again to replace it.",
      });
    } else {
      await tx.store.put({
        key,
        scope: this.scope,
        phase,
        answer: server,
        server,
        pending: false,
        blocked: "",
      });
    }
    await tx.done;
  }
  async acknowledge(sent: Answer, server: Answer, phase: string) {
    const db = await examDB();
    const tx = db.transaction("answers", "readwrite");
    const key = this.key(sent.question_id);
    const entry = await tx.store.get(key);
    if (
      !entry ||
      (entry.server?.mutation_version ?? 0) > server.mutation_version
    ) {
      await tx.done;
      return;
    }
    // Canonical numeric text may differ from submitted text. Ack only this exact version.
    await tx.store.put(
      entry.answer.mutation_version === sent.mutation_version
        ? {
            key,
            scope: this.scope,
            phase,
            answer: server,
            server,
            pending: false,
            blocked: "",
          }
        : { ...entry, server },
    );
    await tx.done;
  }
  async block(id: string, version: number, reason: string) {
    const db = await examDB();
    const tx = db.transaction("answers", "readwrite");
    const entry = await tx.store.get(this.key(id));
    if (entry?.pending && entry.answer.mutation_version === version)
      await tx.store.put({ ...entry, blocked: reason });
    await tx.done;
  }
  async closeOtherPhases(active: string | null) {
    const db = await examDB();
    const tx = db.transaction("answers", "readwrite");
    for (const entry of await tx.store.index("scope").getAll(this.scope)) {
      if (entry.pending && entry.phase !== active)
        await tx.store.put({
          ...entry,
          blocked:
            "Phase closed. This device-only answer was not accepted by the server.",
        });
    }
    await tx.done;
  }
}

export function displayedAnswer(entry: LocalAnswer | undefined, id: string) {
  return entry?.blocked && !entry.blocked.startsWith("Finish entering")
    ? (entry.server ?? blankAnswer(id))
    : (entry?.answer ?? blankAnswer(id));
}
