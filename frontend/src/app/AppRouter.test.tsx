import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { AuthUser, StudentProfile } from "../api/client";
import { AuthContext, type AuthContextValue } from "../auth/auth-context";
import { AppRoutes } from "./AppRouter";

vi.mock("@react-oauth/google", () => ({
  GoogleLogin: () => <button>Continue with Google</button>,
}));

const incompleteUser: AuthUser = {
  id: "student-id",
  email: "student@example.com",
  first_name: "Asha",
  last_name: "Patil",
  full_name: "Asha Patil",
  onboarding_completed: false,
  is_staff: false,
  is_superuser: false,
};

const ownerUser: AuthUser = {
  id: "owner-id",
  email: "owner@example.com",
  first_name: "GrowthSathi",
  last_name: "Owner",
  full_name: "GrowthSathi Owner",
  onboarding_completed: false,
  is_staff: true,
  is_superuser: true,
};

const emptyProfile: StudentProfile = {
  full_name: "Asha Patil",
  email: "student@example.com",
  phone: "",
  class_level: "",
  target_exam: "",
  onboarding_completed: false,
};

function authValue(
  overrides: Partial<AuthContextValue> = {},
): AuthContextValue {
  return {
    status: "unauthenticated",
    user: null,
    loginWithGoogle: vi.fn(),
    logout: vi.fn(),
    getProfile: vi.fn().mockResolvedValue(emptyProfile),
    saveProfile: vi.fn(),
    withAccess: vi.fn().mockResolvedValue([]),
    ...overrides,
  };
}

function withOwnerAccess<T>(operation: (token: string) => Promise<T>) {
  return operation("owner-token");
}

function renderRoute(path: string, value: AuthContextValue) {
  return render(
    <AuthContext.Provider value={value}>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

describe("Phase 1 route protection", () => {
  beforeEach(() => vi.stubEnv("VITE_GOOGLE_CLIENT_ID", "test-google-client"));
  afterEach(() => vi.unstubAllEnvs());

  it("redirects an unauthenticated student away from a protected route", () => {
    renderRoute("/dashboard", authValue());
    expect(
      screen.getByRole("heading", { name: "Prepare with purpose." }),
    ).toBeInTheDocument();
  });

  it("shows the public GrowthSathi landing page to a new visitor", () => {
    renderRoute("/", authValue());
    expect(
      screen.getByRole("heading", {
        name: /Exam ke din nahi. Aaj pata karo tum kaha stand karte ho./i,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Explore mock tests" }),
    ).toHaveAttribute("href", "/mocks");
  });

  it("redirects an incomplete student to onboarding", async () => {
    renderRoute(
      "/dashboard",
      authValue({ status: "authenticated", user: incompleteUser }),
    );
    expect(
      await screen.findByRole("heading", {
        name: "Build your student profile",
      }),
    ).toBeInTheDocument();
  });

  it("blocks an unauthenticated visitor from the owner area", async () => {
    renderRoute("/owner", authValue());

    expect(
      await screen.findByRole("heading", { name: "Prepare with purpose." }),
    ).toBeInTheDocument();
  });

  it("redirects a normal student away from the owner area", async () => {
    renderRoute(
      "/owner",
      authValue({ status: "authenticated", user: incompleteUser }),
    );

    expect(
      await screen.findByRole("heading", {
        name: "Build your student profile",
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Owner overview" }),
    ).not.toBeInTheDocument();
  });

  it("renders the owner area after backend owner access is confirmed", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(Response.json({ is_owner: true }))
        .mockResolvedValueOnce(
          Response.json({
            total_students: 3,
            upcoming_mocks: 2,
            completed_mocks: 4,
            paid_orders: 5,
            failed_payments: 1,
            total_revenue_paise: 2900,
          }),
        ),
    );
    renderRoute(
      "/owner",
      authValue({
        status: "authenticated",
        user: ownerUser,
        withAccess: withOwnerAccess,
      }),
    );

    expect(
      await screen.findByRole("heading", { name: "Owner overview" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("navigation", { name: "Owner navigation" }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Mocks" })[0]).toHaveAttribute(
      "href",
      "/owner/mocks",
    );
    expect(screen.getByText("Total students")).toBeInTheDocument();
    expect(screen.getByText("Upcoming mocks")).toBeInTheDocument();
    expect(screen.getByText("Completed mocks")).toBeInTheDocument();
    expect(screen.getByText("Paid orders")).toBeInTheDocument();
    expect(screen.getByText("Revenue")).toBeInTheDocument();
    expect(screen.getByText("Payment failures")).toBeInTheDocument();
    expect(await screen.findByText("₹29")).toBeInTheDocument();
  });

  it("keeps owner navigation working when opening the mock list", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(Response.json({ is_owner: true }))
        .mockResolvedValueOnce(
          Response.json({
            total_students: 0,
            upcoming_mocks: 0,
            completed_mocks: 0,
            paid_orders: 0,
            failed_payments: 0,
            total_revenue_paise: 0,
          }),
        )
        .mockResolvedValueOnce(Response.json({ results: [] })),
    );
    renderRoute(
      "/owner",
      authValue({
        status: "authenticated",
        user: ownerUser,
        withAccess: withOwnerAccess,
      }),
    );

    await screen.findByRole("heading", { name: "Owner overview" });
    fireEvent.click(screen.getAllByRole("link", { name: "Mocks" })[0]!);

    expect(
      await screen.findByRole("heading", { name: "No mocks yet" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Mocks", level: 1 }),
    ).toBeInTheDocument();
    expect(
      screen.getAllByRole("link", { name: "Overview" })[0],
    ).toHaveAttribute("href", "/owner");
  });

  it("lets a returning student bypass onboarding", () => {
    renderRoute(
      "/onboarding",
      authValue({
        status: "authenticated",
        user: { ...incompleteUser, onboarding_completed: true },
      }),
    );
    expect(
      screen.getByRole("heading", { name: "Welcome, Asha Patil." }),
    ).toBeInTheDocument();
  });
});
