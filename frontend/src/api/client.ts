import { parseApiError } from "./errors";

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

export interface AuthUser {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  full_name: string;
  onboarding_completed: boolean;
  is_staff: boolean;
  is_superuser: boolean;
}

export interface StudentProfile {
  full_name: string;
  email: string;
  phone: string;
  class_level: "" | "11" | "12" | "DROPPER";
  target_exam: "" | "JEE" | "CET" | "BOTH";
  onboarding_completed: boolean;
}

export interface ProfileInput {
  full_name: string;
  phone: string;
  class_level: "11" | "12" | "DROPPER";
  target_exam: "JEE" | "CET" | "BOTH";
}

interface SessionResponse {
  access_token: string;
  token_type: "Bearer";
  expires_in: number;
  user?: AuthUser;
}

async function apiFetch(path: string, init: RequestInit): Promise<Response> {
  const bodyIsFormData =
    typeof FormData !== "undefined" && init.body instanceof FormData;
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    signal: init.signal ?? AbortSignal.timeout(15000),
    credentials: "include",
    headers: {
      ...(init.body && !bodyIsFormData
        ? { "Content-Type": "application/json" }
        : {}),
      ...init.headers,
    },
  });
  if (!response.ok) {
    throw await parseApiError(response);
  }
  return response;
}

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await apiFetch(path, init);
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export async function apiBlobRequest(
  path: string,
  init: RequestInit = {},
): Promise<Blob> {
  return (await apiFetch(path, init)).blob();
}

async function getCsrfToken(): Promise<string> {
  const response = await apiRequest<{ csrf_token: string }>("/auth/csrf/");
  return response.csrf_token;
}

export async function exchangeGoogleCredential(credential: string) {
  const csrfToken = await getCsrfToken();
  return apiRequest<SessionResponse & { user: AuthUser }>("/auth/google/", {
    method: "POST",
    headers: { "X-CSRFToken": csrfToken },
    body: JSON.stringify({ credential }),
  });
}

export async function refreshSession() {
  const csrfToken = await getCsrfToken();
  return apiRequest<SessionResponse>("/auth/refresh/", {
    method: "POST",
    headers: { "X-CSRFToken": csrfToken },
  });
}

export async function endSession() {
  const csrfToken = await getCsrfToken();
  return apiRequest<void>("/auth/logout/", {
    method: "POST",
    headers: { "X-CSRFToken": csrfToken },
  });
}

function bearer(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` };
}

export function fetchCurrentUser(token: string) {
  return apiRequest<AuthUser>("/auth/me/", { headers: bearer(token) });
}

export function fetchStudentProfile(token: string) {
  return apiRequest<StudentProfile>("/profile/", { headers: bearer(token) });
}

export function patchStudentProfile(token: string, profile: ProfileInput) {
  return apiRequest<StudentProfile>("/profile/", {
    method: "PATCH",
    headers: bearer(token),
    body: JSON.stringify(profile),
  });
}
