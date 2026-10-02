import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type PropsWithChildren,
} from "react";
import {
  Link,
  useLocation,
  useParams,
  useSearchParams,
} from "react-router-dom";

import {
  createOrder,
  getMock,
  getOffer,
  getOrder,
  listAccess,
  listMocks,
  listOffers,
  price,
  verifyPayment,
  type Offer,
  type Order,
} from "../api/commerce";
import growthSathiLogo from "../assets/brand/growthsathi-logo.png";
import { useAuth } from "../auth/auth-context";
import { openCheckout } from "../payments/razorpay";

function useLoad<T>(load: () => Promise<T>) {
  const [result, setResult] = useState<{
    load: () => Promise<T>;
    data?: T;
    error: string;
  }>();
  useEffect(() => {
    let current = true;
    void load()
      .then((value) => {
        if (current) setResult({ load, data: value, error: "" });
      })
      .catch((caught: unknown) => {
        if (current)
          setResult({
            load,
            error:
              caught instanceof Error
                ? caught.message
                : "Unable to load. Please refresh.",
          });
      });
    return () => {
      current = false;
    };
  }, [load]);
  return result?.load === load ? result : { data: undefined, error: "" };
}

export function CommerceShell({ children }: PropsWithChildren) {
  return (
    <main className="commerce-shell">
      <nav className="commerce-nav" aria-label="Main navigation">
        <Link className="brand-lockup brand-lockup--small" to="/mocks">
          <img src={growthSathiLogo} width="48" height="48" alt="GrowthSathi" />
          <span>GrowthSathi</span>
        </Link>
        <Link to="/dashboard">My account</Link>
      </nav>
      {children}
      <footer className="commerce-footer">
        <span>Sandbox only · No live payments</span>
        <Link to="/privacy">Privacy (draft)</Link>
        <Link to="/terms">Terms (draft)</Link>
        <Link to="/refund-policy">Refund policy (draft)</Link>
      </footer>
    </main>
  );
}

function LoadState({ error }: { error: string }) {
  return error ? (
    <p role="alert" className="form-error">
      {error}
    </p>
  ) : (
    <p role="status">Loading…</p>
  );
}

function OfferCard({ offer }: { offer: Offer }) {
  return (
    <article
      className={`offer-card ${offer.offer_type === "COMBO" ? "offer-card--combo" : ""}`}
    >
      <p className="eyebrow">
        {offer.offer_type === "COMBO"
          ? "Two exams. One offer."
          : "One focused practice."}
      </p>
      <h3>{offer.name}</h3>
      <p className="offer-price">{price(offer.price_paise)}</p>
      <ul>
        {offer.mocks.map((mock) => (
          <li key={mock.id}>
            <Link to={`/mocks/${mock.id}`}>{mock.title}</Link>
          </li>
        ))}
      </ul>
      <p>{offer.available ? "Registration open" : "Not currently available"}</p>
      {offer.available && (
        <Link className="primary-button" to={`/checkout/${offer.id}`}>
          View checkout
        </Link>
      )}
    </article>
  );
}

const loadCatalogue = () => Promise.all([listMocks(), listOffers()]);
export function MockListingPage() {
  const { data, error } = useLoad(loadCatalogue);
  return (
    <CommerceShell>
      <header className="commerce-heading">
        <p className="eyebrow">GrowthSathi mock tests</p>
        <h1>
          Your next mock.
          <br />
          <span>Make it count.</span>
        </h1>
        <p>Choose JEE Main, MHT-CET PCM, or an explicit two-mock combo.</p>
      </header>
      {!data ? (
        <LoadState error={error} />
      ) : (
        <>
          <h2>Choose your offer</h2>
          <div className="offer-grid">
            {data[1].map((offer) => (
              <OfferCard key={offer.id} offer={offer} />
            ))}
          </div>
          {!data[1].length && (
            <p>
              No offers are published yet. Check back when registration opens.
            </p>
          )}
          <h2>Mock schedule</h2>
          <div className="mock-list">
            {data[0].map((mock) => (
              <Link key={mock.id} to={`/mocks/${mock.id}`} className="mock-row">
                <strong>{mock.title}</strong>
                <span>
                  {new Date(mock.starts_at).toLocaleString("en-IN", {
                    timeZone: "Asia/Kolkata",
                  })}{" "}
                  IST
                </span>
                <span>{mock.status.replaceAll("_", " ")}</span>
              </Link>
            ))}
          </div>
        </>
      )}
    </CommerceShell>
  );
}

