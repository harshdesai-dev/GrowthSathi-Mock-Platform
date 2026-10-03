import { render, screen } from "@testing-library/react";
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
