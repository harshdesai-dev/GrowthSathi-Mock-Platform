import { GoogleLogin, type CredentialResponse } from "@react-oauth/google";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import growthSathiLogo from "../assets/brand/growthsathi-logo.webp";
import { useAuth } from "../auth/auth-context";

export function AuthPage() {
  const { loginWithGoogle } = useAuth();
  const navigate = useNavigate();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");
  const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;

  const handleSuccess = async (response: CredentialResponse) => {
    if (!response.credential) {
      setError(
        "Google did not return a usable sign-in credential. Please try again.",
      );
      return;
    }
    setIsSubmitting(true);
    setError("");
    try {
      const user = await loginWithGoogle(response.credential);
      navigate(user.onboarding_completed ? "/dashboard" : "/onboarding", {
        replace: true,
      });
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Google sign-in could not be completed.",
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className="auth-shell">
      <section className="auth-card" aria-labelledby="auth-title">
        <div className="brand-lockup">
          <img src={growthSathiLogo} alt="GrowthSathi" width="88" height="88" />
          <span>GrowthSathi</span>
        </div>
        <p className="eyebrow">Mock tests. Real exam discipline.</p>
        <h1 id="auth-title">Prepare with purpose.</h1>
        <p className="auth-intro">
          Sign in to continue to your JEE Main and MHT-CET mock-test account.
        </p>

        <div className="google-signin" aria-busy={isSubmitting}>
          {isSubmitting ? (
            <p className="status-message">Verifying your Google account…</p>
          ) : googleClientId ? (
            <GoogleLogin
              onSuccess={handleSuccess}
              onError={() =>
                setError(
                  "Google sign-in was cancelled or failed. Please try again.",
                )
              }
              theme="filled_black"
              shape="pill"
              size="large"
              text="continue_with"
              width="320"
            />
          ) : (
            <p className="form-error" role="alert">
              Google Sign-In is not configured for this environment.
            </p>
          )}
        </div>
        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}
        <p className="auth-footnote">
          Google is the only sign-in method for GrowthSathi.
        </p>
        <Link to="/mocks">Browse mocks and offers</Link>
      </section>
    </main>
  );
}
