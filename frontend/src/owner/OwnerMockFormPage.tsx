import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ApiError } from "../api/errors";
import { useAuth } from "../auth/auth-context";
import {
  createOwnerMockApi,
  ownerMockDetailApi,
  ownerMockOptionsApi,
  updateOwnerMockApi,
  type OwnerMockDetail,
  type OwnerMockInput,
  type OwnerMockOptions,
} from "./api";
import { isoToIstDateTimeLocal, rupeesToPaise } from "./mockForm.utils";

type DateField = "starts_at" | "ends_at" | "result_release_at";
type FormValues = Omit<OwnerMockInput, "price_paise"> & {
  price_rupees: string;
};
type FieldErrors = Partial<Record<keyof FormValues, string>>;
type LoadState =
  | { status: "loading" }
  | { status: "ready"; options: OwnerMockOptions; mock: OwnerMockDetail | null }
  | { status: "error" };

const dateFields: DateField[] = ["starts_at", "ends_at", "result_release_at"];
const emptyValues: FormValues = {
  exam_type: "",
  exam_scheme: "",
  title: "",
  slug: "",
  description: "",
  starts_at: "",
  ends_at: "",
  result_release_at: "",
  price_rupees: "29.00",
  instructions_md: "",
};

function valuesFromMock(mock: OwnerMockDetail): FormValues {
  return {
    exam_type: mock.exam_type_id,
    exam_scheme: mock.exam_scheme_id,
    title: mock.title,
    slug: mock.slug,
    description: mock.description,
    starts_at: isoToIstDateTimeLocal(mock.starts_at),
    ends_at: isoToIstDateTimeLocal(mock.ends_at),
    result_release_at: isoToIstDateTimeLocal(mock.result_release_at),
    price_rupees: (mock.price_paise / 100).toFixed(2),
    instructions_md: mock.instructions_md,
  };
}

function errorText(value: unknown): string {
  if (Array.isArray(value)) return value.map(errorText).join(" ");
  if (typeof value === "string") return value;
  return "This value is invalid.";
}

function fieldErrorsFrom(error: ApiError): {
  fields: FieldErrors;
  message: string;
} {
  const details = error.details;
  if (!details || typeof details !== "object" || Array.isArray(details)) {
    return { fields: {}, message: error.message };
  }

  const fields: FieldErrors = {};
  let message = "";
  for (const [key, value] of Object.entries(details)) {
    if (key === "price_paise") {
      fields.price_rupees = errorText(value);
    } else if (key in emptyValues) {
      fields[key as keyof FormValues] = errorText(value);
    } else {
      message = [message, errorText(value)].filter(Boolean).join(" ");
    }
  }
  return {
    fields,
    message:
      message ||
      (Object.keys(fields).length
        ? "Review the highlighted fields."
        : error.message),
  };
}

