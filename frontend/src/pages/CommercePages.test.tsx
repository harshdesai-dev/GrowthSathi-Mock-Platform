import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import * as api from "../api/commerce";
import { AuthContext, type AuthContextValue } from "../auth/auth-context";
import type { RazorpayOptions } from "../payments/razorpay";
import {
  CheckoutPage,
  LegalDraftPage,
  MockListingPage,
  PurchasedAccess,
} from "./CommercePages";

vi.mock("../api/commerce", async (original) => {
  const actual = await original<typeof api>();
  return {
    ...actual,
    listMocks: vi.fn(),
    listOffers: vi.fn(),
    getOffer: vi.fn(),
    createOrder: vi.fn(),
    getOrder: vi.fn(),
    verifyPayment: vi.fn(),
    listAccess: vi.fn(),
  };
});

const mock: api.Mock = {
  id: "mock-jee",
  title: "JEE October Mock",
  slug: "jee",
  description: "Practice",
  exam: "JEE_MAIN",
  scheme_version: "2026-review",
  status: "REGISTRATION_OPEN",
  starts_at: "2026-10-10T04:00:00Z",
  ends_at: "2026-10-10T07:00:00Z",
};
const offer: api.Offer = {
  id: "offer-jee",
  name: "JEE Main",
  offer_type: "JEE",
  price_paise: 2900,
  available: true,
  mocks: [mock],
  sales_start_at: "2026-10-01T00:00:00Z",
  sales_end_at: "2026-10-10T00:00:00Z",
};
const pending: api.Order = {
  id: "local-order",
  offer_name_snapshot: "JEE Main",
  total_amount_paise: 2900,
  currency: "INR",
  status: "PENDING",
  items: [{ id: "item", mock, price_paise_snapshot: 2900 }],
  checkout: {
    key: "rzp_test_public",
    order_id: "order_gateway",
    amount: 2900,
    currency: "INR",
    description: "JEE Main",
  },
};
const paid: api.Order = { ...pending, status: "PAID", checkout: null };
const callback = {
  razorpay_order_id: "order_gateway",
  razorpay_payment_id: "pay_example",
  razorpay_signature: "a".repeat(64),
};
const auth: AuthContextValue = {
  status: "authenticated",
  user: null,
  loginWithGoogle: vi.fn(),
  logout: vi.fn(),
  getProfile: vi.fn(),
  saveProfile: vi.fn(),
  withAccess: (operation) => operation("access-token"),
};
let options: RazorpayOptions;
let failed: () => void;
const opened = vi.fn();

function renderCheckout() {
  return render(
    <AuthContext.Provider value={auth}>
      <MemoryRouter initialEntries={["/checkout/offer-jee"]}>
        <Routes>
          <Route path="/checkout/:offerId" element={<CheckoutPage />} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.listMocks).mockResolvedValue([mock]);
  vi.mocked(api.listOffers).mockResolvedValue([
    offer,
    {
      ...offer,
      id: "combo",
      name: "JEE + CET",
      offer_type: "COMBO",
      price_paise: 5000,
    },
  ]);
  vi.mocked(api.getOffer).mockResolvedValue(offer);
  vi.mocked(api.createOrder).mockResolvedValue(pending);
  vi.mocked(api.getOrder).mockResolvedValue(pending);
  vi.mocked(api.verifyPayment).mockResolvedValue(paid);
  window.Razorpay = class {
    constructor(value: RazorpayOptions) {
      options = value;
    }
    open = opened;
    on(_event: "payment.failed", handler: () => void) {
      failed = handler;
    }
  };
});

afterEach(() => {
  delete window.Razorpay;
});

it("renders loading, offers, integer prices and published mocks", async () => {
  render(
    <MemoryRouter>
      <MockListingPage />
    </MemoryRouter>,
  );
  expect(screen.getByRole("status")).toHaveTextContent("Loading");
  expect(await screen.findByText("₹29")).toBeInTheDocument();
  expect(screen.getByText("₹50")).toBeInTheDocument();
  expect(screen.getAllByRole("link", { name: "View checkout" })).toHaveLength(
    2,
  );
  expect(api.price(5101)).toBe("₹51.01");
});

it("shows catalogue errors without a fabricated offer", async () => {
  vi.mocked(api.listOffers).mockRejectedValue(new Error("Service unavailable"));
  render(
    <MemoryRouter>
      <MockListingPage />
    </MemoryRouter>,
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Service unavailable",
  );
  expect(screen.queryByText("₹29")).not.toBeInTheDocument();
});

