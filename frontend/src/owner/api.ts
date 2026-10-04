import { apiBlobRequest, apiRequest } from "../api/client";
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

export const MOCK_STATUSES = [
  "DRAFT",
  "REGISTRATION_OPEN",
  "SCHEDULED",
  "LIVE",
  "CLOSED",
  "RESULTS_PUBLISHED",
  "CANCELLED",
] as const;

export type OwnerMockStatus = (typeof MOCK_STATUSES)[number];

export interface OwnerMockExamType {
  code: string;
  name: string;
  active: boolean;
}

export interface OwnerMockExamScheme {
  name: string;
  version: string;
  active: boolean;
  total_question_count: number;
  total_duration_minutes: number;
  maximum_marks: number;
}

export interface OwnerMockSummary {
  id: string;
  title: string;
  slug: string;
  exam_type: OwnerMockExamType;
  exam_scheme: OwnerMockExamScheme;
  status: OwnerMockStatus;
  status_label: string;
  starts_at: string;
  ends_at: string;
  result_release_at: string;
  price_paise: number;
  rules_verified_at: string | null;
  question_count: number;
}

export interface OwnerMockPhase {
  order: number;
  name: string;
  start_offset_minutes: number;
  duration_minutes: number;
  sequence_locked: boolean;
  question_count: number;
}

export interface OwnerMockDetail extends OwnerMockSummary {
  exam_type_id: string;
  exam_scheme_id: string;
  description: string;
  instructions_md: string;
  phases: OwnerMockPhase[];
  operational_warnings: string[];
}

export interface OwnerQuestionGroup {
  phase_order: number;
  phase_name: string;
  subject: string;
  question_type: string;
  count: number;
}

export interface OwnerQuestionSummary {
  id: string;
  question_number: number;
  phase_order: number;
  phase_name: string;
  subject: string;
  question_type: string;
  status: string;
  status_label: string;
  question_preview: string;
  has_image: boolean;
}

export interface OwnerQuestionDetail extends OwnerQuestionSummary {
  question_text_md: string;
  options: { label: string; text: string; has_image: boolean }[];
}

export interface OwnerQuestionsResponse {
  mock: {
    id: string;
    title: string;
    status: OwnerMockStatus;
    question_count: number;
    expected_question_count: number;
    read_only: boolean;
  };
  grouped_counts: OwnerQuestionGroup[];
  results: OwnerQuestionSummary[];
}

export interface OwnerQuestionImportPreview {
  valid: boolean;
  token: string;
  rows: {
    row: number;
    question_number: string;
    phase: string;
    subject: string;
    question_type: string;
    question_preview: string;
  }[];
  errors: { row: number | null; message: string }[];
  warnings: string[];
}

export interface OwnerMockTypeOption extends OwnerMockExamType {
  id: string;
}

export interface OwnerMockSchemeOption extends OwnerMockExamScheme {
  id: string;
  exam_type_id: string;
}

export interface OwnerMockOptions {
  exam_types: OwnerMockTypeOption[];
  exam_schemes: OwnerMockSchemeOption[];
}

export interface OwnerMockInput {
  exam_type: string;
  exam_scheme: string;
  title: string;
  slug: string;
  description: string;
  starts_at: string;
  ends_at: string;
  result_release_at: string;
  price_paise: number;
  instructions_md: string;
}

