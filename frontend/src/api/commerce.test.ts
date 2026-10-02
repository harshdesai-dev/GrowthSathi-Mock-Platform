import { createOrder, verifyPayment } from "./commerce";

afterEach(() => vi.unstubAllGlobals());

it("sends only the offer ID, never a client-calculated price or mock list", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValue(new Response("{}", { status: 200 }));
  vi.stubGlobal("fetch", fetcher);
  await createOrder("token", "offer-id");
  expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual({
    offer_id: "offer-id",
  });
  expect(fetcher.mock.calls[0][1].headers.Authorization).toBe("Bearer token");
});

it("requests authenticated server verification of the callback", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValue(new Response("{}", { status: 200 }));
  vi.stubGlobal("fetch", fetcher);
  await verifyPayment("token", "local-order", {
    razorpay_order_id: "order_test",
    razorpay_payment_id: "pay_test",
    razorpay_signature: "signature",
  });
  expect(fetcher.mock.calls[0][0]).toMatch(/payments\/verify\/$/);
  expect(JSON.parse(fetcher.mock.calls[0][1].body).order_id).toBe(
    "local-order",
  );
});