export function MockDetailPage() {
  const { mockId = "" } = useParams();
  const loader = useCallback(
    () => Promise.all([getMock(mockId), listOffers()]),
    [mockId],
  );
  const { data, error } = useLoad(loader);
  return (
    <CommerceShell>
      <Link to="/mocks">← All mocks</Link>
      {!data ? (
        <LoadState error={error} />
      ) : (
        <>
          <header className="commerce-heading">
            <p className="eyebrow">{data[0].exam.replaceAll("_", " ")}</p>
            <h1>{data[0].title}</h1>
            <p>{data[0].description}</p>
            <p>
              {new Date(data[0].starts_at).toLocaleString("en-IN", {
                timeZone: "Asia/Kolkata",
              })}{" "}
              IST
            </p>
            <p>
              Scheme: {data[0].scheme_version} ·{" "}
              {data[0].status.replaceAll("_", " ")}
            </p>
          </header>
          <h2>Offers containing this mock</h2>
          <div className="offer-grid">
            {data[1]
              .filter((offer) => offer.mocks.some((mock) => mock.id === mockId))
              .map((offer) => (
                <OfferCard key={offer.id} offer={offer} />
              ))}
          </div>
          <p>
            Purchasing records access only. The exam interface is not available
            in this phase.
          </p>
        </>
      )}
    </CommerceShell>
  );
}

export function CheckoutPage() {
  const { offerId = "" } = useParams();
  const { withAccess } = useAuth();
  const [params, setParams] = useSearchParams();
  const loader = useCallback(() => getOffer(offerId), [offerId]);
  const { data: offer, error: loadError } = useLoad(loader);
  const [order, setOrder] = useState<Order>();
  const acceptOrder = useCallback((next: Order) => {
    setOrder((previous) =>
      previous?.id === next.id &&
      (previous.status === "REFUNDED" ||
        (previous.status === "PAID" && next.status !== "REFUNDED"))
        ? previous
        : next,
    );
  }, []);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const verifying = useRef(false);
  const orderId = params.get("order");
  useEffect(() => {
    let current = true;
    if (orderId)
      void withAccess((token) => getOrder(token, orderId))
        .then((value) => {
          if (current) acceptOrder(value);
        })
        .catch((caught: unknown) => {
          if (current)
            setMessage(
              caught instanceof Error
                ? caught.message
                : "Unable to check order.",
            );
        });
    return () => {
      current = false;
    };
  }, [orderId, withAccess, acceptOrder]);

  const refresh = async () => {
    if (!order) return;
    setBusy(true);
    try {
      acceptOrder(await withAccess((token) => getOrder(token, order.id)));
      setMessage("");
    } catch {
      setMessage(
        "Status could not be refreshed. Do not pay again if money was deducted.",
      );
    } finally {
      setBusy(false);
    }
  };

  const buy = async () => {
    setBusy(true);
    setMessage("");
    verifying.current = false;
    try {
      const created = await withAccess((token) => createOrder(token, offerId));
      acceptOrder(created);
      setParams({ order: created.id }, { replace: true });
      if (!created.checkout) {
        setMessage(
          "Checkout is not ready. Refresh status or contact support with your order ID.",
        );
        setBusy(false);
        return;
      }
      await openCheckout(created.checkout, {
        success: (callback) => {
          verifying.current = true;
          setMessage("Verifying payment securely…");
          void withAccess((token) => verifyPayment(token, created.id, callback))
            .then((verified) => {
              acceptOrder(verified);
              setMessage(
                verified.status === "PAID"
                  ? ""
                  : "Payment is awaiting capture. Refresh status shortly.",
              );
            })
            .catch(() => {
              setMessage(
                "Verification is pending. Do not pay again if money was deducted; refresh status or contact support.",
              );
            })
            .finally(() => setBusy(false));
        },
        failure: () => {
          if (!verifying.current) {
            setMessage(
              "Payment failed. No access is granted without server confirmation.",
            );
            setBusy(false);
          }
        },
        cancel: () => {
          if (!verifying.current) {
            setMessage(
              "Checkout cancelled. If money was deducted, refresh status before trying again.",
            );
            setBusy(false);
          }
        },
      });
    } catch (caught) {
      setMessage(
        caught instanceof Error ? caught.message : "Checkout is unavailable.",
      );
      setBusy(false);
    }
  };

  return (
    <CommerceShell>
      <Link to="/mocks">← Back to mocks</Link>
      <section className="checkout-panel">
        <p className="eyebrow">Secure checkout · Test mode</p>
        <h1>
          {order?.status === "PAID"
            ? "Payment confirmed"
            : "Review your purchase"}
        </h1>
        {!offer ? (
          <LoadState error={loadError} />
        ) : (
          <>
            <h2>{order?.offer_name_snapshot ?? offer.name}</h2>
            <p className="offer-price">
              {price(order?.total_amount_paise ?? offer.price_paise)}
            </p>
            <ul>
              {(order?.items.map((item) => item.mock) ?? offer.mocks).map(
                (mock) => (
                  <li key={mock.id}>{mock.title}</li>
                ),
              )}
            </ul>
          </>
        )}
        <p>This is a sandbox checkout. Do not use live credentials.</p>
        {order && (
          <>
            <p>
              Order: <code>{order.id}</code>
            </p>
            <p>Backend status: {order.status}</p>
          </>
        )}
        {order?.status === "PAID" ? (
          <>
            <p>
              Your payment is verified. Check your account for each mock’s
              access status.
            </p>
            <Link className="primary-button" to="/dashboard">
              View purchased access
            </Link>
          </>
        ) : order?.status === "REFUNDED" ? (
          <p>This order has been refunded.</p>
        ) : (
          <button
            className="primary-button"
            disabled={busy || !offer?.available}
            onClick={() => void buy()}
          >
            {busy ? "Processing…" : "Open test checkout"}
          </button>
        )}
        {order && (
          <button
            className="secondary-button"
            disabled={busy}
            onClick={() => void refresh()}
          >
            Refresh payment status
          </button>
        )}
        {message && <p role="status">{message}</p>}
        <p>
          Policy pages are drafts awaiting owner approval. Live payments are
          disabled.
        </p>
      </section>
    </CommerceShell>
  );
}

