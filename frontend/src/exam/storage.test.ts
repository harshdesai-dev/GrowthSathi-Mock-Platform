import "fake-indexeddb/auto";
import { AnswerStore, displayedAnswer, examDB } from "./storage";
import { blankAnswer } from "./api";

beforeEach(async () => {
  await (await examDB()).clear("answers");
});

test("persists before network and recovers in a new instance without cross-user leakage", async () => {
  const first = new AnswerStore("user/attempt");
  await first.edit("q", "phase", {
    selected_option: "A",
    numeric_answer: "",
    marked_for_review: true,
  });
  const reopened = new AnswerStore("user/attempt");
  expect((await reopened.list())[0].answer.selected_option).toBe("A");
  expect(await new AnswerStore("other/attempt").list()).toEqual([]);
});

test("two tabs allocate monotonic versions atomically", async () => {
  const a = new AnswerStore("user/attempt"),
    b = new AnswerStore("user/attempt");
  const records = await Promise.all(
    Array.from({ length: 30 }, (_, i) =>
      (i % 2 ? a : b).edit("q", "phase", {
        ...blankAnswer("q"),
        numeric_answer: String(i),
      }),
    ),
  );
  expect(new Set(records.map((r) => r.answer.mutation_version)).size).toBe(30);
  expect((await a.list())[0].answer.mutation_version).toBe(30);
});

test("late acknowledgement never clears a newer pending mutation", async () => {
  const store = new AnswerStore("u/a");
  const a = await store.edit("q", "p", {
    ...blankAnswer("q"),
    numeric_answer: "1",
  });
  await store.edit("q", "p", { ...blankAnswer("q"), numeric_answer: "2" });
  await store.acknowledge(a.answer, a.answer, "p");
  const entry = (await store.list())[0];
  expect(entry.pending).toBe(true);
  expect(entry.answer.numeric_answer).toBe("2");
  await store.accept({ ...a.answer, mutation_version: 0 }, "p");
  expect((await store.list())[0].server?.mutation_version).toBe(1);
});

test("conflicts show server state but preserve blocked device draft, without rebasing", async () => {
  const store = new AnswerStore("u/a");
  await store.edit("q", "p", { ...blankAnswer("q"), numeric_answer: "1" });
  const server = {
    ...blankAnswer("q"),
    mutation_version: 2,
    numeric_answer: "9",
  };
  await store.accept(server, "p");
  const entry = (await store.list())[0];
  expect(entry.blocked).toContain("Conflicting");
  expect(entry.answer.mutation_version).toBe(1);
  expect(displayedAnswer(entry, "q").numeric_answer).toBe("9");
  const edited = await store.edit("q", "p", { ...server, numeric_answer: "3" });
  expect(edited.answer.mutation_version).toBe(3);
  expect(edited.blocked).toBe("");
});

test("closed phases stay blocked and canonical decimal acks are accepted", async () => {
  const store = new AnswerStore("u/a");
  const entry = await store.edit("q", "pc", {
    ...blankAnswer("q"),
    numeric_answer: "01.0",
  });
  await store.acknowledge(
    entry.answer,
    { ...entry.answer, numeric_answer: "1" },
    "pc",
  );
  expect((await store.list())[0].pending).toBe(false);
  await store.edit("q", "pc", { ...blankAnswer("q"), numeric_answer: "2" });
  await store.closeOtherPhases("math");
  expect((await store.list())[0].blocked).toContain("Phase closed");
});