export interface OwnerMockFilters {
  search: string;
  examType: string;
  status: OwnerMockStatus | "";
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

export function ownerMocksApi(
  withAccess: AuthContextValue["withAccess"],
  filters: OwnerMockFilters,
  signal: AbortSignal,
) {
  const params = new URLSearchParams();
  const search = filters.search.trim();
  if (search) params.set("search", search);
  if (filters.examType) params.set("exam_type", filters.examType);
  if (filters.status) params.set("status", filters.status);
  const query = params.toString();

  return withAccess((token) =>
    apiRequest<{ results: OwnerMockSummary[] }>(
      `/owner/mocks/${query ? `?${query}` : ""}`,
      {
        cache: "no-store",
        headers: { Authorization: `Bearer ${token}` },
        signal,
      },
    ),
  );
}

export function ownerMockDetailApi(
  withAccess: AuthContextValue["withAccess"],
  mockId: string,
  signal: AbortSignal,
) {
  return withAccess((token) =>
    apiRequest<OwnerMockDetail>(`/owner/mocks/${encodeURIComponent(mockId)}/`, {
      cache: "no-store",
      headers: { Authorization: `Bearer ${token}` },
      signal,
    }),
  );
}

export function ownerMockOptionsApi(
  withAccess: AuthContextValue["withAccess"],
  signal: AbortSignal,
) {
  return withAccess((token) =>
    apiRequest<OwnerMockOptions>("/owner/mock-options/", {
      cache: "no-store",
      headers: { Authorization: `Bearer ${token}` },
      signal,
    }),
  );
}

export function createOwnerMockApi(
  withAccess: AuthContextValue["withAccess"],
  input: OwnerMockInput,
) {
  return withAccess((token) =>
    apiRequest<OwnerMockDetail>("/owner/mocks/", {
      method: "POST",
      cache: "no-store",
      headers: { Authorization: `Bearer ${token}` },
      body: JSON.stringify(input),
    }),
  );
}

export function updateOwnerMockApi(
  withAccess: AuthContextValue["withAccess"],
  mockId: string,
  input: OwnerMockInput,
) {
  return withAccess((token) =>
    apiRequest<OwnerMockDetail>(`/owner/mocks/${encodeURIComponent(mockId)}/`, {
      method: "PATCH",
      cache: "no-store",
      headers: { Authorization: `Bearer ${token}` },
      body: JSON.stringify(input),
    }),
  );
}

export function ownerQuestionsApi(
  withAccess: AuthContextValue["withAccess"],
  mockId: string,
  signal: AbortSignal,
) {
  return withAccess((token) =>
    apiRequest<OwnerQuestionsResponse>(
      `/owner/mocks/${encodeURIComponent(mockId)}/questions/`,
      {
        cache: "no-store",
        headers: { Authorization: `Bearer ${token}` },
        signal,
      },
    ),
  );
}

export function ownerQuestionDetailApi(
  withAccess: AuthContextValue["withAccess"],
  mockId: string,
  questionId: string,
  signal: AbortSignal,
) {
  return withAccess((token) =>
    apiRequest<OwnerQuestionDetail>(
      `/owner/mocks/${encodeURIComponent(mockId)}/questions/${encodeURIComponent(questionId)}/`,
      {
        cache: "no-store",
        headers: { Authorization: `Bearer ${token}` },
        signal,
      },
    ),
  );
}

export function previewOwnerQuestionImportApi(
  withAccess: AuthContextValue["withAccess"],
  mockId: string,
  file: File,
) {
  const formData = new FormData();
  formData.append("file", file);
  return withAccess((token) =>
    apiRequest<OwnerQuestionImportPreview>(
      `/owner/mocks/${encodeURIComponent(mockId)}/questions/import/preview/`,
      {
        method: "POST",
        cache: "no-store",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      },
    ),
  );
}

export function commitOwnerQuestionImportApi(
  withAccess: AuthContextValue["withAccess"],
  mockId: string,
  token: string,
) {
  return withAccess((accessToken) =>
    apiRequest<{ imported_count: number }>(
      `/owner/mocks/${encodeURIComponent(mockId)}/questions/import/commit/`,
      {
        method: "POST",
        cache: "no-store",
        headers: { Authorization: `Bearer ${accessToken}` },
        body: JSON.stringify({ token }),
      },
    ),
  );
}

export function ownerQuestionTemplateApi(
  withAccess: AuthContextValue["withAccess"],
  fileFormat: "csv" | "xlsx",
) {
  return withAccess((token) =>
    apiBlobRequest(`/owner/question-import/template/${fileFormat}/`, {
      cache: "no-store",
      headers: { Authorization: `Bearer ${token}` },
    }),
  );
}
