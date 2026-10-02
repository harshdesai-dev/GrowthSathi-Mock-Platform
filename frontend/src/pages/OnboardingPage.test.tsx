import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { AuthUser, StudentProfile } from "../api/client";
import { AuthContext, type AuthContextValue } from "../auth/auth-context";
import { OnboardingPage } from "./OnboardingPage";

const user: AuthUser = {
  id: "student-id",
  email: "student@example.com",
  first_name: "Asha",
  last_name: "Patil",
  full_name: "Asha Patil",
  onboarding_completed: false,
  is_staff: false,
};

const profile: StudentProfile = {
  full_name: "Asha Patil",
  email: user.email,
  phone: "",
  class_level: "",
  target_exam: "",
  onboarding_completed: false,
};

function renderOnboarding(saveProfile = vi.fn()): AuthContextValue {
  const value: AuthContextValue = {
    status: "authenticated",
    user,
    loginWithGoogle: vi.fn(),
    logout: vi.fn(),
    getProfile: vi.fn().mockResolvedValue(profile),
    saveProfile,
  };
  render(
    <AuthContext.Provider value={value}>
      <MemoryRouter initialEntries={["/onboarding"]}>
        <Routes>
          <Route path="/onboarding" element={<OnboardingPage />} />
          <Route path="/dashboard" element={<p>Dashboard destination</p>} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  );
  return value;
}

describe("student onboarding", () => {
  it("validates required fields and the Indian phone format", async () => {
    renderOnboarding();
    await screen.findByDisplayValue("Asha Patil");
    fireEvent.change(screen.getByLabelText("Indian mobile number"), {
      target: { value: "12345" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Continue to dashboard" }),
    );

    expect(
      await screen.findByText("Enter a valid 10-digit Indian mobile number."),
    ).toBeInTheDocument();
    expect(screen.getByText("Select your class.")).toBeInTheDocument();
    expect(screen.getByText("Choose a target exam.")).toBeInTheDocument();
  });

  it("saves valid onboarding and navigates to the dashboard", async () => {
    const saveProfile = vi.fn().mockResolvedValue({
      ...profile,
      phone: "+919876543210",
      class_level: "12",
      target_exam: "BOTH",
      onboarding_completed: true,
    });
    renderOnboarding(saveProfile);
    await screen.findByDisplayValue("Asha Patil");

    fireEvent.change(screen.getByLabelText("Indian mobile number"), {
      target: { value: "98765 43210" },
    });
    fireEvent.change(screen.getByLabelText("Class"), {
      target: { value: "12" },
    });
    fireEvent.click(screen.getByLabelText("Both"));
    fireEvent.click(
      screen.getByRole("button", { name: "Continue to dashboard" }),
    );

    await waitFor(() => expect(saveProfile).toHaveBeenCalledOnce());
    expect(
      await screen.findByText("Dashboard destination"),
    ).toBeInTheDocument();
  });
});
