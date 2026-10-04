import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { AuthUser } from "../api/client";
import { AuthContext, type AuthContextValue } from "../auth/auth-context";
import type {
  OwnerQuestionDetail,
  OwnerQuestionImportPreview,
  OwnerQuestionsResponse,
} from "./api";
import { OwnerMockQuestionsPage } from "./OwnerMockQuestionsPage";

const owner: AuthUser = {
  id: "owner-id",
  email: "owner@example.com",
  first_name: "GrowthSathi",
  last_name: "Owner",
  full_name: "GrowthSathi Owner",
  onboarding_completed: false,
  is_staff: true,
  is_superuser: true,
};

const emptyQuestions: OwnerQuestionsResponse = {
  mock: {
    id: "mock-id",
    title: "JEE Weekly Mock",
    status: "DRAFT",
    question_count: 0,
    expected_question_count: 75,
    read_only: false,
  },
  grouped_counts: [],
  results: [],
};

const question = {
  id: "question-id",
  question_number: 1,
  phase_order: 1,
  phase_name: "Full paper",
  subject: "PHYSICS",
  question_type: "MCQ_SINGLE",
  status: "READY",
  status_label: "Ready",
  question_preview: "A short question preview",
  has_image: false,
};

const populatedQuestions: OwnerQuestionsResponse = {
  mock: {
    ...emptyQuestions.mock,
    question_count: 1,
  },
  grouped_counts: [
    {
      phase_order: 1,
      phase_name: "Full paper",
      subject: "PHYSICS",
      question_type: "MCQ_SINGLE",
      count: 1,
    },
  ],
  results: [question],
};

const questionDetail: OwnerQuestionDetail = {
  ...question,
  question_text_md: "What is the value of x?",
  options: [
    { label: "A", text: "One", has_image: false },
    { label: "B", text: "Two", has_image: false },
  ],
};

const validPreview: OwnerQuestionImportPreview = {
  valid: true,
  token: "signed-preview-token",
  rows: [
    {
      row: 2,
      question_number: "1",
      phase: "1",
      subject: "PHYSICS",
      question_type: "MCQ_SINGLE",
      question_preview: "Imported question",
    },
  ],
  errors: [],
  warnings: ["Paper is incomplete. Final validation is required."],
};

function withOwnerAccess<T>(operation: (token: string) => Promise<T>) {
  return operation("owner-access-token");
}

function renderPage() {
  const context: AuthContextValue = {
    status: "authenticated",
    user: owner,
    loginWithGoogle: vi.fn(),
    logout: vi.fn(),
    getProfile: vi.fn(),
    saveProfile: vi.fn(),
    withAccess: withOwnerAccess,
  };
  return render(
    <AuthContext.Provider value={context}>
      <MemoryRouter initialEntries={["/owner/mocks/mock-id/questions"]}>
        <Routes>
          <Route
            element={<OwnerMockQuestionsPage />}
            path="/owner/mocks/:mockId/questions"
          />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

it("shows the loading state while questions are being fetched", () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => new Promise<Response>(() => {})),
  );

  renderPage();

  expect(
    screen.getByRole("status", { name: "Loading questions" }),
  ).toBeInTheDocument();
});

it("shows an empty state when the mock has no questions", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(Response.json(emptyQuestions)),
  );

  renderPage();

  expect(
    await screen.findByText("No questions have been added."),
  ).toBeInTheDocument();
  expect(screen.getByText("No questions yet")).toBeInTheDocument();
  expect(screen.getByText("0")).toBeInTheDocument();
});

