import { useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { useAuth } from "../auth/auth-context";
import {
  commitOwnerQuestionImportApi,
  ownerQuestionDetailApi,
  ownerQuestionTemplateApi,
  ownerQuestionsApi,
  previewOwnerQuestionImportApi,
  type OwnerQuestionDetail,
  type OwnerQuestionImportPreview,
  type OwnerQuestionsResponse,
} from "./api";

type LoadState =
  | { status: "loading" }
  | { status: "success"; mockId: string; data: OwnerQuestionsResponse }
  | { status: "error"; mockId: string };
type PreviewState =
  | null
  | { status: "loading" }
  | { status: "success"; data: OwnerQuestionImportPreview }
  | { status: "error"; message: string };
type QuestionState =
  | { status: "loading" }
  | { status: "success"; question: OwnerQuestionDetail }
  | { status: "error" };

function errorMessage(error: unknown) {
  return error instanceof Error
    ? error.message
    : "The request could not be completed. Please try again.";
}

function questionTypeLabel(value: string) {
  return value === "MCQ_SINGLE" ? "Multiple choice" : "Numerical";
}

function downloadBlob(blob: Blob, fileName: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function OwnerMockQuestionsPage() {
  const { mockId = "" } = useParams();
  const { withAccess } = useAuth();
  const [retryKey, setRetryKey] = useState(0);
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewState, setPreviewState] = useState<PreviewState>(null);
  const [confirmImport, setConfirmImport] = useState(false);
  const [commitError, setCommitError] = useState("");
  const [importedCount, setImportedCount] = useState<number | null>(null);
  const [questionId, setQuestionId] = useState("");
  const [questionState, setQuestionState] = useState<QuestionState | null>(
    null,
  );
  const [templateBusy, setTemplateBusy] = useState<"csv" | "xlsx" | "">("");
  const [templateError, setTemplateError] = useState("");

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    void ownerQuestionsApi(withAccess, mockId, controller.signal)
      .then((data) => {
        if (active) setState({ status: "success", mockId, data });
      })
      .catch(() => {
        if (active) setState({ status: "error", mockId });
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [mockId, retryKey, withAccess]);

  useEffect(() => {
    if (!questionId) return;
    let active = true;
    const controller = new AbortController();
    void ownerQuestionDetailApi(
      withAccess,
      mockId,
      questionId,
      controller.signal,
    )
      .then((question) => {
        if (active) setQuestionState({ status: "success", question });
      })
      .catch(() => {
        if (active) setQuestionState({ status: "error" });
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [mockId, questionId, withAccess]);

  function retryLoad() {
    setState({ status: "loading" });
    setRetryKey((key) => key + 1);
  }

  function inspectQuestion(id: string) {
    setQuestionState({ status: "loading" });
    setQuestionId(id);
  }

  async function handlePreview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedFile) return;
    setConfirmImport(false);
    setCommitError("");
    setImportedCount(null);
    setPreviewState({ status: "loading" });
    try {
      const data = await previewOwnerQuestionImportApi(
        withAccess,
        mockId,
        selectedFile,
      );
      setPreviewState({ status: "success", data });
    } catch (error) {
      setPreviewState({ status: "error", message: errorMessage(error) });
    }
  }

  async function handleCommit() {
    if (previewState?.status !== "success" || !confirmImport) return;
    setCommitError("");
    setImportedCount(null);
    try {
      const result = await commitOwnerQuestionImportApi(
        withAccess,
        mockId,
        previewState.data.token,
      );
      setImportedCount(result.imported_count);
      setPreviewState(null);
      setConfirmImport(false);
      setSelectedFile(null);
      const input = document.getElementById(
        "owner-question-file",
      ) as HTMLInputElement | null;
      if (input) input.value = "";
      retryLoad();
    } catch (error) {
      setCommitError(errorMessage(error));
    }
  }

  async function handleTemplateDownload(fileFormat: "csv" | "xlsx") {
    setTemplateError("");
    setTemplateBusy(fileFormat);
    try {
      const blob = await ownerQuestionTemplateApi(withAccess, fileFormat);
      downloadBlob(blob, "question-import." + fileFormat);
    } catch (error) {
      setTemplateError(errorMessage(error));
    } finally {
      setTemplateBusy("");
    }
  }

  if (state.status === "loading" || state.mockId !== mockId) {
    return (
      <section
        aria-busy="true"
        aria-label="Loading questions"
        className="owner-mocks-state"
        role="status"
      >
        Loading questions...
      </section>
    );
  }

  if (state.status === "error") {
    return (
      <section
        className="owner-mocks-state owner-mocks-state--error"
        role="alert"
      >
        <p className="eyebrow">Connection issue</p>
        <h2>Questions unavailable</h2>
        <p>We couldn&apos;t load this mock&apos;s questions.</p>
        <button className="primary-button" onClick={retryLoad} type="button">
          Try again
        </button>
      </section>
    );
  }

  const { data } = state;
  const byRow = new Map<number | null, string[]>();
  if (previewState?.status === "success") {
    for (const error of previewState.data.errors) {
      byRow.set(error.row, [...(byRow.get(error.row) ?? []), error.message]);
    }
  }

  return (
    <section className="owner-questions-page">
      <Link className="owner-back-link" to={"/owner/mocks/" + mockId}>
        ← Mock details
      </Link>
      <header className="owner-mock-questions-heading">
        <div>
          <p className="eyebrow">Question operations</p>
          <h2>Questions</h2>
          <p>{data.mock.title}</p>
        </div>
        <div className="owner-question-count" aria-label="Question count">
          <strong>{data.mock.question_count.toLocaleString("en-IN")}</strong>
          <span>
            of {data.mock.expected_question_count.toLocaleString("en-IN")}{" "}
            questions
          </span>
        </div>
      </header>

      {data.mock.read_only && (
        <div className="owner-question-readonly" role="status">
          This mock is {data.mock.status}. Questions are available for
          inspection; imports are disabled outside DRAFT.
        </div>
      )}

      <section
        aria-labelledby="owner-question-groups-heading"
        className="owner-question-groups"
      >
        <div className="owner-mock-section-heading">
          <div>
            <p className="eyebrow">Paper breakdown</p>
            <h3 id="owner-question-groups-heading">By phase and subject</h3>
          </div>
        </div>
        {data.grouped_counts.length ? (
          <div className="owner-question-group-grid">
            {data.grouped_counts.map((group) => (
              <article
                className="owner-question-group"
                key={
                  group.phase_order +
                  "-" +
                  group.subject +
                  "-" +
                  group.question_type
                }
              >
                <p>
                  Phase {group.phase_order}: {group.phase_name}
                </p>
                <h4>{group.subject}</h4>
                <span>
                  {questionTypeLabel(group.question_type)} · {group.count}
                </span>
              </article>
            ))}
          </div>
        ) : (
          <p className="owner-question-empty">No questions have been added.</p>
        )}
      </section>

      <section
        aria-labelledby="owner-question-list-heading"
        className="owner-question-list-section"
      >
        <div className="owner-mock-section-heading">
          <div>
            <p className="eyebrow">Paper content</p>
            <h3 id="owner-question-list-heading">Question list</h3>
          </div>
          <span>{data.results.length} total</span>
        </div>
        {data.results.length ? (
          <div className="owner-question-table-wrap">
            <table className="owner-question-table">
              <thead>
                <tr>
                  <th scope="col">No.</th>
                  <th scope="col">Phase / subject</th>
                  <th scope="col">Type</th>
                  <th scope="col">Question preview</th>
                  <th scope="col">Readiness</th>
                  <th scope="col">Inspect</th>
                </tr>
              </thead>
              <tbody>
                {data.results.map((question) => (
                  <tr key={question.id}>
                    <th scope="row">{question.question_number}</th>
                    <td>
                      Phase {question.phase_order} · {question.subject}
                    </td>
                    <td>{questionTypeLabel(question.question_type)}</td>
                    <td>
                      <span>{question.question_preview}</span>
                      {question.has_image && (
                        <small className="owner-question-image-note">
                          Image attached
                        </small>
                      )}
                    </td>
                    <td>
                      <span
                        className={
                          "owner-question-status owner-question-status--" +
                          question.status.toLowerCase()
                        }
                      >
                        {question.status_label}
                      </span>
                    </td>
                    <td>
                      <button
                        className="owner-view-link"
                        onClick={() => inspectQuestion(question.id)}
                        type="button"
                      >
                        Inspect
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="owner-question-empty owner-question-empty--large">
            <h4>No questions yet</h4>
            <p>
              Import the existing CSV or XLSX template to add paper content.
            </p>
          </div>
        )}
      </section>

      <section
        aria-labelledby="owner-question-import-heading"
        className="owner-question-import"
      >
        <div className="owner-mock-section-heading">
          <div>
            <p className="eyebrow">Bulk import</p>
            <h3 id="owner-question-import-heading">Import questions</h3>
          </div>
        </div>
        {data.mock.read_only ? (
          <p className="owner-question-readonly">
            Import is available only while the mock is in DRAFT status.
          </p>
        ) : (
          <>
            <p className="owner-question-import__help">
              Use the current GrowthSathi question template. CSV and XLSX files
              are supported, up to 2 MiB and 1,000 rows.
            </p>
            <div className="owner-question-template-actions">
              <button
                className="secondary-button"
                disabled={Boolean(templateBusy)}
                onClick={() => void handleTemplateDownload("csv")}
                type="button"
              >
                {templateBusy === "csv"
                  ? "Preparing CSV..."
                  : "Download CSV template"}
              </button>
              <button
                className="secondary-button"
                disabled={Boolean(templateBusy)}
                onClick={() => void handleTemplateDownload("xlsx")}
                type="button"
              >
                {templateBusy === "xlsx"
                  ? "Preparing XLSX..."
                  : "Download XLSX template"}
              </button>
            </div>
            {templateError && <p role="alert">{templateError}</p>}
            <form className="owner-question-upload" onSubmit={handlePreview}>
              <label htmlFor="owner-question-file">Question file</label>
              <input
                accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                id="owner-question-file"
                onChange={(event) => {
                  setSelectedFile(event.currentTarget.files?.[0] ?? null);
                  setPreviewState(null);
                  setConfirmImport(false);
                  setCommitError("");
                  setImportedCount(null);
                }}
                type="file"
              />
              <button
                className="primary-button"
                disabled={!selectedFile || previewState?.status === "loading"}
                type="submit"
              >
                {previewState?.status === "loading"
                  ? "Checking file..."
                  : "Preview import"}
              </button>
            </form>
            {previewState?.status === "error" && (
              <div className="owner-question-import-error" role="alert">
                <p>{previewState.message}</p>
                <button
                  className="secondary-button"
                  disabled={!selectedFile}
                  onClick={(event) =>
                    event.currentTarget
                      .closest("section")
                      ?.querySelector("form")
                      ?.requestSubmit()
                  }
                  type="button"
                >
                  Retry preview
                </button>
              </div>
            )}
            {previewState?.status === "success" && (
              <section
                aria-labelledby="owner-question-preview-heading"
                className="owner-question-preview"
              >
                <div className="owner-mock-section-heading">
                  <div>
                    <p className="eyebrow">No database changes yet</p>
                    <h4 id="owner-question-preview-heading">Import preview</h4>
                  </div>
                  <span>
                    {previewState.data.rows.length}{" "}
                    {previewState.data.rows.length === 1 ? "row" : "rows"}
                  </span>
                </div>
                {previewState.data.errors.length > 0 && (
                  <div className="owner-question-validation owner-question-validation--errors">
                    <h5>Validation errors</h5>
                    <ul>
                      {Array.from(byRow.entries()).map(([row, errors]) => (
                        <li key={row ?? "file"}>
                          <strong>
                            {row === null ? "File" : "Row " + row}:
                          </strong>{" "}
                          {errors.join("; ")}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {previewState.data.warnings.length > 0 && (
                  <div className="owner-question-validation owner-question-validation--warnings">
                    <h5>Warnings</h5>
                    <ul>
                      {previewState.data.warnings.map((warning) => (
                        <li key={warning}>{warning}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {previewState.data.rows.length > 0 && (
                  <div className="owner-question-table-wrap">
                    <table className="owner-question-table owner-question-table--preview">
                      <thead>
                        <tr>
                          <th scope="col">File row</th>
                          <th scope="col">Question no.</th>
                          <th scope="col">Phase</th>
                          <th scope="col">Subject</th>
                          <th scope="col">Type</th>
                          <th scope="col">Preview</th>
                          <th scope="col">Validation</th>
                        </tr>
                      </thead>
                      <tbody>
                        {previewState.data.rows.map((row) => (
                          <tr key={row.row}>
                            <th scope="row">{row.row}</th>
                            <td>{row.question_number || "—"}</td>
                            <td>{row.phase || "—"}</td>
                            <td>{row.subject || "—"}</td>
                            <td>{row.question_type || "—"}</td>
                            <td>{row.question_preview || "—"}</td>
                            <td>
                              {(byRow.get(row.row)?.length ?? 0) === 0
                                ? "Valid"
                                : byRow.get(row.row)?.join("; ")}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                {previewState.data.valid && (
                  <div className="owner-question-confirm">
                    <label>
                      <input
                        checked={confirmImport}
                        onChange={(event) =>
                          setConfirmImport(event.target.checked)
                        }
                        type="checkbox"
                      />
                      I reviewed this preview and confirm the atomic import.
                    </label>
                    <button
                      className="primary-button"
                      disabled={!confirmImport}
                      onClick={() => void handleCommit()}
                      type="button"
                    >
                      Confirm import
                    </button>
                  </div>
                )}
              </section>
            )}
            {commitError && (
              <div className="owner-question-import-error" role="alert">
                <p>Import could not be confirmed: {commitError}</p>
                <button
                  className="secondary-button"
                  onClick={retryLoad}
                  type="button"
                >
                  Reload questions
                </button>
              </div>
            )}
            {importedCount !== null && (
              <p className="owner-question-import-success" role="status">
                Imported {importedCount}{" "}
                {importedCount === 1 ? "question" : "questions"}.
              </p>
            )}
          </>
        )}
      </section>

      {questionId && (
        <div className="owner-question-inspect-backdrop">
          <section
            aria-labelledby="owner-question-inspect-heading"
            aria-modal="true"
            className="owner-question-inspect"
            role="dialog"
          >
            <div className="owner-mock-section-heading">
              <div>
                <p className="eyebrow">Question inspection</p>
                <h3 id="owner-question-inspect-heading">
                  {questionState?.status === "success"
                    ? "Question " + questionState.question.question_number
                    : "Question details"}
                </h3>
              </div>
              <button
                aria-label="Close question inspection"
                className="owner-question-close"
                onClick={() => {
                  setQuestionId("");
                  setQuestionState(null);
                }}
                type="button"
              >
                ×
              </button>
            </div>
            {questionState?.status === "loading" && (
              <p role="status">Loading question...</p>
            )}
            {questionState?.status === "error" && (
              <p role="alert">Question details are unavailable.</p>
            )}
            {questionState?.status === "success" && (
              <div className="owner-question-inspect__body">
                <p>
                  Phase {questionState.question.phase_order} ·{" "}
                  {questionState.question.subject} ·{" "}
                  {questionTypeLabel(questionState.question.question_type)} ·{" "}
                  {questionState.question.status_label}
                </p>
                <div className="owner-question-text">
                  {questionState.question.question_text_md}
                </div>
                {questionState.question.has_image && (
                  <p className="owner-question-image-note">
                    This question includes an external image reference.
                  </p>
                )}
                {questionState.question.options.length > 0 && (
                  <ol className="owner-question-options" type="A">
                    {questionState.question.options.map((option) => (
                      <li key={option.label}>
                        {option.text || "Image option"}
                        {option.has_image && (
                          <small className="owner-question-image-note">
                            Image attached
                          </small>
                        )}
                      </li>
                    ))}
                  </ol>
                )}
                <p className="owner-question-answer-note">
                  Answer keys are omitted from question inspection.
                </p>
              </div>
            )}
          </section>
        </div>
      )}
    </section>
  );
}