it("initializes checkout with backend fields and confirms only after server verification", async () => {
  let confirm!: (value: api.Order) => void;
  vi.mocked(api.verifyPayment).mockReturnValue(
    new Promise((resolve) => {
      confirm = resolve;
    }),
  );
  renderCheckout();
  fireEvent.click(
    await screen.findByRole("button", { name: "Open test checkout" }),
  );
  await waitFor(() => expect(opened).toHaveBeenCalledOnce());
  expect(api.createOrder).toHaveBeenCalledWith("access-token", "offer-jee");
  expect(options).toMatchObject({
    key: "rzp_test_public",
    order_id: "order_gateway",
    amount: 2900,
    currency: "INR",
  });
  act(() => options.handler(callback));
  expect(
    screen.queryByRole("heading", { name: "Payment confirmed" }),
  ).not.toBeInTheDocument();
  expect(api.verifyPayment).toHaveBeenCalledWith(
    "access-token",
    "local-order",
    callback,
  );
  await act(async () => confirm(paid));
  expect(
    await screen.findByRole("heading", { name: "Payment confirmed" }),
  ).toBeInTheDocument();
});

it.each(["failed", "cancelled"])(
  "shows a %s checkout state without granting access",
  async (state) => {
    renderCheckout();
    fireEvent.click(
      await screen.findByRole("button", { name: "Open test checkout" }),
    );
    await waitFor(() => expect(opened).toHaveBeenCalledOnce());
    act(() => {
      if (state === "failed") failed();
      else options.modal.ondismiss();
    });
    expect(screen.getByRole("status")).toHaveTextContent(state);
    expect(api.verifyPayment).not.toHaveBeenCalled();
    expect(screen.queryByText("Payment confirmed")).not.toBeInTheDocument();
  },
);

it("keeps rejected verification pending and can refresh a webhook-confirmed order", async () => {
  vi.mocked(api.verifyPayment).mockRejectedValue(new Error("Network timeout"));
  renderCheckout();
  fireEvent.click(
    await screen.findByRole("button", { name: "Open test checkout" }),
  );
  await waitFor(() => expect(opened).toHaveBeenCalledOnce());
  act(() => options.handler(callback));
  await waitFor(() =>
    expect(screen.getByRole("status")).toHaveTextContent(
      "Verification is pending",
    ),
  );
  vi.mocked(api.getOrder).mockResolvedValue(paid);
  fireEvent.click(
    screen.getByRole("button", { name: "Refresh payment status" }),
  );
  expect(
    await screen.findByRole("heading", { name: "Payment confirmed" }),
  ).toBeInTheDocument();
});

it("does not let a late pending lookup overwrite confirmed payment", async () => {
  let resolveLookup!: (value: api.Order) => void;
  vi.mocked(api.getOrder).mockReturnValue(
    new Promise((resolve) => {
      resolveLookup = resolve;
    }),
  );
  renderCheckout();
  fireEvent.click(
    await screen.findByRole("button", { name: "Open test checkout" }),
  );
  await waitFor(() => expect(api.getOrder).toHaveBeenCalled());
  act(() => options.handler(callback));
  expect(
    await screen.findByRole("heading", { name: "Payment confirmed" }),
  ).toBeInTheDocument();
  await act(async () => resolveLookup(pending));
  expect(
    screen.getByRole("heading", { name: "Payment confirmed" }),
  ).toBeInTheDocument();
});

it("displays purchased access and revoked states without an exam start button", async () => {
  vi.mocked(api.listAccess).mockResolvedValue([
    {
      id: "grant1",
      mock,
      status: "ACTIVE",
      has_access: true,
      granted_at: "2026-10-01",
    },
    {
      id: "grant2",
      mock: { ...mock, title: "Other mock" },
      status: "REVOKED",
      has_access: false,
      granted_at: "2026-10-01",
    },
  ]);
  render(
    <AuthContext.Provider value={auth}>
      <MemoryRouter>
        <PurchasedAccess />
      </MemoryRouter>
    </AuthContext.Provider>,
  );
  expect(await screen.findByText("Access purchased")).toBeInTheDocument();
  expect(screen.getByText("REVOKED")).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: /start/i }),
  ).not.toBeInTheDocument();
});

it("rejects live-mode checkout data", async () => {
  vi.mocked(api.createOrder).mockResolvedValue({
    ...pending,
    checkout: { ...pending.checkout!, key: "rzp_live_forbidden" },
  });
  renderCheckout();
  fireEvent.click(
    await screen.findByRole("button", { name: "Open test checkout" }),
  );
  expect(await screen.findByRole("status")).toHaveTextContent(
    "Only sandbox checkout",
  );
  expect(opened).not.toHaveBeenCalled();
});

it("clearly labels legal copy as an unapproved draft", () => {
  render(
    <MemoryRouter initialEntries={["/refund-policy"]}>
      <LegalDraftPage />
    </MemoryRouter>,
  );
  expect(
    screen.getByText("Draft placeholder · Not approved"),
  ).toBeInTheDocument();
  expect(screen.getByText(/Live payments remain disabled/)).toBeInTheDocument();
});
