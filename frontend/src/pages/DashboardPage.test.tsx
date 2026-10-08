import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { DashboardData } from "../api/dashboard";
import { AuthContext, type AuthContextValue } from "../auth/auth-context";
import { DashboardPage } from "./DashboardPage";

const mock = {
  id: "mock-1",
  title: "JEE Main Full Mock 1",
  exam: "JEE Main",
  starts_at: "2026-10-11T04:30:00Z",
  ends_at: "2026-10-11T07:30:00Z",
  access_state: "PURCHASED" as const,
  lifecycle_state: "STARTING_SOON" as const,
  can_start: true,
  registration_available: false,
  attempt_id: null,
  attempt_status: null,
};
const data: DashboardData = {
  server_time: "2026-10-11T04:20:00Z",
  next_mock: mock,
  upcoming_mocks: [mock],
  latest_result: {
    mock_id: "result-1",
    mock_title: "JEE Main Full Mock 0",
    exam: "JEE Main",
    starts_at: "2026-09-27T04:30:00Z",
    maximum_score: "300.00",
    score: "151.00",
    rank: 42,
    percentile: "91.40",
    correct_count: 40,
    incorrect_count: 9,
    attempted_count: 49,
    unattempted_count: 26,
    previous_score: "126.00",
    score_difference: "25.00",
  },
  history: [],
};
const context: AuthContextValue = {
  status: "authenticated",
  user: null,
  loginWithGoogle: vi.fn(),
  logout: vi.fn(),
  getProfile: vi.fn(),
  saveProfile: vi.fn(),
  withAccess: (operation) => operation("token"),
};
function renderDashboard(response: DashboardData = data) {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify(response), { status: 200 }),
      ),
  );
  return render(
    <AuthContext.Provider value={context}>
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}
afterEach(() => vi.unstubAllGlobals());

it("renders the server-backed purchased mock countdown and start path", async () => {
  renderDashboard();
  expect(
    await screen.findByRole("heading", { name: mock.title }),
  ).toBeInTheDocument();
  expect(screen.getByText("Starts in")).toBeInTheDocument();
  expect(screen.getByText("Access purchased")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Start Test" })).toHaveAttribute(
    "href",
    "/mocks/mock-1/instructions",
  );
  expect(screen.getByText("+25 marks")).toBeInTheDocument();
  expect(screen.getByText("#42")).toBeInTheDocument();
});

it("renders unpurchased, in-progress and result-pending states without enabling a new start", async () => {
  renderDashboard({
    ...data,
    latest_result: null,
    upcoming_mocks: [
      {
        ...mock,
        access_state: "NOT_PURCHASED",
        registration_available: true,
        can_start: false,
        lifecycle_state: "UPCOMING",
      },
      {
        ...mock,
        id: "mock-2",
        title: "CET Mock",
        lifecycle_state: "ATTEMPT_IN_PROGRESS",
        attempt_id: "attempt-2",
        attempt_status: "IN_PROGRESS",
      },
      {
        ...mock,
        id: "mock-3",
        title: "Submitted mock",
        lifecycle_state: "RESULT_PENDING",
        can_start: false,
        attempt_status: "SUBMITTED",
      },
    ],
    next_mock: {
      ...mock,
      access_state: "NOT_PURCHASED",
      registration_available: true,
      can_start: false,
      lifecycle_state: "UPCOMING",
    },
  });
  expect(await screen.findByText("Not purchased")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Get access" })).toHaveAttribute(
    "href",
    "/mocks",
  );
  expect(screen.getByRole("link", { name: "Continue Test" })).toHaveAttribute(
    "href",
    "/exam/attempt-2",
  );
  expect(screen.getByText("Result pending")).toBeInTheDocument();
  expect(
    screen.getByText(/first mock result will appear here/i),
  ).toBeInTheDocument();
});

it("renders clean empty and generic error states", async () => {
  renderDashboard({
    ...data,
    next_mock: null,
    upcoming_mocks: [],
    latest_result: null,
    history: [],
  });
  expect(
    await screen.findByText(/No upcoming mocks right now/),
  ).toBeInTheDocument();
  expect(screen.getByText("No published results yet.")).toBeInTheDocument();
});

it("shows registration opens soon for an inactive offer without a checkout link", async () => {
  renderDashboard({
    ...data,
    next_mock: {
      ...mock,
      access_state: "NOT_PURCHASED",
      can_start: false,
      lifecycle_state: "UPCOMING",
      registration_available: false,
    },
    upcoming_mocks: [],
  });
  expect(await screen.findByText("Registration opens soon")).toBeInTheDocument();
  expect(
    screen.queryByRole("link", { name: "Get access" }),
  ).not.toBeInTheDocument();
});

it("shows get access when a future offer is actually purchasable", async () => {
  renderDashboard({
    ...data,
    next_mock: {
      ...mock,
      access_state: "NOT_PURCHASED",
      can_start: false,
      lifecycle_state: "UPCOMING",
      registration_available: true,
    },
    upcoming_mocks: [],
  });
  expect(
    await screen.findByRole("link", { name: "Get access" }),
  ).toHaveAttribute("href", "/mocks");
});
