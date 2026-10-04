import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { AuthUser } from "../api/client";
import { AuthContext, type AuthContextValue } from "../auth/auth-context";
import type {
  OwnerMockDetail,
  OwnerMockSummary,
  OwnerPaperValidationResult,
} from "./api";
import { OwnerMockDetailPage } from "./OwnerMockDetailPage";
import { OwnerMockFormPage } from "./OwnerMockFormPage";
import { OwnerMocksPage } from "./OwnerMocksPage";

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

const mock: OwnerMockSummary = {
  id: "e34c80b1-48b9-4d9b-a965-54e85c3ad1a7",
  title: "JEE Weekly Mock",
  slug: "jee-weekly-mock",
  exam_type: { code: "JEE_MAIN", name: "JEE Main", active: true },
  exam_scheme: {
    name: "JEE Main official rules",
    version: "2026-v2",
    active: true,
    total_question_count: 75,
    total_duration_minutes: 180,
    maximum_marks: 300,
  },
  status: "REGISTRATION_OPEN",
  status_label: "Registration Open",
  starts_at: "2026-10-10T04:00:00Z",
  ends_at: "2026-10-10T07:00:00Z",
  result_release_at: "2026-10-11T04:00:00Z",
  price_paise: 2900,
  rules_verified_at: null,
  question_count: 74,
};

const detail: OwnerMockDetail = {
  ...mock,
  rules_source_notes: "",
  exam_type_id: "exam-type-id",
  exam_scheme_id: "exam-scheme-id",
  description: "A student mock description.",
  instructions_md: "Read the instructions.",
  phases: [
    {
      order: 1,
      name: "Full paper",
      start_offset_minutes: 0,
      duration_minutes: 180,
      sequence_locked: false,
      question_count: 74,
    },
  ],
  operational_warnings: [
    "Official rules have not been verified for this mock.",
    "The stored question count differs from the exam scheme's expected total.",
  ],
};

function withOwnerAccess<T>(operation: (token: string) => Promise<T>) {
  return operation("owner-access-token");
}

function renderPage(path = "/owner/mocks") {
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
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route element={<OwnerMocksPage />} path="/owner/mocks" />
          <Route
            element={<OwnerMockDetailPage />}
            path="/owner/mocks/:mockId"
          />
          <Route element={<OwnerMockFormPage />} path="/owner/mocks/new" />
          <Route
            element={<OwnerMockFormPage />}
            path="/owner/mocks/:mockId/edit"
          />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

it("renders mock operational fields and a real status badge", async () => {
  const fetcher = vi.fn().mockResolvedValue(Response.json({ results: [mock] }));
  vi.stubGlobal("fetch", fetcher);

  renderPage();

  expect(
    await screen.findByRole("heading", { name: "Mocks" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Create mock" })).toHaveAttribute(
    "href",
    "/owner/mocks/new",
  );
  expect(await screen.findAllByText("JEE Weekly Mock")).not.toHaveLength(0);
  expect(screen.getAllByText("Registration open").length).toBeGreaterThan(0);
  expect(screen.getAllByText("74 / 75").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Not verified").length).toBeGreaterThan(0);
  expect(screen.getAllByText("₹29").length).toBeGreaterThan(0);
  expect(screen.getAllByRole("link", { name: "View" })[0]).toHaveAttribute(
    "href",
    `/owner/mocks/${mock.id}`,
  );
});

it("sends exam, status, and title search filters to the server and clears them", async () => {
  const fetcher = vi.fn().mockResolvedValue(Response.json({ results: [mock] }));
  vi.stubGlobal("fetch", fetcher);

  renderPage();
  await screen.findAllByText("JEE Weekly Mock");

  fireEvent.change(screen.getByLabelText("Exam type"), {
    target: { value: "JEE_MAIN" },
  });
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
  expect(fetcher.mock.calls[1]?.[0]).toEqual(
    expect.stringMatching(/exam_type=JEE_MAIN/),
  );

  fireEvent.change(screen.getByLabelText("Status"), {
    target: { value: "REGISTRATION_OPEN" },
  });
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(3));
  expect(fetcher.mock.calls[2]?.[0]).toEqual(
    expect.stringMatching(/exam_type=JEE_MAIN&status=REGISTRATION_OPEN/),
  );

  fireEvent.change(screen.getByLabelText("Search by title"), {
    target: { value: "weekly" },
  });
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(4), {
    timeout: 1500,
  });
  expect(fetcher.mock.calls[3]?.[0]).toEqual(
    expect.stringMatching(
      /search=weekly&exam_type=JEE_MAIN&status=REGISTRATION_OPEN/,
    ),
  );

  fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(5));
  expect(fetcher.mock.calls[4]?.[0]).toEqual(
    expect.stringMatching(/\/owner\/mocks\/$/),
  );
});

it("shows a genuine empty state when no mocks exist", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(Response.json({ results: [] })),
  );

  renderPage();

  expect(
    await screen.findByRole("heading", { name: "No mocks yet" }),
  ).toBeInTheDocument();
});

