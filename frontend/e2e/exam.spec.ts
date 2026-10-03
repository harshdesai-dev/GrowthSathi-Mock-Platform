import { test, expect, type BrowserContext } from "@playwright/test";
import type { Answer, AttemptState, Question } from "../src/exam/api";

async function fixture(context: BrowserContext, cet = false) {
  const start = Date.now() - 30 * 60000;
  const phase1 = {
    id: "pc",
    name: cet ? "Physics & Chemistry" : "Physics, Chemistry & Mathematics",
    order: 1,
  };
  const state: AttemptState = {
    attempt_id: "attempt",
    mock_id: "mock",
    mock_title: cet ? "MHT-CET PCM · Full mock" : "JEE Main · Full mock",
    status: "IN_PROGRESS",
    server_time: new Date().toISOString(),
    started_at: new Date().toISOString(),
    mock_starts_at: new Date(start).toISOString(),
    mock_ends_at: new Date(start + 180 * 60000).toISOString(),
    phase_starts_at: new Date(start).toISOString(),
    phase_ends_at: new Date(start + (cet ? 90 : 180) * 60000).toISOString(),
    current_phase: phase1,
    can_submit: !cet,
    submitted_at: null,
    responses: [],
    saved_response_count: 0,
    answered_count: 0,
    question_count: cet ? 150 : 75,
  };
  const saved = new Map<string, Answer>();
  const control = {
    offline: false,
    expireOnce: false,
    expired: false,
    refreshes: 0,
    saves: 0,
    submissions: 0,
  };
  const questions = (phase: string): Question[] =>
    Array.from({ length: cet ? (phase === "pc" ? 100 : 50) : 75 }, (_, i) => ({
      id: `${phase}-${i}`,
      question_number: phase === "math" ? 101 + i : i + 1,
      phase_id: phase,
      subject:
        phase === "math"
          ? "MATHEMATICS"
          : i < (cet ? 50 : 25)
            ? "PHYSICS"
            : i < (cet ? 100 : 50)
              ? "CHEMISTRY"
              : "MATHEMATICS",
      question_type: i === 1 ? "NUMERICAL" : "MCQ_SINGLE",
      question_text_md:
        i === 1
          ? "Find the value of $x$ when $2x=5$."
          : "A particle moves along a straight line. Its displacement is given by $s(t)=3t^2+2t$. What is its velocity at $t=2$ seconds?",
      question_image_url: "",
      options:
        i === 1
          ? []
          : ["A", "B", "C", "D"].map((label, index) => ({
              id: `${phase}-${i}-${label}`,
              label,
              option_text_md: `$${[8, 10, 14, 16][index]}\\;\\mathrm{m/s}$`,
              option_image_url: "",
            })),
    }));
  await context.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, json: body });
    if (path.endsWith("/auth/csrf/")) return json({ csrf_token: "synthetic" });
    if (path.endsWith("/auth/refresh/")) {
      control.refreshes++;
      return json({
        access_token: `token-${control.refreshes}`,
        expires_in: 300,
      });
    }
    if (path.endsWith("/auth/me/"))
      return json({
        id: "student",
        email: "student@test.invalid",
        full_name: "Test Student",
        onboarding_completed: true,
        is_staff: false,
      });
    if (control.offline) return route.abort("internetdisconnected");
    if (
      control.expireOnce &&
      !control.expired &&
      path.includes("/responses/")
    ) {
      control.expired = true;
      return json(
        { error: { code: "token_not_valid", message: "Expired" } },
        401,
      );
    }
    state.server_time = new Date().toISOString();
    state.responses = [...saved.values()].filter((a) =>
      a.question_id.startsWith(state.current_phase?.id ?? "none"),
    );
    state.saved_response_count = saved.size;
    state.answered_count = [...saved.values()].filter(
      (a) => a.selected_option || a.numeric_answer,
    ).length;
    if (path.endsWith("/heartbeat/") || path.endsWith("/attempts/attempt/"))
      return json(state);
    if (path.endsWith("/paper/"))
      return json({
        state,
        questions: questions(state.current_phase?.id ?? "pc"),
      });
    if (path.includes("/responses/")) {
      const id = path.split("/").at(-2)!;
      const answer = {
        question_id: id,
        ...route.request().postDataJSON(),
      } as Answer;
      control.saves++;
      saved.set(id, answer);
      return json({
        response: answer,
        acknowledgement: "saved",
        server_time: state.server_time,
      });
    }
    if (path.endsWith("/submit/")) {
      control.submissions++;
      state.status = "SUBMITTED";
      state.current_phase = null;
      state.responses = [];
      return json(state);
    }
    return json({ error: { code: "not_found", message: path } }, 404);
  });
  return { state, saved, control };
}

