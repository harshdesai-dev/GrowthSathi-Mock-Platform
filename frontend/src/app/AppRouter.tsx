import { BrowserRouter, Route, Routes } from "react-router-dom";

import {
  CompletedProfileRoute,
  HomeRoute,
  OnboardingRoute,
  PublicAuthRoute,
} from "../components/auth/RouteGuards";
import { AuthPage } from "../pages/AuthPage";
import { DashboardPage } from "../pages/DashboardPage";
import {
  CheckoutPage,
  LegalDraftPage,
  MockDetailPage,
  MockListingPage,
} from "../pages/CommercePages";
import { NotFoundPage } from "../pages/NotFoundPage";
import { OnboardingPage } from "../pages/OnboardingPage";

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/mocks" element={<MockListingPage />} />
      <Route path="/mocks/:mockId" element={<MockDetailPage />} />
      <Route
        path="/checkout/:offerId"
        element={
          <CompletedProfileRoute>
            <CheckoutPage />
          </CompletedProfileRoute>
        }
      />
      <Route path="/privacy" element={<LegalDraftPage />} />
      <Route path="/terms" element={<LegalDraftPage />} />
      <Route path="/refund-policy" element={<LegalDraftPage />} />
      <Route path="/" element={<HomeRoute />} />
      <Route
        path="/auth"
        element={
          <PublicAuthRoute>
            <AuthPage />
          </PublicAuthRoute>
        }
      />
      <Route
        path="/onboarding"
        element={
          <OnboardingRoute>
            <OnboardingPage />
          </OnboardingRoute>
        }
      />
      <Route
        path="/dashboard"
        element={
          <CompletedProfileRoute>
            <DashboardPage />
          </CompletedProfileRoute>
        }
      />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}

export function AppRouter() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  );
}
