import type { PropsWithChildren } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { useAuth } from "../auth/auth-context";
import { SessionLoadingPage } from "../components/auth/RouteGuards";

export function OwnerOnlyRoute({ children }: PropsWithChildren) {
  const { status, user } = useAuth();
  const location = useLocation();

  if (status === "loading") return <SessionLoadingPage />;
  if (status === "unauthenticated" || !user) {
    return <Navigate replace state={{ from: location.pathname }} to="/auth" />;
  }
  if (!user.is_staff || !user.is_superuser) {
    return (
      <Navigate
        replace
        to={user.onboarding_completed ? "/dashboard" : "/onboarding"}
      />
    );
  }

  return children;
}
