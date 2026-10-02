import { ApiError, parseApiError } from "./errors";

describe("parseApiError", () => {
  it("preserves the shared API error envelope", async () => {
    const response = new Response(
      JSON.stringify({
        error: { code: "invalid_input", message: "Invalid input" },
      }),
      { status: 400, headers: { "Content-Type": "application/json" } },
    );
    const error = await parseApiError(response);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.code).toBe("invalid_input");
    expect(error.status).toBe(400);
  });

  it("returns a stable fallback for non-JSON responses", async () => {
    const error = await parseApiError(
      new Response("Gateway failure", { status: 502 }),
    );
    expect(error.code).toBe("unexpected_error");
    expect(error.status).toBe(502);
  });
});