export function OwnerMockFormPage() {
  const { mockId } = useParams();
  const isEditing = Boolean(mockId);
  const navigate = useNavigate();
  const { withAccess } = useAuth();
  const [retryKey, setRetryKey] = useState(0);
  const [loadState, setLoadState] = useState<LoadState>({ status: "loading" });
  const [values, setValues] = useState(emptyValues);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [requestError, setRequestError] = useState("");
  const [saving, setSaving] = useState(false);
  const originalTimes = useRef<
    Partial<Record<DateField, { iso: string; local: string }>>
  >({});

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const optionsRequest = ownerMockOptionsApi(withAccess, controller.signal);
    const mockRequest = mockId
      ? ownerMockDetailApi(withAccess, mockId, controller.signal)
      : Promise.resolve(null);
    void Promise.all([optionsRequest, mockRequest])
      .then(([options, mock]) => {
        if (!active) return;
        if (mock) {
          const nextValues = valuesFromMock(mock);
          originalTimes.current = Object.fromEntries(
            dateFields.map((field) => [
              field,
              { iso: mock[field], local: nextValues[field] },
            ]),
          );
          setValues(nextValues);
        } else {
          originalTimes.current = {};
          setValues(emptyValues);
        }
        setFieldErrors({});
        setRequestError("");
        setLoadState({ status: "ready", options, mock });
      })
      .catch(() => {
        if (active) setLoadState({ status: "error" });
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [mockId, retryKey, withAccess]);

  const setValue = <K extends keyof FormValues>(
    key: K,
    value: FormValues[K],
  ) => {
    setValues((current) => ({ ...current, [key]: value }));
    setFieldErrors((current) => ({ ...current, [key]: undefined }));
    setRequestError("");
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (loadState.status !== "ready") return;
    const pricePaise = rupeesToPaise(values.price_rupees);
    if (pricePaise === null) {
      setFieldErrors((current) => ({
        ...current,
        price_rupees: "Enter a positive amount with up to two decimal places.",
      }));
      return;
    }

    const timestamp = (field: DateField) => {
      const original = originalTimes.current[field];
      return original?.local === values[field] ? original.iso : values[field];
    };
    const input: OwnerMockInput = {
      exam_type: values.exam_type,
      exam_scheme: values.exam_scheme,
      title: values.title,
      slug: values.slug,
      description: values.description,
      starts_at: timestamp("starts_at"),
      ends_at: timestamp("ends_at"),
      result_release_at: timestamp("result_release_at"),
      price_paise: pricePaise,
      instructions_md: values.instructions_md,
    };

    setSaving(true);
    setFieldErrors({});
    setRequestError("");
    try {
      const saved = mockId
        ? await updateOwnerMockApi(withAccess, mockId, input)
        : await createOwnerMockApi(withAccess, input);
      navigate(`/owner/mocks/${saved.id}`);
    } catch (error) {
      if (error instanceof ApiError) {
        const parsed = fieldErrorsFrom(error);
        setFieldErrors(parsed.fields);
        setRequestError(parsed.message);
      } else {
        setRequestError(
          "The mock could not be saved. Check your connection and try again.",
        );
      }
    } finally {
      setSaving(false);
    }
  };

  if (loadState.status === "loading") {
    return (
      <section aria-busy="true" className="owner-mocks-state" role="status">
        Loading mock form…
      </section>
    );
  }
  if (loadState.status === "error") {
    return (
      <section
        className="owner-mocks-state owner-mocks-state--error"
        role="alert"
      >
        <p className="eyebrow">Connection issue</p>
        <h2>Mock form unavailable</h2>
        <p>
          We couldn&apos;t load the exam and scheme options. Please try again.
        </p>
        <button
          className="primary-button"
          onClick={() => {
            setLoadState({ status: "loading" });
            setRetryKey((key) => key + 1);
          }}
          type="button"
        >
          Try again
        </button>
      </section>
    );
  }

  const { options, mock } = loadState;
  if (isEditing && mock && mock.status !== "DRAFT") {
    return (
      <section className="owner-mocks-state" role="status">
        <h2>This mock can no longer be edited</h2>
        <p>Only DRAFT mocks can be changed from the owner dashboard.</p>
        <Link className="owner-back-link" to={`/owner/mocks/${mock.id}`}>
          Return to mock
        </Link>
      </section>
    );
  }

  const selectedScheme = options.exam_schemes.find(
    (scheme) => scheme.id === values.exam_scheme,
  );
  const hasSchemeMismatch = Boolean(
    selectedScheme && selectedScheme.exam_type_id !== values.exam_type,
  );

  return (
    <section className="owner-mock-form-page">
      <Link
        className="owner-back-link"
        to={mock ? `/owner/mocks/${mock.id}` : "/owner/mocks"}
      >
        ← {mock ? "Back to mock" : "All mocks"}
      </Link>
      <header className="owner-mocks-heading">
        <div>
          <p className="eyebrow">Draft authoring</p>
          <h2>{mock ? "Edit draft mock" : "Create mock"}</h2>
          <p>
            Only DRAFT details can be changed here. All schedule times use India
            Standard Time (IST).
          </p>
        </div>
      </header>

      {requestError && (
        <p className="owner-mock-form__error-summary" role="alert">
          {requestError}
        </p>
      )}

      <form className="owner-mock-form" onSubmit={handleSubmit}>
        <div className="owner-mock-form__grid">
          <label>
            <span>Exam type</span>
            <select
              aria-invalid={Boolean(fieldErrors.exam_type)}
              onChange={(event) => setValue("exam_type", event.target.value)}
              required
              value={values.exam_type}
            >
              <option value="">Choose an exam type</option>
              {options.exam_types.map((type) => (
                <option key={type.id} value={type.id}>
                  {type.name}
                  {type.active ? "" : " (inactive)"}
                </option>
              ))}
            </select>
            {fieldErrors.exam_type && (
              <small role="alert">{fieldErrors.exam_type}</small>
            )}
          </label>
          <label>
            <span>Exam scheme</span>
            <select
              aria-invalid={
                Boolean(fieldErrors.exam_scheme) || hasSchemeMismatch
              }
              onChange={(event) => setValue("exam_scheme", event.target.value)}
              required
              value={values.exam_scheme}
            >
              <option value="">Choose a scheme</option>
              {hasSchemeMismatch && selectedScheme && (
                <option disabled value={selectedScheme.id}>
                  {selectedScheme.name} · {selectedScheme.version} (different
                  exam type)
                </option>
              )}
              {options.exam_schemes
                .filter((scheme) => scheme.exam_type_id === values.exam_type)
                .map((scheme) => (
                  <option key={scheme.id} value={scheme.id}>
                    {scheme.name} · {scheme.version}
                    {scheme.active ? "" : " (inactive)"}
                  </option>
                ))}
            </select>
            {(fieldErrors.exam_scheme || hasSchemeMismatch) && (
              <small role="alert">
                {fieldErrors.exam_scheme ||
                  "Choose a scheme for the selected exam type."}
              </small>
            )}
          </label>
          <label>
            <span>Title</span>
            <input
              aria-invalid={Boolean(fieldErrors.title)}
              maxLength={200}
              onChange={(event) => setValue("title", event.target.value)}
              required
              value={values.title}
            />
            {fieldErrors.title && (
              <small role="alert">{fieldErrors.title}</small>
            )}
          </label>
          <label>
            <span>Slug</span>
            <input
              aria-label="Slug"
              aria-invalid={Boolean(fieldErrors.slug)}
              maxLength={220}
              onChange={(event) => setValue("slug", event.target.value)}
              required
              value={values.slug}
            />
            {fieldErrors.slug && <small role="alert">{fieldErrors.slug}</small>}
          </label>
          <label className="owner-mock-form__wide">
            <span>Description</span>
            <textarea
              aria-invalid={Boolean(fieldErrors.description)}
              onChange={(event) => setValue("description", event.target.value)}
              rows={4}
              value={values.description}
            />
            {fieldErrors.description && (
              <small role="alert">{fieldErrors.description}</small>
            )}
          </label>
          <label>
            <span>Start date and time (IST)</span>
            <input
              aria-invalid={Boolean(fieldErrors.starts_at)}
              onChange={(event) => setValue("starts_at", event.target.value)}
              required
              step="1"
              type="datetime-local"
              value={values.starts_at}
            />
            {fieldErrors.starts_at && (
              <small role="alert">{fieldErrors.starts_at}</small>
            )}
          </label>
          <label>
            <span>End date and time (IST)</span>
            <input
              aria-invalid={Boolean(fieldErrors.ends_at)}
              onChange={(event) => setValue("ends_at", event.target.value)}
              required
              step="1"
              type="datetime-local"
              value={values.ends_at}
            />
            {fieldErrors.ends_at && (
              <small role="alert">{fieldErrors.ends_at}</small>
            )}
          </label>
          <label>
            <span>Result release date and time (IST)</span>
            <input
              aria-invalid={Boolean(fieldErrors.result_release_at)}
              onChange={(event) =>
                setValue("result_release_at", event.target.value)
              }
              required
              step="1"
              type="datetime-local"
              value={values.result_release_at}
            />
            {fieldErrors.result_release_at && (
              <small role="alert">{fieldErrors.result_release_at}</small>
            )}
          </label>
          <label>
            <span>Price (INR)</span>
            <div className="owner-mock-form__price-input">
              <span aria-hidden="true">₹</span>
              <input
                aria-label="Price (INR)"
                aria-invalid={Boolean(fieldErrors.price_rupees)}
                inputMode="decimal"
                onChange={(event) =>
                  setValue("price_rupees", event.target.value)
                }
                required
                value={values.price_rupees}
              />
            </div>
            <small>Enter rupees, with up to two decimal places.</small>
            {fieldErrors.price_rupees && (
              <small role="alert">{fieldErrors.price_rupees}</small>
            )}
          </label>
          <label className="owner-mock-form__wide">
            <span>Instructions</span>
            <textarea
              aria-invalid={Boolean(fieldErrors.instructions_md)}
              onChange={(event) =>
                setValue("instructions_md", event.target.value)
              }
              rows={6}
              value={values.instructions_md}
            />
            {fieldErrors.instructions_md && (
              <small role="alert">{fieldErrors.instructions_md}</small>
            )}
          </label>
        </div>
        <footer className="owner-mock-form__actions">
          <Link
            className="owner-back-link"
            to={mock ? `/owner/mocks/${mock.id}` : "/owner/mocks"}
          >
            Cancel
          </Link>
          <button className="primary-button" disabled={saving} type="submit">
            {saving ? "Saving…" : mock ? "Save draft" : "Create draft"}
          </button>
        </footer>
      </form>
    </section>
  );
}
