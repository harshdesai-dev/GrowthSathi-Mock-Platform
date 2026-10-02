import { useState } from "react";
import { useNavigate } from "react-router-dom";

import growthSathiLogo from "../assets/brand/growthsathi-logo.png";
import { useAuth } from "../auth/auth-context";

export function DashboardPage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [error, setError] = useState("");

  const handleLogout = async () => {
    setIsLoggingOut(true);
    setError("");
    try {
      await logout();
      navigate("/auth", { replace: true });
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Logout could not be completed.",
      );
      setIsLoggingOut(false);
    }
  };

  return (
    <main className="dashboard-shell">
      <nav className="dashboard-nav" aria-label="Student navigation">
        <div className="brand-lockup brand-lockup--small">
          <img src={growthSathiLogo} alt="GrowthSathi" width="52" height="52" />
          <span>GrowthSathi</span>
        </div>
        <button
          className="secondary-button"
          onClick={handleLogout}
          disabled={isLoggingOut}
        >
          {isLoggingOut ? "Signing out…" : "Sign out"}
        </button>
      </nav>
      <section
        className="dashboard-placeholder"
        aria-labelledby="dashboard-title"
      >
        <p className="eyebrow">Student account ready</p>
        <h1 id="dashboard-title">
          Welcome, {user?.full_name || user?.first_name}.
        </h1>
        <p>
          Your secure GrowthSathi account and student profile are ready.
          Mock-test features arrive in the next implementation phases.
        </p>
        <dl>
          <div>
            <dt>Signed in as</dt>
            <dd>{user?.email}</dd>
          </div>
          <div>
            <dt>Profile</dt>
            <dd>Onboarding complete</dd>
          </div>
        </dl>
        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}
      </section>
    </main>
  );
}