export function PurchasedAccess() {
  const { withAccess } = useAuth();
  const loader = useCallback(() => withAccess(listAccess), [withAccess]);
  const { data, error } = useLoad(loader);
  return (
    <section className="purchased-access">
      <h2>Your mock access</h2>
      <Link to="/mocks">Browse mocks and offers →</Link>
      {!data ? (
        <LoadState error={error} />
      ) : !data.length ? (
        <p>No purchased access yet.</p>
      ) : (
        data.map((grant) => (
          <article className="mock-row" key={grant.id}>
            <Link to={`/mocks/${grant.mock.id}`}>{grant.mock.title}</Link>
            <strong>
              {grant.has_access
                ? "Access purchased"
                : grant.status === "ACTIVE"
                  ? "Mock cancelled — contact support"
                  : grant.status}
            </strong>
            <span>Exam interface coming in a later phase.</span>
          </article>
        ))
      )}
    </section>
  );
}

export function LegalDraftPage() {
  const path = useLocation().pathname;
  const title =
    path === "/privacy"
      ? "Privacy"
      : path === "/terms"
        ? "Terms"
        : "Refund policy";
  return (
    <CommerceShell>
      <section className="commerce-heading">
        <p className="eyebrow">Draft placeholder · Not approved</p>
        <h1>{title}</h1>
        <p>
          Owner-approved legal text has not been supplied. This page is not a
          legally authoritative policy or legal advice.
        </p>
        <p>
          Live payments remain disabled. Only sandbox development is enabled.
        </p>
        {title === "Refund policy" && (
          <>
            <h2>Approved product rules awaiting legal review</h2>
            <p>
              Refund eligibility is limited to cancelled mocks, duplicate
              verified payments, or confirmed GrowthSathi platform failure
              preventing access.
            </p>
            <p>
              No refund for no-show, late arrival, or student-side device or
              internet issues after exam start.
            </p>
          </>
        )}
      </section>
    </CommerceShell>
  );
}
