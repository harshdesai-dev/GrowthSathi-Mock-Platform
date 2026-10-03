import { afterEach, expect, it, vi } from "vitest";

import { exchangeGoogleCredential } from "./client";

afterEach(() => vi.unstubAllGlobals());

it("bootstraps CSRF before exchanging a Google ID token", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(Response.json({ csrf_token: "csrf-fixture" }))
    .mockResolvedValueOnce(Response.json({ access_token: "access-fixture" }));
  vi.stubGlobal("fetch", fetcher);

  await exchangeGoogleCredential("google-fixture");

  expect(fetcher.mock.calls[0][0]).toMatch(/\/auth\/csrf\/$/);
  expect(fetcher.mock.calls[1][0]).toMatch(/\/auth\/google\/$/);
  expect(fetcher.mock.calls[1][1]).toMatchObject({
    method: "POST",
    credentials: "include",
    headers: { "X-CSRFToken": "csrf-fixture" },
    body: JSON.stringify({ credential: "google-fixture" }),
  });
});
