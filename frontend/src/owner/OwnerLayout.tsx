import { useCallback, useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { ApiError } from "../api/errors";
import { useAuth } from "../auth/auth-context";
import growthSathiLogo from "../assets/brand/growthsathi-logo.webp";
import { ownerAccessApi } from "./api";
import "./owner.css";

const navigation = [
  { label: "Offers", to: "/owner/offers" },
  { label: "Students", to: "/owner/students" },
  { label: "Payments", to: "/owner/payments" },
  { label: "Results", to: "/owner/results" },
] as const;

function OwnerNavigation({ label = "Owner navigation" }: { label?: string }) {
  return (
    <nav aria-label={label} className="owner-navigation">
      <NavLink className="owner-navigation__link" end to="/owner">
        <span>Overview</span>
        <span aria-hidden="true" className="owner-navigation__marker" />
      </NavLink>
      <NavLink className="owner-navigation__link" to="/owner/mocks">
        <span>Mocks</span>
        <span aria-hidden="true" className="owner-navigation__marker" />
      </NavLink>
      {navigation.map((item) => (
        <NavLink className="owner-navigation__link" key={item.to} to={item.to}>
          <span>{item.label}</span>
          <span aria-hidden="true" className="owner-navigation__marker" />
        </NavLink>
      ))}
    </nav>
  );
}

function AccessCheckPage({
  retry,
  status,
}: {
  retry?: () => void;
  status: "checking" | "denied" | "error";
}) {
  if (status === "checking") {
    return (
      <main className="owner-access-page" role="status">
        <span aria-hidden="true" className="owner-access-page__indicator" />
        <p>Checking owner access…</p>
      </main>
    );
  }
  if (status === "denied") {
    return (
      <main className="owner-access-page" role="alert">
        <p className="eyebrow">Access restricted</p>
        <h1>Owner access is required.</h1>
      </main>
    );
  }
  return (
    <main className="owner-access-page" role="alert">
      <p className="eyebrow">Connection issue</p>
      <h1>Could not verify owner access.</h1>
      <p>Check your connection and try again.</p>
      <button className="primary-button" onClick={retry} type="button">
        Try again
      </button>
    </main>
  );
}

export function OwnerLayout() {
  const { user, logout, withAccess } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [access, setAccess] = useState<
    "checking" | "allowed" | "denied" | "error"
  >("checking");
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  const verifyAccess = useCallback(async () => {
    try {
      const result = await ownerAccessApi(withAccess);
      setAccess(result.is_owner ? "allowed" : "denied");
    } catch (error) {
      setAccess(
        error instanceof ApiError && error.status === 403 ? "denied" : "error",
      );
    }
  }, [withAccess]);

  useEffect(() => {
    let active = true;
    void ownerAccessApi(withAccess)
      .then((result) => {
        if (active) setAccess(result.is_owner ? "allowed" : "denied");
      })
      .catch((error: unknown) => {
        if (active) {
          setAccess(
            error instanceof ApiError && error.status === 403
              ? "denied"
              : "error",
          );
        }
      });
    return () => {
      active = false;
    };
  }, [withAccess]);

  const handleLogout = async () => {
    setIsLoggingOut(true);
    try {
      await logout();
      navigate("/auth", { replace: true });
    } catch {
      setIsLoggingOut(false);
    }
  };

  if (access !== "allowed") {
    return (
      <AccessCheckPage
        retry={
          access === "error"
            ? () => {
                setAccess("checking");
                void verifyAccess();
              }
            : undefined
        }
        status={access}
      />
    );
  }

  const ownerName = user?.full_name || user?.first_name || "Owner";
  const sectionHeading = location.pathname.startsWith("/owner/mocks")
    ? "Mocks"
    : location.pathname.startsWith("/owner/offers")
      ? "Offers"
      : location.pathname.startsWith("/owner/students")
      ? "Students"
      : location.pathname.startsWith("/owner/payments")
        ? "Payments"
        : location.pathname.startsWith("/owner/results")
          ? "Results"
          : "Overview";

  return (
    <div className="owner-shell">
      <aside className="owner-sidebar">
        <div className="owner-brand">
          <img alt="" height="48" src={growthSathiLogo} width="48" />
          <span>GrowthSathi</span>
        </div>
        <p className="owner-sidebar__label">Owner dashboard</p>
        <OwnerNavigation />
      </aside>

      <div className="owner-workspace">
        <div className="owner-mobile-bar">
          <div className="owner-brand owner-brand--mobile">
            <img alt="" height="40" src={growthSathiLogo} width="40" />
            <span>GrowthSathi</span>
          </div>
          <details className="owner-mobile-menu">
            <summary className="secondary-button">Menu</summary>
            <div className="owner-mobile-menu__panel">
              <OwnerNavigation label="Owner mobile navigation" />
            </div>
          </details>
        </div>

        <header className="owner-topbar">
          <div>
            <p className="eyebrow">GrowthSathi operations</p>
            <h1>{sectionHeading}</h1>
          </div>
          <div className="owner-account">
            <span className="owner-account__identity">
              <strong>{ownerName}</strong>
              <small>{user?.email}</small>
            </span>
            <button
              className="secondary-button"
              disabled={isLoggingOut}
              onClick={handleLogout}
              type="button"
            >
              {isLoggingOut ? "Signing out…" : "Sign out"}
            </button>
          </div>
        </header>

        <main className="owner-page">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
