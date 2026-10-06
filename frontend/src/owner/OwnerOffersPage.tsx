import { useEffect, useMemo, useState } from "react";

import { ApiError } from "../api/errors";
import { price } from "../api/commerce";
import { useAuth } from "../auth/auth-context";
import {
  createOwnerOfferApi,
  ownerMocksApi,
  ownerOffersApi,
  setOwnerOfferActiveApi,
  updateOwnerOfferApi,
  type OwnerMockSummary,
  type OwnerOffer,
  type OwnerOfferInput,
  type OwnerOfferType,
} from "./api";
import { isoToIstDateTimeLocal, istDateTimeLocalToIso, rupeesToPaise } from "./mockForm.utils";

const offerLabels: Record<OwnerOfferType, string> = {
  JEE: "JEE Main",
  CET: "MHT-CET PCM",
  COMBO: "JEE + CET",
};

const saleableStatuses = new Set(["REGISTRATION_OPEN", "SCHEDULED", "LIVE"]);

type FormState = {
  name: string;
  slug: string;
  offer_type: OwnerOfferType;
  price_rupees: string;
  sales_start_at: string;
  sales_end_at: string;
  mock_ids: string[];
};

const emptyForm: FormState = {
  name: "",
  slug: "",
  offer_type: "JEE",
  price_rupees: "29.00",
  sales_start_at: "",
  sales_end_at: "",
  mock_ids: [],
};

function errorMessage(error: unknown) {
  if (error instanceof ApiError) {
    const details = error.details;
    if (details && typeof details === "object") {
      const text = Object.values(details as Record<string, unknown>)
        .flatMap((value) => (Array.isArray(value) ? value : [value]))
        .filter((value): value is string => typeof value === "string")
        .join(" ");
      if (text) return text;
    }
    return error.message;
  }
  return "The request could not be completed.";
}

function formFromOffer(offer: OwnerOffer): FormState {
  return {
    name: offer.name,
    slug: offer.slug,
    offer_type: offer.offer_type,
    price_rupees: (offer.price_paise / 100).toFixed(2),
    sales_start_at: isoToIstDateTimeLocal(offer.sales_start_at),
    sales_end_at: isoToIstDateTimeLocal(offer.sales_end_at),
    mock_ids: offer.mocks.map((mock) => mock.id),
  };
}