it("renders populated questions and opens safe question inspection", async () => {
  const fetcher = vi.fn().mockImplementation((input: RequestInfo | URL) => {
    const url = String(input);
    return Promise.resolve(
      url.endsWith("/questions/question-id/")
        ? Response.json(questionDetail)
        : Response.json(populatedQuestions),
    );
  });
  vi.stubGlobal("fetch", fetcher);

  renderPage();

  expect(
    await screen.findByText("A short question preview"),
  ).toBeInTheDocument();
  expect(screen.getByText("Ready")).toBeInTheDocument();
  expect(screen.getByText("Multiple choice · 1")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Inspect" }));

  expect(
    await screen.findByText("What is the value of x?"),
  ).toBeInTheDocument();
  expect(
    screen.getByText("Answer keys are omitted from question inspection."),
  ).toBeInTheDocument();
  expect(screen.queryByText("Correct answer: One")).not.toBeInTheDocument();
});

it("uploads a file, previews it, requires confirmation, and commits", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(Response.json(emptyQuestions))
    .mockResolvedValueOnce(Response.json(validPreview))
    .mockResolvedValueOnce(Response.json({ imported_count: 1 }))
    .mockResolvedValueOnce(Response.json(populatedQuestions));
  vi.stubGlobal("fetch", fetcher);

  renderPage();

  const file = new File(["fixture"], "questions.csv", { type: "text/csv" });
  fireEvent.change(await screen.findByLabelText("Question file"), {
    target: { files: [file] },
  });
  fireEvent.click(screen.getByRole("button", { name: "Preview import" }));

  expect(
    await screen.findByRole("heading", { name: "Import preview" }),
  ).toBeInTheDocument();
  expect(
    screen.getByText("Paper is incomplete. Final validation is required."),
  ).toBeInTheDocument();
  const previewRequest = fetcher.mock.calls[1]?.[1] as RequestInit;
  expect(previewRequest.body).toBeInstanceOf(FormData);
  expect(new Headers(previewRequest.headers).has("Content-Type")).toBe(false);
  expect(screen.getByRole("button", { name: "Confirm import" })).toBeDisabled();

  fireEvent.click(
    screen.getByLabelText(
      "I reviewed this preview and confirm the atomic import.",
    ),
  );
  fireEvent.click(screen.getByRole("button", { name: "Confirm import" }));

  expect(await screen.findByText("Imported 1 question.")).toBeInTheDocument();
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(4));
  expect(screen.getByText("A short question preview")).toBeInTheDocument();
});

it("groups validation errors and does not offer confirmation for an invalid preview", async () => {
  const invalidPreview: OwnerQuestionImportPreview = {
    ...validPreview,
    valid: false,
    token: "",
    errors: [
      {
        row: 2,
        message: "correct_option must be exactly one label A, B, C or D.",
      },
      { row: null, message: "Upload a UTF-8 CSV or XLSX file." },
    ],
  };
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(Response.json(emptyQuestions))
    .mockResolvedValueOnce(Response.json(invalidPreview));
  vi.stubGlobal("fetch", fetcher);

  renderPage();

  fireEvent.change(await screen.findByLabelText("Question file"), {
    target: {
      files: [new File(["bad"], "questions.csv", { type: "text/csv" })],
    },
  });
  fireEvent.click(screen.getByRole("button", { name: "Preview import" }));

  expect(await screen.findByText(/Row 2:/)).toBeInTheDocument();
  expect(screen.getByText(/File:/)).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Confirm import" }),
  ).not.toBeInTheDocument();
});

it("shows the read-only state and hides upload controls for non-draft mocks", async () => {
  const closed: OwnerQuestionsResponse = {
    ...populatedQuestions,
    mock: { ...populatedQuestions.mock, status: "CLOSED", read_only: true },
  };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json(closed)));

  renderPage();

  expect(
    await screen.findByText(/Questions are available for inspection/),
  ).toBeInTheDocument();
  expect(
    screen.getByText(
      "Import is available only while the mock is in DRAFT status.",
    ),
  ).toBeInTheDocument();
  expect(screen.queryByLabelText("Question file")).not.toBeInTheDocument();
});

it("offers retry after question API failure", async () => {
  const fetcher = vi
    .fn()
    .mockRejectedValueOnce(new Error("Unavailable"))
    .mockResolvedValueOnce(Response.json(emptyQuestions));
  vi.stubGlobal("fetch", fetcher);

  renderPage();

  fireEvent.click(await screen.findByRole("button", { name: "Try again" }));

  expect(
    await screen.findByText("No questions have been added."),
  ).toBeInTheDocument();
});

it("shows a recoverable API error when import preview fails", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(Response.json(emptyQuestions))
    .mockRejectedValueOnce(new Error("Preview service unavailable"))
    .mockResolvedValueOnce(Response.json(validPreview));
  vi.stubGlobal("fetch", fetcher);

  renderPage();
  fireEvent.change(await screen.findByLabelText("Question file"), {
    target: {
      files: [new File(["fixture"], "questions.csv", { type: "text/csv" })],
    },
  });
  fireEvent.click(screen.getByRole("button", { name: "Preview import" }));

  expect(
    await screen.findByText("Preview service unavailable"),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Retry preview" }));
  expect(
    await screen.findByRole("heading", { name: "Import preview" }),
  ).toBeInTheDocument();
});
