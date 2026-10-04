import type { PropsWithChildren } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { useAuth } from "../../auth/auth-context";
import { authenticatedHomePath } from "../../auth/routes";
import { LandingPage } from "../../pages/LandingPage";

export function SessionLoadingPage() {
  return (
    <main className="auth-shell" aria-busy="true">
      <p className="status-message">Restoring your secure session…</p>
    </main>
  );
}

export function PublicAuthRoute({ children }: PropsWithChildren) {
  const { status, user } = useAuth();
  if (status === "loading") return <SessionLoadingPage />;
  if (status === "authenticated" && user) {
    return <Navigate replace to={authenticatedHomePath(user)} />;
  }
  return children;
}

export function OnboardingRoute({ children }: PropsWithChildren) {
  const { status, user } = useAuth();
  const location = useLocation();
  if (status === "loading") return <SessionLoadingPage />;
  if (status === "unauthenticated" || !user) {
    return <Navigate replace state={{ from: location.pathname }} to="/auth" />;
  }
  if (user.is_staff && user.is_superuser) {
    return <Navigate replace to="/owner" />;
  }
  if (user.onboarding_completed) return <Navigate replace to="/dashboard" />;
  return children;
}

export function CompletedProfileRoute({ children }: PropsWithChildren) {
  const { status, user } = useAuth();
  const location = useLocation();
  if (status === "loading") return <SessionLoadingPage />;
  if (status === "unauthenticated" || !user) {
    return <Navigate replace state={{ from: location.pathname }} to="/auth" />;
  }
  if (!user.onboarding_completed) return <Navigate replace to="/onboarding" />;
  return children;
}

export function HomeRoute() {
  const { status, user } = useAuth();
  if (status === "loading") return <SessionLoadingPage />;
  if (status === "unauthenticated" || !user) return <LandingPage />;
  return <Navigate replace to={authenticatedHomePath(user)} />;
}
