import type { Checkout, PaymentCallback } from "../api/commerce";

export interface RazorpayOptions extends Checkout {
  name: string;
  handler: (response: PaymentCallback) => void;
  modal: { ondismiss: () => void };
  theme: { color: string };
}

interface RazorpayInstance {
  open: () => void;
  on: (event: "payment.failed", handler: () => void) => void;
}

declare global {
  interface Window {
    Razorpay?: new (options: RazorpayOptions) => RazorpayInstance;
  }
}

let loading: Promise<void> | undefined;

export function loadCheckout(): Promise<void> {
  if (window.Razorpay) return Promise.resolve();
  if (!loading) {
    loading = new Promise<void>((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "https://checkout.razorpay.com/v1/checkout.js";
      script.async = true;
      const timer = window.setTimeout(() => fail(), 15000);
      const fail = () => {
        window.clearTimeout(timer);
        script.remove();
        loading = undefined;
        reject(
          new Error(
            "Checkout could not load. Check your connection and retry.",
          ),
        );
      };
      script.onerror = fail;
      script.onload = () => {
        window.clearTimeout(timer);
        if (window.Razorpay) resolve();
        else fail();
      };
      document.head.appendChild(script);
    });
  }
  return loading;
}

export async function openCheckout(
  checkout: Checkout,
  handlers: {
    success: (response: PaymentCallback) => void;
    failure: () => void;
    cancel: () => void;
  },
) {
  if (!checkout.key.startsWith("rzp_test_"))
    throw new Error("Only sandbox checkout is enabled.");
  await loadCheckout();
  const Razorpay = window.Razorpay;
  if (!Razorpay) throw new Error("Checkout is unavailable.");
  const instance = new Razorpay({
    ...checkout,
    name: "GrowthSathi · Test mode",
    handler: handlers.success,
    modal: { ondismiss: handlers.cancel },
    theme: { color: "#b7ff00" },
  });
  instance.on("payment.failed", handlers.failure);
  instance.open();
}