export function OwnerOffersPage() {
  const { withAccess } = useAuth();
  const [offers, setOffers] = useState<OwnerOffer[]>([]);
  const [mocks, setMocks] = useState<OwnerMockSummary[]>([]);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [editing, setEditing] = useState<OwnerOffer | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    void Promise.all([
      ownerOffersApi(withAccess, controller.signal),
      ownerMocksApi(
        withAccess,
        { search: "", examType: "", status: "" },
        controller.signal,
      ),
    ])
      .then(([offerResult, mockResult]) => {
        setOffers(offerResult.results);
        setMocks(mockResult.results);
        setState("ready");
      })
      .catch(() => setState("error"));
    return () => controller.abort();
  }, [withAccess, refreshKey]);

  const selectableMocks = useMemo(
    () =>
      mocks.filter((mock) => {
        if (!saleableStatuses.has(mock.status)) return false;
        if (form.offer_type === "JEE")
          return mock.exam_type.code === "JEE_MAIN";
        if (form.offer_type === "CET")
          return mock.exam_type.code === "MHT_CET_PCM";
        return ["JEE_MAIN", "MHT_CET_PCM"].includes(mock.exam_type.code);
      }),
    [mocks, form.offer_type],
  );

  const expectedMockCount = form.offer_type === "COMBO" ? 2 : 1;

  const setValue = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((current) => ({
      ...current,
      [key]: value,
      ...(key === "offer_type" ? { mock_ids: [] } : {}),
    }));
    setMessage("");
  };

  const reset = () => {
    setEditing(null);
    setForm(emptyForm);
    setMessage("");
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    const paise = rupeesToPaise(form.price_rupees);
    if (paise === null) {
      setMessage("Enter a valid positive price.");
      return;
    }
    if (form.mock_ids.length !== expectedMockCount) {
      setMessage(
        form.offer_type === "COMBO"
          ? "Choose exactly one JEE mock and one MHT-CET mock."
          : "Choose exactly one mock.",
      );
      return;
    }
    if (form.offer_type === "COMBO") {
      const codes = new Set(
        form.mock_ids
          .map((id) => mocks.find((mock) => mock.id === id)?.exam_type.code)
          .filter(Boolean),
      );
      if (!codes.has("JEE_MAIN") || !codes.has("MHT_CET_PCM")) {
        setMessage(
          "A combo must include one JEE Main mock and one MHT-CET PCM mock.",
        );
        return;
      }
    }

    const salesStart = istDateTimeLocalToIso(form.sales_start_at);
    const salesEnd = istDateTimeLocalToIso(form.sales_end_at);
    if (!salesStart || !salesEnd) {
      setMessage("Enter valid sales start and end times in IST.");
      return;
    }

    const input: OwnerOfferInput = {
      name: form.name.trim(),
      slug: form.slug.trim(),
      offer_type: form.offer_type,
      price_paise: paise,
      sales_start_at: salesStart,
      sales_end_at: salesEnd,
      mock_ids: form.mock_ids,
    };

    setBusy(true);
    setMessage("");
    try {
      if (editing) {
        await updateOwnerOfferApi(withAccess, editing.id, input);
        setMessage("Offer updated.");
      } else {
        await createOwnerOfferApi(withAccess, input);
        setMessage("Offer created. Activate it when ready for students.");
      }
      setEditing(null);
      setForm(emptyForm);
      setRefreshKey((value) => value + 1);
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(false);
    }
  };

  const toggle = async (offer: OwnerOffer) => {
    const action = offer.active ? "Deactivate" : "Activate";
    if (!window.confirm(`${action} "${offer.name}"?`)) return;
    setBusy(true);
    setMessage("");
    try {
      await setOwnerOfferActiveApi(withAccess, offer.id, !offer.active);
      setMessage(`Offer ${offer.active ? "deactivated" : "activated"}.`);
      setRefreshKey((value) => value + 1);
      if (editing?.id === offer.id) reset();
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(false);
    }
  };

  if (state === "loading") {
    return <p role="status">Loading offers…</p>;
  }
  if (state === "error") {
    return (
      <section
        className="owner-mocks-state owner-mocks-state--error"
        role="alert"
      >
        <h2>Offers unavailable</h2>
        <p>Wake the backend if needed, then try again.</p>
        <button
          className="primary-button"
          onClick={() => {
            setState("loading");
            setRefreshKey((value) => value + 1);
          }}
          type="button"
        >
          Try again
        </button>
      </section>
    );
  }

  return (
    <section className="owner-offers-page">
      <header className="owner-list-heading">
        <div>
          <p className="eyebrow">Commerce operations</p>
          <h2>Offers</h2>
          <p>Create JEE, CET or combo offers without using Django Admin.</p>
        </div>
      </header>

      {message && (
        <p className="owner-offer-message" role="status">
          {message}
        </p>
      )}

      <form
        className="owner-operation-panel owner-offer-form"
        onSubmit={submit}
      >
        <div className="owner-operation-panel__heading">
          <h3>{editing ? "Edit inactive offer" : "Create offer"}</h3>
          {editing && (
            <button className="secondary-button" onClick={reset} type="button">
              Cancel edit
            </button>
          )}
        </div>

        <label>
          <span>Name</span>
          <input
            maxLength={160}
            onChange={(event) => setValue("name", event.target.value)}
            required
            value={form.name}
          />
        </label>
        <label>
          <span>Slug</span>
          <input
            maxLength={50}
            onChange={(event) => setValue("slug", event.target.value)}
            pattern="[a-z0-9]+(?:-[a-z0-9]+)*"
            required
            value={form.slug}
          />
        </label>
        <label>
          <span>Offer type</span>
          <select
            onChange={(event) =>
              setValue("offer_type", event.target.value as OwnerOfferType)
            }
            value={form.offer_type}
          >
            {Object.entries(offerLabels).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Price (INR)</span>
          <input
            inputMode="decimal"
            onChange={(event) => setValue("price_rupees", event.target.value)}
            required
            value={form.price_rupees}
          />
        </label>
        <label>
          <span>Sales start (IST)</span>
          <input
            onChange={(event) => setValue("sales_start_at", event.target.value)}
            required
            type="datetime-local"
            value={form.sales_start_at}
          />
        </label>
        <label>
          <span>Sales end (IST)</span>
          <input
            onChange={(event) => setValue("sales_end_at", event.target.value)}
            required
            type="datetime-local"
            value={form.sales_end_at}
          />
        </label>

        <fieldset className="owner-offer-mocks">
          <legend>
            Included mock{expectedMockCount > 1 ? "s" : ""} · choose{" "}
            {expectedMockCount}
          </legend>
          {!selectableMocks.length ? (
            <p>
              No registration-open, scheduled or live mocks match this offer
              type.
            </p>
          ) : (
            selectableMocks.map((mock) => {
              const checked = form.mock_ids.includes(mock.id);
              return (
                <label key={mock.id}>
                  <input
                    checked={checked}
                    disabled={
                      !checked && form.mock_ids.length >= expectedMockCount
                    }
                    onChange={() =>
                      setValue(
                        "mock_ids",
                        checked
                          ? form.mock_ids.filter((id) => id !== mock.id)
                          : [...form.mock_ids, mock.id],
                      )
                    }
                    type="checkbox"
                  />
                  <span>
                    <strong>{mock.title}</strong>
                    <small>
                      {mock.exam_type.name} · {mock.status.replaceAll("_", " ")}
                    </small>
                  </span>
                </label>
              );
            })
          )}
        </fieldset>

        <button className="primary-button" disabled={busy} type="submit">
          {busy ? "Saving…" : editing ? "Save offer" : "Create offer"}
        </button>
      </form>

      <section className="owner-data-list" aria-label="Existing offers">
        {offers.length ? (
          offers.map((offer) => (
            <article className="owner-data-card" key={offer.id}>
              <div className="owner-operation-panel__heading">
                <div>
                  <p className="eyebrow">{offerLabels[offer.offer_type]}</p>
                  <h3>{offer.name}</h3>
                </div>
                <span
                  className={
                    offer.active
                      ? "owner-rules-badge owner-rules-badge--verified"
                      : "owner-rules-badge"
                  }
                >
                  {offer.active ? "Active" : "Inactive"}
                </span>
              </div>
              <dl>
                <div>
                  <dt>Price</dt>
                  <dd>{price(offer.price_paise)}</dd>
                </div>
                <div>
                  <dt>Purchases</dt>
                  <dd>{offer.purchase_count}</dd>
                </div>
                <div>
                  <dt>Mocks</dt>
                  <dd>{offer.mocks.map((mock) => mock.title).join(" + ")}</dd>
                </div>
                <div>
                  <dt>Sales window</dt>
                  <dd>
                    {new Date(offer.sales_start_at).toLocaleString("en-IN", {
                      timeZone: "Asia/Kolkata",
                    })}
                    {" → "}
                    {new Date(offer.sales_end_at).toLocaleString("en-IN", {
                      timeZone: "Asia/Kolkata",
                    })}
                  </dd>
                </div>
              </dl>
              <div className="owner-offer-actions">
                <button
                  className={offer.active ? "danger-button" : "primary-button"}
                  disabled={busy}
                  onClick={() => void toggle(offer)}
                  type="button"
                >
                  {offer.active ? "Deactivate" : "Activate"}
                </button>
                <button
                  className="secondary-button"
                  disabled={busy || offer.active}
                  onClick={() => {
                    setEditing(offer);
                    setForm(formFromOffer(offer));
                    setMessage("");
                    window.scrollTo({ top: 0, behavior: "smooth" });
                  }}
                  type="button"
                >
                  Edit
                </button>
              </div>
            </article>
          ))
        ) : (
          <div className="owner-mocks-state">
            <h3>No offers yet</h3>
            <p>Create the first offer above.</p>
          </div>
        )}
      </section>
    </section>
  );
}
