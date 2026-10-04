import type { AuthUser } from "../api/client";

export function authenticatedHomePath(user: AuthUser): string {
  if (user.is_staff && user.is_superuser) return "/owner";
  return user.onboarding_completed ? "/dashboard" : "/onboarding";
}
