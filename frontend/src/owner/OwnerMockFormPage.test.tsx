import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { AuthUser } from "../api/client";
import { AuthContext, type AuthContextValue } from "../auth/auth-context";
import type {
  OwnerMockDetail,
  OwnerMockOptions,
  OwnerMockSummary,
} from "./api";
import { OwnerMockDetailPage } from "./OwnerMockDetailPage";
import { OwnerMockFormPage } from "./OwnerMockFormPage";
import { isoToIstDateTimeLocal, rupeesToPaise } from "./mockForm.utils";

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

const examTypeId = "54d834bd-808c-4b0e-b5ad-43bb98dd70a3";
const schemeId = "9a45d41f-629c-41f9-8986-40f20524db41";
const mockId = "e34c80b1-48b9-4d9b-a965-54e85c3ad1a7";

const options: OwnerMockOptions = {
  exam_types: [
    { id: examTypeId, code: "JEE_MAIN", name: "JEE Main", active: true },
  ],
  exam_schemes: [
    {
      id: schemeId,
      exam_type_id: examTypeId,
      name: "JEE Main official rules",
      version: "2026-v2",
      active: true,
      total_question_count: 75,
      total_duration_minutes: 180,
      maximum_marks: 300,
    },
  ],
};

const summary: OwnerMockSummary = {
  id: mockId,
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
  status: "DRAFT",
  status_label: "DRAFT",
  starts_at: "2026-11-10T03:30:00Z",
  ends_at: "2026-11-10T06:30:00Z",
  result_release_at: "2026-11-11T03:30:00Z",
  price_paise: 2900,
  rules_verified_at: null,
  question_count: 0,
};

const detail: OwnerMockDetail = {
  ...summary,
  exam_type_id: examTypeId,
  exam_scheme_id: schemeId,
  description: "Initial description",
  instructions_md: "Read instructions before starting.",
  phases: [],
  operational_warnings: [],
};

function withOwnerAccess<T>(operation: (token: string) => Promise<T>) {
  return operation("owner-access-token");
}

function renderPage(path = "/owner/mocks/new") {
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
          <Route element={<OwnerMockFormPage />} path="/owner/mocks/new" />
          <Route
            element={<OwnerMockFormPage />}
            path="/owner/mocks/:mockId/edit"
          />
          <Route
            element={<OwnerMockDetailPage />}
            path="/owner/mocks/:mockId"
          />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

async function fillRequiredFields() {
  await screen.findByRole("heading", { name: "Create mock" });
  fireEvent.change(screen.getByLabelText("Exam type"), {
    target: { value: examTypeId },
  });
  fireEvent.change(screen.getByLabelText("Exam scheme"), {
    target: { value: schemeId },
  });
  fireEvent.change(screen.getByLabelText("Title"), {
    target: { value: "New owner mock" },
  });
  fireEvent.change(screen.getByLabelText("Slug"), {
    target: { value: "new-owner-mock" },
  });
  fireEvent.change(screen.getByLabelText("Start date and time (IST)"), {
    target: { value: "2026-11-10T09:00:00" },
  });
  fireEvent.change(screen.getByLabelText("End date and time (IST)"), {
    target: { value: "2026-11-10T12:00:00" },
  });
  fireEvent.change(
    screen.getByLabelText("Result release date and time (IST)"),
    {
      target: { value: "2026-11-11T09:00:00" },
    },
  );
}

afterEach(() => vi.unstubAllGlobals());

it("renders the DRAFT create form with exam options and rupee input", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json(options)));

  renderPage();

  expect(
    await screen.findByRole("heading", { name: "Create mock" }),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("Exam type")).toHaveValue("");
  expect(screen.getByLabelText("Price (INR)")).toHaveValue("29.00");
  expect(screen.getByText(/India Standard Time \(IST\)/)).toBeInTheDocument();
});

