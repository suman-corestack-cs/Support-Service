import { useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { MODULES, CLOUDS } from "../scriptsData";
import { submitAddScript } from "../api";
import SearchableSelect from "./SearchableSelect";

const BUNDLE_OPTIONS = MODULES.map((m) => ({ value: m.key, label: m.label }));
const CLOUD_OPTIONS = CLOUDS.map((c) => ({ value: c, label: c }));

// EDIT ME: shown as a blue "Note:" callout on the wizard's "Upload Script"
// step. Change this string to whatever you want people to know before
// uploading a script — prerequisites, required roles, portal steps, anything
// outside CoreStack the script depends on, how the script should be written
// so Claude can read it cleanly, etc.
const UPLOAD_SCRIPT_NOTE ="Declare all input values as blank placeholders at the top of the script. Do not create input fields elsewhere in the script or hardcode input values inline. Keep all non-input values and fixed configurations unchanged."


// Extensions accepted for the output-sample upload — kept in sync with
// Backend/app/add_script/routes.py's _ALLOWED_OUTPUT_EXTENSIONS. Listed as
// both extensions and MIME types since some browsers/OS file pickers filter
// on one or the other depending on how the file's type was set on save.
const OUTPUT_FILE_EXTENSIONS = [".pdf", ".xlsx", ".xls", ".xlsm", ".csv", ".tsv", ".txt"];
const OUTPUT_FILE_ACCEPT = [
  ...OUTPUT_FILE_EXTENSIONS,
  "application/pdf",
  "application/vnd.ms-excel",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/vnd.ms-excel.sheet.macroEnabled.12",
  "text/csv",
  "text/tab-separated-values",
  "text/plain",
].join(",");

const STEPS = [
  { key: "basic", title: "Script Name & Bundle" },
  { key: "cloud", title: "Cloud" },
  { key: "script", title: "Upload Script" },
  { key: "output", title: "Upload Output Sample" },
  { key: "description", title: "Description" },
];

function FileList({ files, onRemove }) {
  if (files.length === 0) return null;
  return (
    <div className="add-script-file-list">
      {files.map((file, i) => (
        <span className="badge add-script-file-chip" key={`${file.name}-${i}`}>
          {file.name}
          <button type="button" className="add-script-file-remove" onClick={() => onRemove(i)} title="Remove">
            ✕
          </button>
        </span>
      ))}
    </div>
  );
}

export default function AddScriptWizard({ onClose }) {
  const [stepIndex, setStepIndex] = useState(0);
  const [scriptName, setScriptName] = useState("");
  const [bundle, setBundle] = useState("");
  const [cloud, setCloud] = useState("");
  const [scriptFiles, setScriptFiles] = useState([]);
  const [outputFiles, setOutputFiles] = useState([]);
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null); // { ok: true, data } | { ok: false, error }

  const activeSteps = useMemo(
    () => (bundle === "settings" ? STEPS.filter((s) => s.key !== "cloud") : STEPS),
    [bundle]
  );
  const step = activeSteps[stepIndex] ?? activeSteps[activeSteps.length - 1];

  function stepValid(key) {
    if (key === "basic") return scriptName.trim().length > 0 && bundle.length > 0;
    if (key === "cloud") return cloud.length > 0;
    if (key === "script") return scriptFiles.length > 0;
    return true; // output sample and description are both optional
  }

  const canGoNext = stepValid(step.key);

  function goNext() {
    if (!canGoNext) return;
    setStepIndex((i) => Math.min(i + 1, activeSteps.length - 1));
  }

  function goPrevious() {
    setStepIndex((i) => Math.max(i - 1, 0));
  }

  function addScriptFiles(fileList) {
    const incoming = Array.from(fileList).filter((f) => f.name.toLowerCase().endsWith(".py"));
    setScriptFiles((prev) => [...prev, ...incoming]);
  }

  function addOutputFiles(fileList) {
    const incoming = Array.from(fileList).filter((f) =>
      OUTPUT_FILE_EXTENSIONS.some((ext) => f.name.toLowerCase().endsWith(ext))
    );
    setOutputFiles((prev) => [...prev, ...incoming]);
  }

  async function handleFinish() {
    setSubmitting(true);
    setResult(null);
    try {
      const data = await submitAddScript({
        scriptName: scriptName.trim(),
        bundle,
        cloud: bundle === "settings" ? "" : cloud,
        description,
        scriptFiles,
        outputFiles,
      });
      setResult({ ok: true, data });
    } catch (err) {
      setResult({ ok: false, error: err.message || "Something went wrong." });
    } finally {
      setSubmitting(false);
    }
  }

  const isLastStep = stepIndex === activeSteps.length - 1;

  return createPortal(
    <div className="source-modal-overlay" onClick={submitting ? undefined : onClose}>
      <div className="add-script-modal" onClick={(e) => e.stopPropagation()}>
        <div className="source-modal-header">
          <div>
            <h3>Add Script</h3>
            <span className="script-card-mono">Analyze a script and wire it into the console</span>
          </div>
          {!submitting && (
            <button type="button" className="icon-button" onClick={onClose} title="Close">
              ✕
            </button>
          )}
        </div>

        {!result && (
          <div className="add-script-stepper">
            {activeSteps.map((s, i) => (
              <div className="add-script-stepper-item" key={s.key}>
                <div className="add-script-step-row">
                  <div
                    className={`add-script-step-circle ${i < stepIndex ? "done" : ""} ${i === stepIndex ? "active" : ""}`}
                  >
                    {i < stepIndex ? "✓" : i + 1}
                  </div>
                  {i < activeSteps.length - 1 && <div className={`add-script-step-line ${i < stepIndex ? "done" : ""}`} />}
                </div>
                <div className="add-script-step-label">{s.title}</div>
              </div>
            ))}
          </div>
        )}

        <div className="add-script-body" data-select-boundary>
          {result ? (
            result.ok ? (
              <div className="add-script-result add-script-result-success">
                <div className="add-script-result-icon">✓</div>
                <h4>Script added</h4>
                <p>{result.data.summary}</p>
                <div className="add-script-result-meta">
                  <div>
                    <strong>Script ID:</strong> {result.data.script_id}
                  </div>
                  <div>
                    <strong>Endpoint:</strong> {result.data.endpoint}
                  </div>
                </div>
                <p className="form-field-hint">
                  Restart both the backend (to load the new route) and the frontend (to pick up the new script
                  card) before using this script — it won't show up or run until both have restarted.
                </p>
              </div>
            ) : (
              <div className="add-script-result add-script-result-error">
                <div className="add-script-result-icon">✕</div>
                <h4>Couldn't add this script</h4>
                <p>{result.error}</p>
              </div>
            )
          ) : submitting ? (
            <div className="add-script-result">
              <div className="progress-box progress-running">
                <div className="progress-track">
                  <div className="progress-fill progress-indeterminate" />
                </div>
                <div className="progress-label">Analyzing script with Claude, this can take a minute…</div>
              </div>
            </div>
          ) : (
            <>
              {step.key === "basic" && (
                <>
                  <div className="form-field">
                    <label>
                      <span className="form-field-label-text">
                        Script Name<span className="required-mark">*</span>
                      </span>
                    </label>
                    <input
                      type="text"
                      value={scriptName}
                      onChange={(e) => setScriptName(e.target.value)}
                      placeholder="e.g. Bulk Disable Billing"
                      autoFocus
                    />
                  </div>
                  <div className="form-field">
                    <label>
                      <span className="form-field-label-text">
                        Bundle<span className="required-mark">*</span>
                      </span>
                    </label>
                    <SearchableSelect
                      label="bundle"
                      options={BUNDLE_OPTIONS}
                      value={bundle}
                      onChange={(value) => {
                        setBundle(value);
                        if (value === "settings") setCloud("");
                      }}
                      compact
                    />
                  </div>
                </>
              )}

              {step.key === "cloud" && (
                <div className="form-field">
                  <label>
                    <span className="form-field-label-text">
                      Cloud<span className="required-mark">*</span>
                    </span>
                  </label>
                  <SearchableSelect label="cloud" options={CLOUD_OPTIONS} value={cloud} onChange={setCloud} compact />
                </div>
              )}

              {step.key === "script" && (
                <div className="form-field">
                  <label>
                    <span className="form-field-label-text">
                      Script File(s)<span className="required-mark">*</span>
                    </span>
                  </label>
                  <div className="form-field-hint">Only .py files are accepted. At least one is required.</div>
                  <FileList files={scriptFiles} onRemove={(i) => setScriptFiles((prev) => prev.filter((_, j) => j !== i))} />
                  <label className="file-choose-button">
                    + {scriptFiles.length === 0 ? "Upload .py file" : "Add another .py file"}
                    <input
                      type="file"
                      accept=".py,text/x-python"
                      multiple
                      onChange={(e) => {
                        addScriptFiles(e.target.files);
                        e.target.value = "";
                      }}
                    />
                  </label>
                  <div className="note-callout">
                    <strong>Note:</strong> {UPLOAD_SCRIPT_NOTE}
                  </div>
                </div>
              )}

              {step.key === "output" && (
                <div className="form-field">
                  <label>
                    <span className="form-field-label-text">Output Sample (optional)</span>
                  </label>
                  <div className="form-field-hint">
                    Excel, text or PDF only — a real sample of what the script produces helps Claude shape the
                    result correctly, but isn't required.
                  </div>
                  <FileList files={outputFiles} onRemove={(i) => setOutputFiles((prev) => prev.filter((_, j) => j !== i))} />
                  <label className="file-choose-button">
                    + {outputFiles.length === 0 ? "Upload output sample" : "Add another output sample"}
                    <input
                      type="file"
                      accept={OUTPUT_FILE_ACCEPT}
                      multiple
                      onChange={(e) => {
                        addOutputFiles(e.target.files);
                        e.target.value = "";
                      }}
                    />
                  </label>
                </div>
              )}

              {step.key === "description" && (
                <div className="form-field">
                  <label>
                    <span className="form-field-label-text">Description &amp; Output View Suggestions</span>
                  </label>
                  <div className="form-field-hint">
                    Describe what the script does, and suggest how its output should be displayed — e.g. which
                    columns/fields matter most, whether it reads better as a table, a grouped summary, or a simple
                    list. Claude uses this as guidance when shaping the result the script returns and how it's
                    presented.
                  </div>
                  <textarea
                    rows={7}
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="e.g. This lists every S3 bucket with its size and last-modified date — show it as a table sorted by size, largest first."
                  />
                </div>
              )}
            </>
          )}
        </div>

        <div className="add-script-footer">
          <button type="button" className="link-button" onClick={onClose}>
            Cancel
          </button>
          {!result && !submitting && (
            <div className="add-script-footer-nav">
              <button type="button" className="secondary-button" onClick={goPrevious} disabled={stepIndex === 0}>
                Previous
              </button>
              {isLastStep ? (
                <button type="button" className="run-button" onClick={handleFinish} disabled={!canGoNext}>
                  Add Script
                </button>
              ) : (
                <button type="button" className="run-button" onClick={goNext} disabled={!canGoNext}>
                  Next
                </button>
              )}
            </div>
          )}
          {result && (
            <div className="add-script-footer-nav">
              <button type="button" className="run-button" onClick={onClose}>
                Close
              </button>
            </div>
          )}
        </div>
      </div>
    </div>,
    document.body
  );
}
