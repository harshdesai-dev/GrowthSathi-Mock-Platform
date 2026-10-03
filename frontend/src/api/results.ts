import { apiRequest } from "./client";
import type { AuthContextValue } from "../auth/auth-context";

export interface ResultSummary {
  mock_id: string;
  mock_title: string;
  exam: string;
  starts_at: string;
  maximum_score: string;
  score: string;
  rank: number;
  percentile: string;
  correct_count: number;
  incorrect_count: number;
  attempted_count: number;
  unattempted_count: number;
}
export interface Report extends ResultSummary {
  student_name: string;
  previous_score: string | null;
  score_difference: string | null;
}
export interface Leaderboard {
  mock_title: string;
  rows: { rank: number; name: string; score: string; percentile: string }[];
}
export interface ReviewQuestion {
  id: string;
  question_number: number;
  question_type: "MCQ_SINGLE" | "NUMERICAL";
  question_text_md: string;
  question_image_url: string;
  options: {
    id: string;
    label: string;
    option_text_md: string;
    option_image_url: string;
  }[];
  selected_option: string | null;
  numeric_answer: string;
  correct_option: string | null;
  correct_numeric_answer: string | null;
  numeric_tolerance: string;
  outcome: "Correct" | "Incorrect" | "Unattempted";
  marks: string;
  explanation_md: string;
}
export interface Review {
  mock_title: string;
  questions: ReviewQuestion[];
}

export function resultsApi(withAccess: AuthContextValue["withAccess"]) {
  const get = <T>(path: string) =>
    withAccess((token) =>
      apiRequest<T>(path, {
        cache: "no-store",
        headers: { Authorization: `Bearer ${token}` },
      }),
    );
  return {
    report: (id: string) =>
      get<Report>(`/mocks/${encodeURIComponent(id)}/result/`),
    leaderboard: (id: string) =>
      get<Leaderboard>(`/mocks/${encodeURIComponent(id)}/leaderboard/`),
    review: (id: string) =>
      get<Review>(`/mocks/${encodeURIComponent(id)}/review/`),
    history: () => get<ResultSummary[]>("/results/history/"),
  };
}