it("creates a mock, converts rupees to paise, and opens its detail page", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(Response.json(options))
    .mockResolvedValueOnce(Response.json(detail))
    .mockResolvedValueOnce(Response.json(detail));
  vi.stubGlobal("fetch", fetcher);

  renderPage();
  await fillRequiredFields();
  fireEvent.change(screen.getByLabelText("Price (INR)"), {
    target: { value: "29" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Create draft" }));

  expect(
    await screen.findByRole("heading", { name: "JEE Weekly Mock" }),
  ).toBeInTheDocument();
  const postCall = fetcher.mock.calls.find(
    ([, init]) => init?.method === "POST",
  );
  expect(JSON.parse(String(postCall?.[1]?.body))).toMatchObject({
    exam_type: examTypeId,
    exam_scheme: schemeId,
    price_paise: 2900,
    starts_at: "2026-11-10T09:00",
    ends_at: "2026-11-10T12:00",
  });
  expect(JSON.parse(String(postCall?.[1]?.body))).not.toHaveProperty("status");
});

it("shows backend validation errors on their fields", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(Response.json(options))
    .mockResolvedValueOnce(
      Response.json(
        {
          error: {
            code: "invalid_input",
            message: "Invalid input",
            details: { slug: ["A mock with this slug already exists."] },
          },
        },
        { status: 400 },
      ),
    );
  vi.stubGlobal("fetch", fetcher);

  renderPage();
  await fillRequiredFields();
  fireEvent.click(screen.getByRole("button", { name: "Create draft" }));

  expect(
    await screen.findByText("A mock with this slug already exists."),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("Slug")).toHaveAttribute("aria-invalid", "true");
});

it("loads an existing draft, shows IST wall time, preserves unchanged instants, and saves", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(Response.json(options))
    .mockResolvedValueOnce(Response.json(detail))
    .mockResolvedValueOnce(Response.json(detail))
    .mockResolvedValueOnce(Response.json(detail));
  vi.stubGlobal("fetch", fetcher);

  renderPage(`/owner/mocks/${mockId}/edit`);

  expect(
    await screen.findByRole("heading", { name: "Edit draft mock" }),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("Start date and time (IST)")).toHaveValue(
    "2026-11-10T09:00",
  );
  fireEvent.change(screen.getByLabelText("Title"), {
    target: { value: "Edited title" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save draft" }));

  expect(
    await screen.findByRole("heading", { name: "JEE Weekly Mock" }),
  ).toBeInTheDocument();
  const patchCall = fetcher.mock.calls.find(
    ([, init]) => init?.method === "PATCH",
  );
  expect(JSON.parse(String(patchCall?.[1]?.body))).toMatchObject({
    title: "Edited title",
    starts_at: "2026-11-10T03:30:00Z",
  });
});

it("shows a load error with retry and a network save error", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(
      Response.json(
        { error: { code: "unavailable", message: "Unavailable" } },
        { status: 503 },
      ),
    )
    .mockResolvedValueOnce(Response.json(options));
  vi.stubGlobal("fetch", fetcher);

  renderPage();
  expect(
    await screen.findByRole("heading", { name: "Mock form unavailable" }),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  await fillRequiredFields();
  fetcher.mockRejectedValueOnce(new Error("offline"));
  fireEvent.click(screen.getByRole("button", { name: "Create draft" }));

  expect(
    await screen.findByText(
      "The mock could not be saved. Check your connection and try again.",
    ),
  ).toBeInTheDocument();
});

it("converts display times in IST and rejects invalid rupee amounts", () => {
  expect(isoToIstDateTimeLocal("2026-11-10T03:30:00Z")).toBe(
    "2026-11-10T09:00:00",
  );
  expect(rupeesToPaise("29")).toBe(2900);
  expect(rupeesToPaise("29.50")).toBe(2950);
  expect(rupeesToPaise("0")).toBeNull();
  expect(rupeesToPaise("29.999")).toBeNull();
});
