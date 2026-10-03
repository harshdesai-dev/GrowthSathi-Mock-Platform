import { apiRequest } from "../api/client";

export interface Answer {
  question_id: string;
  selected_option: string | null;
  numeric_answer: string;
  marked_for_review: boolean;
  mutation_version: number;
}
export type AnswerInput = Omit<Answer, "question_id" | "mutation_version">;
export interface AttemptState {
  attempt_id: string;
  mock_id: string;
  mock_title: string;
  status: "IN_PROGRESS" | "SUBMITTED" | "AUTO_SUBMITTED" | "INVALID";
  server_time: string;
  started_at: string;
  mock_starts_at: string;
  mock_ends_at: string;
  submitted_at: string | null;
  current_phase: { id: string; name: string; order: number } | null;
  phase_starts_at: string | null;
  phase_ends_at: string | null;
  can_submit: boolean;
  responses: Answer[];
  saved_response_count: number;
  answered_count: number;
  question_count: number;
}
export interface Question {
  id: string;
  question_number: number;
  phase_id: string;
  subject: string;
  question_type: "MCQ_SINGLE" | "NUMERICAL";
  question_text_md: string;
  question_image_url: string;
  options: {
    id: string;
    label: string;
    option_text_md: string;
    option_image_url: string;
  }[];
}
export interface ExamInfo {
  mock_id: string;
  title: string;
  instructions_md: string;
  server_time: string;
  starts_at: string;
  ends_at: string;
  can_start: boolean;
  attempt_id: string | null;
  attempt_status: AttemptState["status"] | null;
  phases: {
    name: string;
    order: number;
    start_offset_minutes: number;
    duration_minutes: number;
  }[];
}
export interface Paper {
  state: AttemptState;
  questions: Question[];
}
export interface Saved {
  response: Answer;
  acknowledgement: string;
  server_time: string;
}
export type Authorized = <T>(
  operation: (token: string) => Promise<T>,
) => Promise<T>;

export function examApi(access: Authorized) {
  const request = <T>(path: string, method = "GET", body?: unknown) =>
    access((token) =>
      apiRequest<T>(path, {
        method,
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
        signal: AbortSignal.timeout(path.endsWith("/start/") ? 60000 : 15000),
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      }),
    );
  return {
    info: (id: string) => request<ExamInfo>(`/mocks/${id}/exam-info/`),
    start: (id: string) =>
      request<AttemptState>(`/mocks/${id}/start/`, "POST", {}),
    state: (id: string) => request<AttemptState>(`/attempts/${id}/`),
    paper: (id: string) => request<Paper>(`/attempts/${id}/paper/`),
    heartbeat: (id: string) =>
      request<AttemptState>(`/attempts/${id}/heartbeat/`, "POST", {}),
    save: (id: string, answer: Answer) => {
      const { question_id, ...body } = answer;
      return request<Saved>(
        `/attempts/${id}/responses/${question_id}/`,
        "PUT",
        body,
      );
    },
    submit: (id: string) =>
      request<AttemptState>(`/attempts/${id}/submit/`, "POST", {}),
  };
}
export type ExamApi = ReturnType<typeof examApi>;
export function blankAnswer(question_id: string): Answer {
  return {
    question_id,
    selected_option: null,
    numeric_answer: "",
    marked_for_review: false,
    mutation_version: 0,
  };
}
