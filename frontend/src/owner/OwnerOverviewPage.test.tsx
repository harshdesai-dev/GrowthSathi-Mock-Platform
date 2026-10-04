import { fireEvent, render, screen } from "@testing-library/react";

import type { AuthUser } from "../api/client";
import { AuthContext, type AuthContextValue } from "../auth/auth-context";
import { OwnerOverviewPage } from "./OwnerOverviewPage";

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

const overview = {
  total_students: 42,
  upcoming_mocks: 3,
  completed_mocks: 12,
  paid_orders: 27,
  failed_payments: 4,
  total_revenue_paise: 2900,
};

function withOwnerAccess<T>(operation: (token: string) => Promise<T>) {
  return operation("owner-access-token");
}

function renderOverview() {
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
      <OwnerOverviewPage />
    </AuthContext.Provider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

it("shows loading cards until the overview response arrives", async () => {
  let resolveFetch!: (response: Response) => void;
  const fetcher = vi.fn(
    () => new Promise<Response>((resolve) => (resolveFetch = resolve)),
  );
  vi.stubGlobal("fetch", fetcher);

  renderOverview();

  expect(
    screen.getByRole("status", { name: "Loading overview metrics" }),
  ).toHaveAttribute("aria-busy", "true");
  resolveFetch(Response.json(overview));
  expect(await screen.findByText("₹29")).toBeInTheDocument();
});

it("renders real aggregate counts and formats paise as INR", async () => {
  const fetcher = vi.fn().mockResolvedValue(Response.json(overview));
  vi.stubGlobal("fetch", fetcher);

  renderOverview();

  expect(await screen.findByText("₹29")).toBeInTheDocument();
  expect(screen.getByText("42")).toBeInTheDocument();
  expect(screen.getByText("3")).toBeInTheDocument();
  expect(screen.getByText("12")).toBeInTheDocument();
  expect(screen.getByText("27")).toBeInTheDocument();
  expect(screen.getByText("4")).toBeInTheDocument();
  expect(fetcher).toHaveBeenCalledWith(
    expect.stringMatching(/\/owner\/overview\/$/),
    expect.objectContaining({
      cache: "no-store",
      credentials: "include",
      headers: { Authorization: "Bearer owner-access-token" },
    }),
  );
});

it("renders genuine zero counts and zero revenue", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      Response.json({
        total_students: 0,
        upcoming_mocks: 0,
        completed_mocks: 0,
        paid_orders: 0,
        failed_payments: 0,
        total_revenue_paise: 0,
      }),
    ),
  );

  renderOverview();

  expect(await screen.findByText("₹0")).toBeInTheDocument();
  expect(screen.getAllByText("0")).toHaveLength(5);
});

it("shows an API error and retries successfully", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(
      Response.json(
        { error: { code: "unavailable", message: "Try again later." } },
        { status: 503 },
      ),
    )
    .mockResolvedValueOnce(Response.json(overview));
  vi.stubGlobal("fetch", fetcher);

  renderOverview();

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Overview unavailable",
  );
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));

  expect(await screen.findByText("₹29")).toBeInTheDocument();
  expect(fetcher).toHaveBeenCalledTimes(2);
});
