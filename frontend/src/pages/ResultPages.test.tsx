import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AuthContext, type AuthContextValue } from "../auth/auth-context";
import type { Report } from "../api/results";
import {
  LeaderboardPage,
  ResultHistoryPage,
  ResultPage,
  ReviewPage,
} from "./ResultPages";
import { difference } from "../results/format";

const report: Report = {
  mock_id: "mock",
  mock_title: "JEE Full Mock",
  exam: "JEE Main",
  starts_at: "2026-09-27T04:30:00Z",
  maximum_score: "300.00",
  score: "151.00",
  rank: 2,
  percentile: "87.50",
  correct_count: 40,
  incorrect_count: 9,
  attempted_count: 49,
  unattempted_count: 26,
  student_name: "Harsh Desai",
  previous_score: "126.00",
  score_difference: "25.00",
};
const context: AuthContextValue = {
  status: "authenticated",
  user: null,
  loginWithGoogle: vi.fn(),
  logout: vi.fn(),
  getProfile: vi.fn(),
  saveProfile: vi.fn(),
  withAccess: (operation) => operation("test-token"),
};
function page(path = "/results/mock") {
  return render(
    <AuthContext.Provider value={context}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/results" element={<ResultHistoryPage />} />
          <Route path="/results/:mockId" element={<ResultPage />} />
          <Route path="/results/:mockId/review" element={<ReviewPage />} />
          <Route
            path="/results/:mockId/leaderboard"
            element={<LeaderboardPage />}
          />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}
function respond(data: unknown) {
  const fetcher = vi
    .fn()
    .mockImplementation(
      async () => new Response(JSON.stringify(data), { status: 200 }),
    );
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}
afterEach(() => vi.unstubAllGlobals());
it("shows the private report, mock-only percentile and signed comparison", async () => {
  const fetcher = respond(report);
  page();
  expect(
    await screen.findByRole("heading", { name: "JEE Full Mock" }),
  ).toBeInTheDocument();
  expect(screen.getByText("Harsh Desai")).toBeInTheDocument();
  expect(screen.getByText("Mock Percentile")).toBeInTheDocument();
  expect(screen.getByText("+25 marks")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Review Answers/ })).toHaveAttribute(
    "href",
    "/results/mock/review",
  );
  expect(fetcher.mock.calls[0][1]).toMatchObject({
    cache: "no-store",
    headers: { Authorization: "Bearer test-token" },
  });
});
it("handles first published attempt, negative and zero differences", async () => {
  respond({ ...report, previous_score: null, score_difference: null });
  page();
  expect(await screen.findByText(/first published result/)).toBeInTheDocument();
  expect(difference("-8.00")).toBe("-8");
  expect(difference("0.00")).toBe("0");
});
it("shows unavailable and retries without revealing a draft", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          error: {
            code: "result_unavailable",
            message: "Awaiting manual publication.",
          },
        }),
        { status: 409 },
      ),
    )
    .mockResolvedValueOnce(
      new Response(JSON.stringify(report), { status: 200 }),
    );
  vi.stubGlobal("fetch", fetcher);
  page();
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Awaiting manual publication.",
  );
  expect(screen.queryByText("Harsh Desai")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Check again" }));
  expect(await screen.findByText("Harsh Desai")).toBeInTheDocument();
});
it("renders masked leaderboard rows and competition ties", async () => {
  respond({
    mock_title: report.mock_title,
    rows: [
      { rank: 1, name: "Harsh D.", score: "151.00", percentile: "100.00" },
      { rank: 1, name: "Sneha M.", score: "151.00", percentile: "100.00" },
    ],
  });
  page("/results/mock/leaderboard");
  expect(await screen.findByText("Harsh D.")).toBeInTheDocument();
  expect(screen.getAllByText("#1")).toHaveLength(2);
  expect(screen.queryByText("Harsh Desai")).not.toBeInTheDocument();
});
it("renders published history and the empty state", async () => {
  respond([]);
  page("/results");
  expect(
    await screen.findByText(/No published results yet/),
  ).toBeInTheDocument();
});
it("distinguishes selected, correct, unattempted and explanation with safe math", async () => {
  respond({
    mock_title: report.mock_title,
    questions: [
      {
        id: "q",
        question_number: 1,
        question_type: "NUMERICAL",
        question_text_md: "Solve $2x=5$. <script>alert(1)</script>",
        question_image_url: "javascript:alert(1)",
        options: [],
        selected_option: null,
        numeric_answer: "",
        correct_option: null,
        correct_numeric_answer: "2.5",
        numeric_tolerance: "0.01",
        outcome: "Unattempted",
        marks: "0.00",
        explanation_md: "Divide by two: $x=2.5$.",
      },
    ],
  });
  const view = page("/results/mock/review");
  expect(
    await screen.findByRole("heading", { name: "Question 1" }),
  ).toBeInTheDocument();
  expect(screen.getByText("Not answered")).toBeInTheDocument();
  expect(screen.getByText(/Absolute tolerance: 0.01/)).toBeInTheDocument();
  expect(
    screen.getByRole("heading", { name: "Explanation" }),
  ).toBeInTheDocument();
  expect(view.container.querySelector("script")).toBeNull();
  expect(view.container.querySelector("img[src^='javascript:']")).toBeNull();
  expect(view.container.querySelector(".katex")).not.toBeNull();
});
