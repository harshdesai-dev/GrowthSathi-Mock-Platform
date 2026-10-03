import { apiRequest } from "./client";
import type { AuthContextValue } from "../auth/auth-context";
import type { ResultSummary } from "./results";

export type DashboardAccessState = "PURCHASED" | "NOT_PURCHASED" | "CANCELLED";
export type DashboardLifecycleState =
  | "UPCOMING"
  | "STARTING_SOON"
  | "LIVE"
  | "ATTEMPT_IN_PROGRESS"
  | "SUBMITTED"
  | "RESULT_PENDING"
  | "RESULTS_PUBLISHED"
  | "CANCELLED";

export interface DashboardMock {
  id: string;
  title: string;
  exam: string;
  starts_at: string;
  ends_at: string;
  access_state: DashboardAccessState;
  lifecycle_state: DashboardLifecycleState;
  can_start: boolean;
  attempt_id: string | null;
  attempt_status:
    "IN_PROGRESS" | "SUBMITTED" | "AUTO_SUBMITTED" | "INVALID" | null;
}

export interface DashboardResult extends ResultSummary {
  previous_score: string | null;
  score_difference: string | null;
}

export interface DashboardData {
  server_time: string;
  next_mock: DashboardMock | null;
  upcoming_mocks: DashboardMock[];
  latest_result: DashboardResult | null;
  history: ResultSummary[];
}

export function dashboardApi(withAccess: AuthContextValue["withAccess"]) {
  return withAccess((token) =>
    apiRequest<DashboardData>("/dashboard/", {
      cache: "no-store",
      headers: { Authorization: `Bearer ${token}` },
    }),
  );
}
