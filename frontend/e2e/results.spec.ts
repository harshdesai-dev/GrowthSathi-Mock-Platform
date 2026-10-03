import { test, expect, type BrowserContext } from "@playwright/test";

async function fixture(context: BrowserContext) {
  const control = {
    published: true,
    offline: false,
    expire: false,
    expired: false,
    refreshes: 0,
  };
  const report = {
    mock_id: "mock",
    mock_title: "JEE Main · Full Mock 08",
    exam: "JEE Main",
    starts_at: "2026-09-27T04:30:00Z",
    maximum_score: "300.00",
    score: "151.00",
    rank: 24,
    percentile: "95.40",
    correct_count: 40,
    incorrect_count: 9,
    attempted_count: 49,
    unattempted_count: 26,
    student_name: "Harsh Desai",
    previous_score: "126.00",
    score_difference: "25.00",
  };
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
        full_name: "Harsh Desai",
        onboarding_completed: true,
        is_staff: false,
      });
    if (control.offline) return route.abort("internetdisconnected");
    if (control.expire && !control.expired) {
      control.expired = true;
      return json(
        { error: { code: "token_not_valid", message: "Expired" } },
        401,
      );
    }
    if (!control.published)
      return json(
        {
          error: {
            code: "result_unavailable",
            message: "Results are not published yet.",
          },
        },
        409,
      );
    if (path.endsWith("/result/")) return json(report);
    if (path.endsWith("/history/")) return json([report]);
    if (path.endsWith("/leaderboard/"))
      return json({
        mock_title: report.mock_title,
        rows: [
          { rank: 1, name: "Rahul P.", score: "200.00", percentile: "100.00" },
          { rank: 2, name: "Sneha M.", score: "190.00", percentile: "99.80" },
          { rank: 2, name: "Harsh D.", score: "190.00", percentile: "99.80" },
          { rank: 4, name: "Asha K.", score: "180.00", percentile: "99.40" },
        ],
      });
    if (path.endsWith("/review/"))
      return json({
        mock_title: report.mock_title,
        questions: [
          {
            id: "q1",
            question_number: 1,
            question_type: "MCQ_SINGLE",
            question_text_md:
              "A particle has displacement $s(t)=3t^2+2t$. Find its velocity at $t=2$ seconds.",
            question_image_url: "",
            options: [
              {
                id: "a",
                label: "A",
                option_text_md: "$14\\;\\mathrm{m/s}$",
                option_image_url: "",
              },
              {
                id: "b",
                label: "B",
                option_text_md: "$10\\;\\mathrm{m/s}$",
                option_image_url: "",
              },
            ],
            selected_option: "b",
            numeric_answer: "",
            correct_option: "a",
            correct_numeric_answer: null,
            numeric_tolerance: "0",
            outcome: "Incorrect",
            marks: "-1.00",
            explanation_md:
              "Differentiate displacement: $v(t)=6t+2$. At $t=2$, $v=14\\;\\mathrm{m/s}$.",
          },
          {
            id: "q2",
            question_number: 2,
            question_type: "NUMERICAL",
            question_text_md: "Find $x$ if $2x=5$.",
            question_image_url: "",
            options: [],
            selected_option: null,
            numeric_answer: "2.5",
            correct_option: null,
            correct_numeric_answer: "2.5",
            numeric_tolerance: "0.01",
            outcome: "Correct",
            marks: "4.00",
            explanation_md: "Divide both sides by two.",
          },
          {
            id: "q3",
            question_number: 3,
            question_type: "NUMERICAL",
            question_text_md: "Find $x$ if $x+1=2$.",
            question_image_url: "",
            options: [],
            selected_option: null,
            numeric_answer: "",
            correct_option: null,
            correct_numeric_answer: "1",
            numeric_tolerance: "0",
            outcome: "Unattempted",
            marks: "0.00",
            explanation_md: "Subtract one from both sides.",
          },
        ],
      });
    return json({}, 404);
  });
  return control;
}

for (const width of [360, 390, 430, 768, 1440]) {
  test(`published results, leaderboard and review fit ${width}px`, async ({
    page,
    context,
  }) => {
    await fixture(context);
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/results/mock");
    await expect(
      page.getByRole("heading", { name: "JEE Main · Full Mock 08" }),
    ).toBeVisible();
    await expect(page.getByText("+25 marks")).toBeVisible();
    await page.screenshot({
      path: `test-results/phase5-report-${width}.png`,
      fullPage: true,
    });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.getByRole("link", { name: "View Leaderboard" }).click();
    await expect(page.getByText("Harsh D.")).toBeVisible();
    await expect(page.getByText("#2", { exact: true })).toHaveCount(2);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: `test-results/phase5-leaderboard-${width}.png`,
      fullPage: true,
    });
    await page.getByRole("link", { name: "Back to my report card" }).click();
    await page.getByRole("link", { name: /Review Answers/ }).click();
    await expect(
      page.getByRole("heading", { name: "Question 1", exact: true }),
    ).toBeVisible();
    await expect(page.getByText("Incorrect · -1 marks")).toBeVisible();
    await expect(page.getByText("Not answered")).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: `test-results/phase5-review-${width}.png`,
      fullPage: true,
    });
    await page.getByRole("link", { name: "Result history" }).click();
    await expect(
      page.getByRole("link", { name: "JEE Main · Full Mock 08" }),
    ).toBeVisible();
  });
}
test("publication gate, reconnect retry, JWT recovery and refresh", async ({
  page,
  context,
}) => {
  const control = await fixture(context);
  control.published = false;
  await page.goto("/results/mock/review");
  await expect(page.getByRole("alert")).toHaveText(
    "Results are not published yet.",
  );
  await expect(
    page.getByRole("heading", { name: "Correct answer" }),
  ).toHaveCount(0);
  control.published = true;
  control.offline = true;
  await page.getByRole("button", { name: "Check again" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  control.offline = false;
  control.expire = true;
  await page.getByRole("button", { name: "Check again" }).click();
  await expect(
    page.getByRole("heading", { name: "Question 1", exact: true }),
  ).toBeVisible();
  expect(control.refreshes).toBeGreaterThanOrEqual(2);
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Question 1", exact: true }),
  ).toBeVisible();
  control.published = false;
  await page.reload();
  await expect(page.getByRole("alert")).toHaveText(
    "Results are not published yet.",
  );
});