it("shows a distinct empty state when filters return no mocks", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(Response.json({ results: [] })),
  );

  renderPage();
  fireEvent.change(screen.getByLabelText("Status"), {
    target: { value: "CANCELLED" },
  });

  expect(
    await screen.findByRole("heading", {
      name: "No mocks match these filters",
    }),
  ).toBeInTheDocument();
});

it("shows an API error and retries successfully", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(
      Response.json({ error: { code: "unavailable" } }, { status: 503 }),
    )
    .mockResolvedValueOnce(Response.json({ results: [mock] }));
  vi.stubGlobal("fetch", fetcher);

  renderPage();

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Mocks unavailable",
  );
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));

  expect(await screen.findAllByText("JEE Weekly Mock")).not.toHaveLength(0);
  expect(fetcher).toHaveBeenCalledTimes(2);
});

it("opens the read-only detail page from View", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(Response.json({ results: [mock] }))
    .mockResolvedValueOnce(Response.json(detail));
  vi.stubGlobal("fetch", fetcher);

  renderPage();
  fireEvent.click((await screen.findAllByRole("link", { name: "View" }))[0]!);

  expect(
    await screen.findByRole("heading", { name: "JEE Weekly Mock" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Phases" })).toBeInTheDocument();
  expect(
    screen.getByText(
      /This result is shown for this page view only and is not saved/,
    ),
  ).toBeInTheDocument();
  expect(fetcher.mock.calls[1]?.[0]).toEqual(
    expect.stringMatching(new RegExp(`/owner/mocks/${mock.id}/$`)),
  );
  expect(screen.queryByRole("link", { name: "Edit" })).not.toBeInTheDocument();
});

it("shows Edit on a draft mock detail page", async () => {
  const draftDetail: OwnerMockDetail = {
    ...detail,
    status: "DRAFT",
    status_label: "DRAFT",
  };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json(draftDetail)));

  renderPage(`/owner/mocks/${mock.id}`);

  expect(await screen.findByRole("link", { name: "Edit" })).toHaveAttribute(
    "href",
    `/owner/mocks/${mock.id}/edit`,
  );
});

const draftDetail: OwnerMockDetail = {
  ...detail,
  status: "DRAFT",
  status_label: "DRAFT",
};

const validPaperResult: OwnerPaperValidationResult = {
  valid: true,
  status: "VALID",
  errors: [],
  warnings: [],
  actual_question_count: 75,
  expected_question_count: 75,
  marks_summary: { actual: "300.00", expected: "300.00" },
};

it("runs paper validation and renders the valid result and summaries", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(Response.json(draftDetail))
    .mockResolvedValueOnce(Response.json(validPaperResult));
  vi.stubGlobal("fetch", fetcher);

  renderPage("/owner/mocks/" + mock.id);

  fireEvent.click(
    await screen.findByRole("button", { name: "Validate paper" }),
  );

  const result = await screen.findByRole("status", {
    name: "Paper validation result",
  });
  expect(result).toHaveTextContent("Valid");
  expect(result).toHaveTextContent("75 / 75");
  expect(result).toHaveTextContent("300.00 / 300.00");
  expect(result).toHaveTextContent(
    "The existing validator does not return separate warnings.",
  );
  expect(fetcher.mock.calls[1]?.[1]).toMatchObject({ method: "POST" });
  expect(screen.getByText(/not saved to the mock/i)).toBeInTheDocument();
});

