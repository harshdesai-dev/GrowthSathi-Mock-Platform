import { lazy, Suspense } from "react";
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
const ExamInstructionsPage = lazy(() =>
  import("../pages/ExamPages").then((module) => ({
    default: module.ExamInstructionsPage,
  })),
);
const ExamPage = lazy(() =>
  import("../pages/ExamPages").then((module) => ({ default: module.ExamPage })),
);
const ResultPage = lazy(() =>
  import("../pages/ResultPages").then((module) => ({
    default: module.ResultPage,
  })),
);
const LeaderboardPage = lazy(() =>
  import("../pages/ResultPages").then((module) => ({
    default: module.LeaderboardPage,
  })),
);
const ReviewPage = lazy(() =>
  import("../pages/ResultPages").then((module) => ({
    default: module.ReviewPage,
  })),
);
const ResultHistoryPage = lazy(() =>
  import("../pages/ResultPages").then((module) => ({
    default: module.ResultHistoryPage,
  })),
);

export function AppRoutes() {
  return (
    <Routes>
      {[
        { path: "/results", element: <ResultHistoryPage /> },
        { path: "/results/:mockId", element: <ResultPage /> },
        { path: "/results/:mockId/leaderboard", element: <LeaderboardPage /> },
        { path: "/results/:mockId/review", element: <ReviewPage /> },
      ].map((route) => (
        <Route
          key={route.path}
          path={route.path}
          element={
            <CompletedProfileRoute>
              <Suspense fallback={<p role="status">Loading results…</p>}>
                {route.element}
              </Suspense>
            </CompletedProfileRoute>
          }
        />
      ))}
      <Route
        path="/mocks/:mockId/instructions"
        element={
          <CompletedProfileRoute>
            <Suspense
              fallback={<p role="status">Loading exam instructions…</p>}
            >
              <ExamInstructionsPage />
            </Suspense>
          </CompletedProfileRoute>
        }
      />
      <Route
        path="/exam/:attemptId"
        element={
          <CompletedProfileRoute>
            <Suspense fallback={<p role="status">Loading exam interface…</p>}>
              <ExamPage />
            </Suspense>
          </CompletedProfileRoute>
        }
      />
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
