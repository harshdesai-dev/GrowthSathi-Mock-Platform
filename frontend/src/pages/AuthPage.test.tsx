import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { AuthUser } from "../api/client";
import { AuthContext, type AuthContextValue } from "../auth/auth-context";
import { AuthPage } from "./AuthPage";

vi.mock("@react-oauth/google", () => ({
  GoogleOAuthProvider: ({ children }: { children: React.ReactNode }) =>
    children,
  GoogleLogin: ({
    onSuccess,
  }: {
    onSuccess: (response: { credential?: string }) => void;
  }) => (
    <button onClick={() => onSuccess({ credential: "google-id-token" })}>
      Continue with Google
    </button>
  ),
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

function contextValue(
  loginWithGoogle: AuthContextValue["loginWithGoogle"],
): AuthContextValue {
  return {
    status: "unauthenticated",
    user: null,
    loginWithGoogle,
    logout: vi.fn(),
    getProfile: vi.fn(),
    saveProfile: vi.fn(),
    withAccess: vi.fn(),
  };
}

function renderAuth(value: AuthContextValue) {
  return render(
    <AuthContext.Provider value={value}>
      <MemoryRouter initialEntries={["/auth"]}>
        <Routes>
          <Route path="/auth" element={<AuthPage />} />
          <Route path="/onboarding" element={<p>Onboarding destination</p>} />
          <Route path="/dashboard" element={<p>Dashboard destination</p>} />
          <Route path="/owner" element={<p>Owner destination</p>} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

describe("Google login", () => {
  beforeEach(() => vi.stubEnv("VITE_GOOGLE_CLIENT_ID", "test-google-client"));
  afterEach(() => vi.unstubAllEnvs());

  it("shows a loading state and navigates after a successful first login", async () => {
    let resolveLogin!: (user: AuthUser) => void;
    const loginWithGoogle = vi.fn(
      () => new Promise<AuthUser>((resolve) => (resolveLogin = resolve)),
    );
    renderAuth(contextValue(loginWithGoogle));

    fireEvent.click(
      screen.getByRole("button", { name: "Continue with Google" }),
    );
    expect(
      screen.getByText("Verifying your Google account…"),
    ).toBeInTheDocument();
    resolveLogin(incompleteUser);

    expect(
      await screen.findByText("Onboarding destination"),
    ).toBeInTheDocument();
    expect(loginWithGoogle).toHaveBeenCalledWith("google-id-token");
  });

  it("shows an authentication failure returned by the API", async () => {
    const loginWithGoogle = vi
      .fn()
      .mockRejectedValue(new Error("Identity conflict"));
    renderAuth(contextValue(loginWithGoogle));

    fireEvent.click(
      screen.getByRole("button", { name: "Continue with Google" }),
    );

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("Identity conflict"),
    );
  });

  it("routes an owner to the owner area after sign-in", async () => {
    const owner: AuthUser = {
      ...incompleteUser,
      is_staff: true,
      is_superuser: true,
    };
    renderAuth(contextValue(vi.fn().mockResolvedValue(owner)));

    fireEvent.click(
      screen.getByRole("button", { name: "Continue with Google" }),
    );

    expect(await screen.findByText("Owner destination")).toBeInTheDocument();
  });
});