it("renders existing validator errors for an invalid paper", async () => {
  const invalidResult: OwnerPaperValidationResult = {
    ...validPaperResult,
    valid: false,
    status: "INVALID",
    actual_question_count: 0,
    marks_summary: { actual: "0.00", expected: "300.00" },
    errors: [
      "Expected 75 questions; found 0.",
      "Subject/type/phase question counts do not match scheme rules.",
    ],
  };
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(Response.json(draftDetail))
    .mockResolvedValueOnce(Response.json(invalidResult));
  vi.stubGlobal("fetch", fetcher);

  renderPage("/owner/mocks/" + mock.id);
  fireEvent.click(
    await screen.findByRole("button", { name: "Validate paper" }),
  );

  const result = await screen.findByRole("status", {
    name: "Paper validation result",
  });
  expect(result).toHaveTextContent("Invalid");
  expect(result).toHaveTextContent("Expected 75 questions; found 0.");
});

it("shows validation error and retry states", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(Response.json(draftDetail))
    .mockResolvedValueOnce(
      Response.json(
        { error: { code: "unavailable", message: "Validator unavailable." } },
        { status: 503 },
      ),
    )
    .mockResolvedValueOnce(Response.json(validPaperResult));
  vi.stubGlobal("fetch", fetcher);

  renderPage("/owner/mocks/" + mock.id);
  fireEvent.click(
    await screen.findByRole("button", { name: "Validate paper" }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Paper validation could not be completed.",
  );
  fireEvent.click(screen.getByRole("button", { name: "Retry validation" }));
  expect(
    await screen.findByRole("status", { name: "Paper validation result" }),
  ).toHaveTextContent("Valid");
});

it("requires explicit confirmation before recording official-rule verification", async () => {
  const verification = {
    rules_verified_at: "2026-10-04T10:30:00Z",
    rules_source_notes:
      "NTA JEE Main bulletin, 2026 edition; checked 2026-09-25; verified pattern.",
  };
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(Response.json(draftDetail))
    .mockResolvedValueOnce(Response.json(verification));
  vi.stubGlobal("fetch", fetcher);

  renderPage("/owner/mocks/" + mock.id);

  expect((await screen.findAllByText("Not verified")).length).toBeGreaterThan(
    0,
  );
  fireEvent.change(screen.getByLabelText("Source and verification notes"), {
    target: { value: verification.rules_source_notes },
  });
  const submit = screen.getByRole("button", { name: "Record verification" });
  expect(submit).toBeDisabled();

  fireEvent.click(
    screen.getByLabelText(
      "I reviewed the official source and confirm recording this verification.",
    ),
  );
  expect(submit).toBeEnabled();
  fireEvent.click(submit);

  expect(
    await screen.findByText("Official-rules verification recorded."),
  ).toBeInTheDocument();
  expect(await screen.findAllByText(/Verified 4 Oct 2026/)).not.toHaveLength(0);
  expect(screen.getAllByText(verification.rules_source_notes)).not.toHaveLength(
    0,
  );
  expect(JSON.parse(String(fetcher.mock.calls[1]?.[1]?.body))).toEqual({
    source_notes: verification.rules_source_notes,
    confirmed: true,
  });
});

it("shows saved official source metadata for an already verified mock", async () => {
  const verifiedDetail: OwnerMockDetail = {
    ...draftDetail,
    rules_verified_at: "2026-10-04T10:30:00Z",
    rules_source_notes: "Official JEE Main bulletin, 2026 edition.",
  };
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(Response.json(verifiedDetail)),
  );

  renderPage("/owner/mocks/" + mock.id);

  expect(await screen.findByText("Verified")).toBeInTheDocument();
  expect(screen.getAllByText(/Verified 4 Oct 2026/).length).toBeGreaterThan(0);
  expect(
    screen.getAllByText("Official JEE Main bulletin, 2026 edition.").length,
  ).toBeGreaterThan(0);
});
