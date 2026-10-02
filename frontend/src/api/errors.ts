export interface ApiErrorPayload {
  error: {
    code: string;
    message: string;
    details?: unknown;
  };
}

export class ApiError extends Error {
  readonly code: string;
  readonly details?: unknown;
  readonly status: number;

  constructor(status: number, payload: ApiErrorPayload) {
    super(payload.error.message);
    this.name = "ApiError";
    this.status = status;
    this.code = payload.error.code;
    this.details = payload.error.details;
  }
}

export async function parseApiError(response: Response): Promise<ApiError> {
  const fallback: ApiErrorPayload = {
    error: {
      code: "unexpected_error",
      message: "The request could not be completed.",
    },
  };

  try {
    const payload = (await response.json()) as ApiErrorPayload;
    if (payload?.error?.code && payload.error.message) {
      return new ApiError(response.status, payload);
    }
  } catch {
    // Use the stable fallback when an upstream response is not JSON.
  }

  return new ApiError(response.status, fallback);
}
