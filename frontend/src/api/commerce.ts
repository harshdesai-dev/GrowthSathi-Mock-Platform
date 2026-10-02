import { apiRequest } from "./client";

export interface Mock {
  id: string;
  title: string;
  slug: string;
  description: string;
  exam: "JEE_MAIN" | "MHT_CET_PCM";
  scheme_version: string;
  status: string;
  starts_at: string;
  ends_at: string;
}

export interface Offer {
  id: string;
  name: string;
  offer_type: "JEE" | "CET" | "COMBO";
  price_paise: number;
  available: boolean;
  mocks: Mock[];
  sales_start_at: string;
  sales_end_at: string;
}

export interface Checkout {
  key: string;
  order_id: string;
  amount: number;
  currency: "INR";
  description: string;
}

export interface Order {
  id: string;
  offer_name_snapshot: string;
  total_amount_paise: number;
  currency: "INR";
  status: "CREATED" | "PENDING" | "PAID" | "FAILED" | "REFUNDED";
  items: { id: string; mock: Mock; price_paise_snapshot: number }[];
  checkout: Checkout | null;
}

export interface AccessGrant {
  id: string;
  mock: Mock;
  status: "ACTIVE" | "REVOKED" | "REFUNDED";
  has_access: boolean;
  granted_at: string;
}

export interface PaymentCallback {
  razorpay_order_id: string;
  razorpay_payment_id: string;
  razorpay_signature: string;
}

const headers = (token: string) => ({ Authorization: `Bearer ${token}` });
export const listMocks = () => apiRequest<Mock[]>("/mocks/");
export const getMock = (id: string) => apiRequest<Mock>(`/mocks/${id}/`);
export const listOffers = () => apiRequest<Offer[]>("/offers/");
export const getOffer = (id: string) => apiRequest<Offer>(`/offers/${id}/`);
export const listAccess = (token: string) =>
  apiRequest<AccessGrant[]>("/access/", { headers: headers(token) });
export const createOrder = (token: string, offerId: string) =>
  apiRequest<Order>("/orders/", {
    method: "POST",
    headers: headers(token),
    body: JSON.stringify({ offer_id: offerId }),
  });
export const getOrder = (token: string, id: string) =>
  apiRequest<Order>(`/orders/${id}/`, { headers: headers(token) });
export const verifyPayment = (
  token: string,
  orderId: string,
  callback: PaymentCallback,
) =>
  apiRequest<Order>("/payments/verify/", {
    method: "POST",
    headers: headers(token),
    body: JSON.stringify({ order_id: orderId, ...callback }),
  });

// Money is stored/calculated by the server in integer paise; this is display only.
export function price(paise: number): string {
  const rupees = Math.floor(paise / 100).toLocaleString("en-IN");
  const remainder = paise % 100;
  return `₹${rupees}${remainder ? `.${String(remainder).padStart(2, "0")}` : ""}`;
}
