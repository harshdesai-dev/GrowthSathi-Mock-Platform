import { apiRequest } from "../api/client";
import type { AuthContextValue } from "../auth/auth-context";

export interface OwnerAccess {
  is_owner: boolean;
}

export interface OwnerOverview {
  total_students: number;
  upcoming_mocks: number;
  completed_mocks: number;
  paid_orders: number;
  failed_payments: number;
  total_revenue_paise: number;
}

export function ownerAccessApi(withAccess: AuthContextValue["withAccess"]) {
  return withAccess((token) =>
    apiRequest<OwnerAccess>("/owner/access/", {
      cache: "no-store",
      headers: { Authorization: `Bearer ${token}` },
    }),
  );
}

export function ownerOverviewApi(withAccess: AuthContextValue["withAccess"]) {
  return withAccess((token) =>
    apiRequest<OwnerOverview>("/owner/overview/", {
      cache: "no-store",
      headers: { Authorization: `Bearer ${token}` },
    }),
  );
}
