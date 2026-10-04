import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { AuthUser } from "../api/client";
import { AuthContext, type AuthContextValue } from "../auth/auth-context";
import type { OwnerMockDetail, OwnerMockSummary } from "./api";
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
  expect(screen.getAllByText("JEE Weekly Mock").length).toBeGreaterThan(0);
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
    screen.getByText(/Full paper validation is not run on this page/),
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