for (const width of [360, 390, 430, 768, 1024, 1440]) {
  test(`exam layout and accessible navigation at ${width}px`, async ({
    page,
    context,
  }) => {
    await fixture(context);
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/exam/attempt");
    await expect(
      page.getByRole("heading", { name: "Question 1", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("All changes saved on server", { exact: false }),
    ).toBeVisible();
    await page.getByRole("radio").nth(2).check();
    await expect(page.getByRole("radio").nth(2)).toBeChecked();
    await page
      .getByRole("button", { name: "Mark for review", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "Unmark review" }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: `test-results/exam-${width}.png`,
      fullPage: true,
    });
    await page
      .getByRole("button", { name: "Clear response", exact: true })
      .click();
    await expect(page.locator('input[type="radio"]:checked')).toHaveCount(0);
    if (width < 768) {
      await page.getByRole("button", { name: /Questions/ }).click();
      await expect(
        page.getByRole("dialog", { name: "Questions", exact: true }),
      ).toBeVisible();
      await page.screenshot({ path: `test-results/palette-${width}.png` });
      await page
        .getByRole("dialog")
        .getByRole("button", { name: "Question 2, unvisited", exact: true })
        .click();
      await expect(page.getByRole("dialog")).not.toBeVisible();
    } else
      await page
        .getByRole("button", { name: "Question 2, unvisited", exact: true })
        .click();
    await page.getByRole("textbox", { name: "Numerical answer" }).fill("-1.25");
    await expect(
      page.getByText("All changes saved on server", { exact: false }),
    ).toBeVisible();
  });
}

test("offline IndexedDB queue survives refresh, page reopen, JWT expiry and final submit", async ({
  page,
  context,
}) => {
  const { saved, control } = await fixture(context);
  await page.goto("/exam/attempt");
  await expect(
    page.getByText("All changes saved on server", { exact: false }),
  ).toBeVisible();
  control.offline = true;
  await page.getByRole("radio").nth(1).check();
  await expect(page.locator(".exam-sync")).toContainText(
    "Connection interrupted",
  );
  await page.reload();
  // The page has no cached paper authority: reconnect is needed, but the queue remains durable.
  control.offline = false;
  control.expireOnce = true;
  await page.getByRole("button", { name: "Retry sync" }).click();
  await expect(page.getByRole("radio").nth(1)).toBeChecked();
  await expect.poll(() => saved.get("pc-0")?.selected_option).toBe("pc-0-B");
  expect(control.refreshes).toBeGreaterThanOrEqual(3);
  const timeBefore = await page.getByRole("timer").innerText();
  const reopened = await context.newPage();
  await page.close();
  await reopened.goto("/exam/attempt");
  await expect(reopened.getByRole("radio").nth(1)).toBeChecked();
  expect((await reopened.getByRole("timer").innerText()) <= timeBefore).toBe(
    true,
  );
  await reopened.evaluate(() => {
    Date.now = () => 0;
  });
  await expect(reopened.getByRole("timer")).not.toHaveText("03:00:00");
  await reopened
    .getByRole("button", { name: "Submit exam", exact: true })
    .click();
  await reopened.getByRole("button", { name: "Sync & submit" }).click();
  await expect(
    reopened.getByRole("heading", { name: "Your attempt is submitted." }),
  ).toBeVisible();
  expect(control.submissions).toBe(1);
});

test("CET switches from global server state and never replays offline PC answers", async ({
  page,
  context,
}) => {
  const { state, control } = await fixture(context, true);
  await page.setViewportSize({ width: 390, height: 850 });
  await page.goto("/exam/attempt");
  await expect(
    page.getByRole("button", { name: "Submit exam", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByText("All changes saved on server", { exact: false }),
  ).toBeVisible();
  control.offline = true;
  await page.getByRole("radio").nth(0).check();
  await expect(page.locator(".exam-sync")).toContainText(
    "Connection interrupted",
  );
  const savesBefore = control.saves;
  state.current_phase = { id: "math", name: "Mathematics", order: 2 };
  state.can_submit = true;
  control.offline = false;
  await page.getByRole("button", { name: "Retry sync" }).click();
  await expect(
    page.getByRole("heading", { name: "Question 101", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(/Closed-phase changes cannot be resent/),
  ).toBeVisible();
  // Only new Mathematics visits can save; the PC option is absent on the server.
  await expect(
    page.getByRole("button", { name: "Submit exam", exact: true }),
  ).toBeEnabled();
  expect(control.saves).toBeLessThanOrEqual(savesBefore + 1);
  state.status = "AUTO_SUBMITTED";
  state.current_phase = null;
  await page.getByRole("button", { name: "Retry sync" }).click();
  await expect(
    page.getByRole("heading", { name: "Time is up. Attempt closed." }),
  ).toBeVisible();
});
