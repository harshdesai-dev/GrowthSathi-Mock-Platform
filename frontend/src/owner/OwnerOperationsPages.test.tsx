import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { AuthUser } from "../api/client";
import { AuthContext, type AuthContextValue } from "../auth/auth-context";
import type { OwnerMockDetail, OwnerResultMock } from "./api";
import { OwnerMockDetailPage } from "./OwnerMockDetailPage";
import {
  OwnerMockResultsPage,
  OwnerStudentsPage,
} from "./OwnerOperationsPages";

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

const mockId = "e34c80b1-48b9-4d9b-a965-54e85c3ad1a7";
const runId = "65c2250e-b5a3-49af-927c-3aaa123d9a34";

const detail: OwnerMockDetail = {
  id: mockId,
  title: "JEE Weekly Mock",
  slug: "jee-weekly-mock",
  exam_type: { code: "JEE_MAIN", name: "JEE Main", active: true },
  exam_scheme: {
    name: "Official scheme",
    version: "2026",
    active: true,
    total_question_count: 75,
    total_duration_minutes: 180,
    maximum_marks: 300,
  },
  status: "REGISTRATION_OPEN",
  status_label: "Registration open",
  starts_at: "2026-10-10T04:00:00Z",
  ends_at: "2026-10-10T07:00:00Z",
  result_release_at: "2026-10-11T04:00:00Z",
  price_paise: 2900,
  rules_verified_at: "2026-10-01T04:00:00Z",
  question_count: 75,
  exam_type_id: "exam-type",
  exam_scheme_id: "scheme",
  rules_source_notes: "Official source checked.",
  description: "",
  instructions_md: "",
  phases: [],
  operational_warnings: [],
  allowed_transitions: ["SCHEDULED", "CANCELLED"],
};

const resultMock: OwnerResultMock = {
  id: mockId,
  title: "JEE Weekly Mock",
  status: "CLOSED",
  attempt_count: 4,
  result_release_at: "2026-10-01T04:00:00Z",
  calculation_state: "COMPLETE",
  verification_state: "VERIFIED",
  publication_state: "READY",
  latest_run: {
    id: runId,
    status: "COMPLETE",
    started_at: "2026-10-01T04:00:00Z",
    completed_at: "2026-10-01T04:05:00Z",
    key_verified_at: "2026-10-01T04:00:00Z",
    participant_count: 4,
    excluded_attempt_count: 0,
    notes: "Checked",
    errors: "",
    published_at: null,
  },
  operational_warnings: [],
  runs: [],
};

function renderOwner(element: React.ReactNode, path: string, route: string) {
  const context: AuthContextValue = {
    status: "authenticated",
    user: owner,
    loginWithGoogle: vi.fn(),
    logout: vi.fn(),
    getProfile: vi.fn(),
    saveProfile: vi.fn(),
    withAccess: (operation) => operation("owner-token"),
  };
  return render(
    <AuthContext.Provider value={context}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route element={element} path={route} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

it("confirms and posts only a legal lifecycle action", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(Response.json(detail))
    .mockResolvedValueOnce(Response.json({ ...detail, status: "SCHEDULED" }));
  vi.stubGlobal("fetch", fetcher);
  const confirm = vi.fn(() => true);
  vi.stubGlobal("confirm", confirm);
  renderOwner(
    <OwnerMockDetailPage />,
    `/owner/mocks/${mockId}`,
    "/owner/mocks/:mockId",
  );

  fireEvent.click(await screen.findByRole("button", { name: "Schedule mock" }));
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
  expect(confirm).toHaveBeenCalled();
  expect(fetcher.mock.calls[1][0]).toContain(
    `/owner/mocks/${mockId}/transition/`,
  );
  expect(fetcher.mock.calls[1][1]?.body).toBe(
    JSON.stringify({ target: "SCHEDULED", confirmed: true }),
  );
});

it("requires confirmation before publishing a complete result batch", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(Response.json(resultMock))
    .mockResolvedValueOnce(Response.json(resultMock.latest_run))
    .mockResolvedValueOnce(Response.json(resultMock));
  vi.stubGlobal("fetch", fetcher);
  vi.stubGlobal(
    "confirm",
    vi.fn(() => true),
  );
  renderOwner(
    <OwnerMockResultsPage />,
    `/owner/mocks/${mockId}/results`,
    "/owner/mocks/:mockId/results",
  );

  fireEvent.click(
    await screen.findByRole("button", { name: "Publish verified results" }),
  );
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(3));
  expect(fetcher.mock.calls[1][0]).toContain(
    `/owner/mocks/${mockId}/results/${runId}/publish/`,
  );
});

it("renders the paginated read-only student list", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      Response.json({
        count: 1,
        next: null,
        previous: null,
        results: [
          {
            id: "student-id",
            name: "Asha Student",
            email: "asha@example.com",
            phone: "+919876543210",
            class_level: "12",
            exam_target: "JEE",
            onboarding_completed: true,
            joined_at: "2026-09-01T04:00:00Z",
            purchased_mocks_count: 2,
            attempts_count: 1,
          },
        ],
      }),
    ),
  );
  renderOwner(<OwnerStudentsPage />, "/owner/students", "/owner/students");
  expect(await screen.findByText("Asha Student")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "View student" })).toHaveAttribute(
    "href",
    "/owner/students/student-id",
  );
});
