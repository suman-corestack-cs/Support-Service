import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import AccordionSection from "../components/AccordionSection";
import CompanionPanel from "../components/CompanionPanel";
import DeleteScriptModal from "../components/DeleteScriptModal";
import InfoTooltip from "../components/InfoTooltip";
import MultiSelectDropdown from "../components/MultiSelectDropdown";
import ProgressBar from "../components/ProgressBar";
import ResultView from "../components/ResultView";
import SearchableSelect from "../components/SearchableSelect";
import { absoluteUrl, getJobStatus, pollJobUntilDone, runScriptWithProgress, startJob } from "../api";
import { useDynamicSelectOptions } from "../hooks/useDynamicSelectOptions";
import { SCRIPTS } from "../scriptsData";

const PHASE_LABEL = {
  idle: "Not run yet",
  running: "Running…",
  completed: "Completed",
  failed: "Failed",
};

const SELECT_TYPES = ["select", "dynamic-select", "async-select", "multi-select"];

function todayDateString() {
  return new Date().toISOString().slice(0, 10);
}

function jobStorageKey(scriptId) {
  return `job:${scriptId}`;
}

function initialValuesFor(script) {
  const initial = {};
  for (const input of script?.inputs ?? []) {
    if (input.default !== undefined) initial[input.name] = input.default;
  }
  return initial;
}

function isRequired(input, values) {
  return typeof input.required === "function" ? input.required(values) : !!input.required;
}

function isDisabled(input, values) {
  return typeof input.disabledWhen === "function" && input.disabledWhen(values);
}

function isVisible(input, values) {
  return typeof input.showWhen !== "function" || input.showWhen(values);
}

// Groups consecutive visible inputs where the first has `groupWithNext` (e.g.
// the upload-mode toggle rendered inline beside whichever of Excel File /
// Tenant Names is currently showing) into one row; everything else is its
// own single-field row.
function buildFieldRows(visibleInputs) {
  const rows = [];
  for (let i = 0; i < visibleInputs.length; i++) {
    const input = visibleInputs[i];
    if (input.groupWithNext && visibleInputs[i + 1]) {
      rows.push([input, visibleInputs[i + 1]]);
      i++;
    } else {
      rows.push([input]);
    }
  }
  return rows;
}

export default function ScriptPage() {
  const { id } = useParams();
  const script = SCRIPTS.find((s) => s.id === id);
  const isJobMode = script?.resultMode === "job";

  const [values, setValues] = useState(() => initialValuesFor(script));
  const [phase, setPhase] = useState("idle"); // idle | running | completed | failed
  const [job, setJob] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [startedAt, setStartedAt] = useState(null);

  const [inputOpen, setInputOpen] = useState(true);
  const [outputOpen, setOutputOpen] = useState(false);
  const [companionPanelOpen, setCompanionPanelOpen] = useState(false);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [deleteResult, setDeleteResult] = useState(null);

  // Options for "async-select" inputs (e.g. API URL, loaded once and then
  // auto-selected to match another field), keyed by input name:
  // { loading, error, options: [{value, label, matchValue}, ...] }.
  const [asyncOptions, setAsyncOptions] = useState({});

  async function watchJob(jobId, { isResume = false } = {}) {
    setPhase("running");
    setOutputOpen(true);
    setJob({ status: "running", processed: 0, total: null });

    try {
      const finalResult = await pollJobUntilDone(script, jobId, (jobUpdate) => setJob(jobUpdate));
      setResult(finalResult);
      setPhase("completed");
    } catch (err) {
      if (isResume) {
        // Stale/evicted job reference (e.g. server restarted since) — fall back to idle quietly.
        sessionStorage.removeItem(jobStorageKey(script.id));
        setPhase("idle");
        setJob(null);
        return;
      }
      setError(err.message);
      setPhase("failed");
    }
  }

  // Reconnect to an in-progress or already-finished job after a page refresh —
  // the fetch itself kept running server-side the whole time regardless.
  useEffect(() => {
    if (!isJobMode) return;
    const savedJobId = sessionStorage.getItem(jobStorageKey(script.id));
    if (!savedJobId) return;
    setStartedAt(performance.now());
    watchJob(savedJobId, { isResume: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // Options for "dynamic-select" inputs (e.g. Master Account, whose list
  // comes from a live Mongo lookup once its dependency — Environment — is
  // picked), keyed by input name: { loading, error, options: [{value,label}] }.
  const dynamicOptions = useDynamicSelectOptions(script?.inputs ?? [], values, setValues);

  // Load "async-select" options once when the script page mounts (they don't
  // depend on any other field — e.g. the full list of per-region API URLs).
  useEffect(() => {
    const asyncInputs = (script?.inputs ?? []).filter((input) => input.type === "async-select");
    for (const input of asyncInputs) {
      setAsyncOptions((prev) => ({ ...prev, [input.name]: { loading: true, error: null, options: [] } }));
      input
        .loadOptions()
        .then((options) => setAsyncOptions((prev) => ({ ...prev, [input.name]: { loading: false, error: null, options } })))
        .catch((err) => setAsyncOptions((prev) => ({ ...prev, [input.name]: { loading: false, error: err.message, options: [] } })));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // Auto-select an "async-select" field's value to match another field (API
  // URL picks the option for the chosen Environment) whenever that driving
  // field changes, or once this field's options finish loading.
  const autoSelectKey = (script?.inputs ?? [])
    .filter((input) => input.type === "async-select" && input.autoSelectFrom)
    .map((input) => `${input.name}:${values[input.autoSelectFrom] ?? ""}:${asyncOptions[input.name]?.options?.length ?? 0}`)
    .join("|");

  useEffect(() => {
    const autoSelectInputs = (script?.inputs ?? []).filter((input) => input.type === "async-select" && input.autoSelectFrom);
    for (const input of autoSelectInputs) {
      const drivingValue = values[input.autoSelectFrom];
      const options = asyncOptions[input.name]?.options ?? [];
      const match = options.find((opt) => opt.matchValue === drivingValue);
      if (match && values[input.name] !== match.value) {
        setValues((prev) => ({ ...prev, [input.name]: match.value }));
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoSelectKey]);

  if (!script) {
    return (
      <div className="script-page">
        <Link to="/" className="back-link">
          ← Back to All Scripts
        </Link>
        <div className="empty-state">Script not found.</div>
      </div>
    );
  }

  if (deleteResult) {
    return (
      <div className="script-page">
        <Link to="/" className="back-link">
          ← Back to All Scripts
        </Link>
        <div className="script-page-header">
          <div className="add-script-result add-script-result-success">
            <div className="add-script-result-icon">✓</div>
            <h4>Script deleted</h4>
            <p>{deleteResult.title || script.title} has been removed from this console.</p>
            <p className="form-field-hint">
              Restart both the backend (to drop its route) and the frontend (to drop its card) for this to fully
              take effect.
            </p>
          </div>
        </div>
      </div>
    );
  }

  function updateValue(name, value) {
    setValues((prev) => ({ ...prev, [name]: value }));
  }

  // Fills the given field values into this script's own form (e.g. the
  // Access Key/Secret Key/Session Token — and Region, if the companion
  // panel resolved one — from a freshly-generated companion result), then
  // closes the panel. Multi-select values are filtered down to whatever the
  // matching input's own options actually contain, so a region the account
  // reports that isn't one of this form's known options doesn't end up as
  // an invisible, unremovable selection.
  function handleCompanionApply(applied) {
    setValues((prev) => {
      const next = { ...prev };
      for (const [name, value] of Object.entries(applied)) {
        if (value === undefined) continue;
        const input = script.inputs.find((i) => i.name === name);
        if (!input) continue;
        if (Array.isArray(value) && input.options) {
          const validValues = new Set(input.options.map((opt) => opt.value));
          const filtered = value.filter((v) => validValues.has(v));
          if (filtered.length > 0) next[name] = filtered;
        } else {
          next[name] = value;
        }
      }
      return next;
    });
    setCompanionPanelOpen(false);
  }

  function expandAll() {
    setInputOpen(true);
    setOutputOpen(true);
  }

  function collapseAll() {
    setInputOpen(false);
    setOutputOpen(false);
  }

  function handleClear() {
    setValues(initialValuesFor(script));
    setPhase("idle");
    setJob(null);
    setResult(null);
    setError(null);
  }

  // The custom dropdowns (select/dynamic-select/async-select) aren't native
  // form controls, so the browser's own `required` validation never sees
  // them — check those specifically before submitting.
  function findMissingCustomSelects() {
    return script.inputs
      .filter((input) => isVisible(input, values) && SELECT_TYPES.includes(input.type))
      .filter((input) => {
        if (!isRequired(input, values)) return false;
        const value = values[input.name];
        return Array.isArray(value) ? value.length === 0 : !value;
      })
      .map((input) => input.label);
  }

  async function handleSubmit(e) {
    e.preventDefault();

    const missing = findMissingCustomSelects();
    if (missing.length > 0) {
      setResult(null);
      setError(`Please select: ${missing.join(", ")}`);
      setPhase("failed");
      setOutputOpen(true);
      return;
    }

    setResult(null);
    setError(null);
    setStartedAt(performance.now());

    if (isJobMode) {
      setPhase("running");
      setOutputOpen(true);
      try {
        const jobId = await startJob(script, values);
        sessionStorage.setItem(jobStorageKey(script.id), jobId);
        await watchJob(jobId);
      } catch (err) {
        setError(err.message);
        setPhase("failed");
      }
      return;
    }

    setPhase("running");
    setJob({ status: "running", processed: 0, total: null });
    setOutputOpen(true); // progress needs to be visible as soon as the run starts

    try {
      const finalResult = await runScriptWithProgress(script, values, (event) => setJob(event));
      setResult(finalResult);
      setPhase("completed");
    } catch (err) {
      setError(err.message);
      setPhase("failed");
    }
  }

  const downloadUrl = result?.download_url ? absoluteUrl(result.download_url) : null;
  const displayResult = result ? { ...result } : result;
  if (displayResult) {
    delete displayResult.download_url;
    delete displayResult.preview_row_limit;
  }

  function renderFieldControl(input) {
    const required = isRequired(input, values);
    const disabled = isDisabled(input, values);

    if (input.type === "file") {
      const chosenFile = values[input.name];
      return (
        <label className={`file-choose-button ${disabled ? "disabled" : ""}`}>
          {chosenFile ? chosenFile.name : "Choose File"}
          <input
            type="file"
            required={required}
            disabled={disabled}
            onChange={(e) => updateValue(input.name, e.target.files[0])}
          />
        </label>
      );
    }

    if (input.type === "toggle") {
      return (
        <label className="toggle-switch">
          <input
            type="checkbox"
            checked={values[input.name] !== false}
            onChange={(e) => updateValue(input.name, e.target.checked)}
          />
          <span className="toggle-slider" />
          <span className="toggle-switch-label">{values[input.name] !== false ? input.onLabel ?? "On" : input.offLabel ?? "Off"}</span>
        </label>
      );
    }

    if (input.type === "select") {
      return (
        <SearchableSelect
          label={input.label}
          options={input.options}
          value={values[input.name] ?? ""}
          onChange={(v) => updateValue(input.name, v)}
          disabled={disabled}
          searchable={!!input.searchable}
        />
      );
    }

    if (input.type === "dynamic-select") {
      const dependencyValue = values[input.dependsOn];
      const state = dynamicOptions[input.name];
      return (
        <SearchableSelect
          label={input.label}
          options={state?.options ?? []}
          value={values[input.name] ?? ""}
          onChange={(v) => updateValue(input.name, v)}
          disabled={disabled || !dependencyValue}
          loading={state?.loading}
          searchable={!!input.searchable}
          placeholder={
            !dependencyValue
              ? `Select ${script.inputs.find((i) => i.name === input.dependsOn)?.label ?? "a value"} first`
              : undefined
          }
        />
      );
    }

    if (input.type === "async-select") {
      const state = asyncOptions[input.name];
      return (
        <SearchableSelect
          label={input.label}
          options={state?.options ?? []}
          value={values[input.name] ?? ""}
          onChange={(v) => updateValue(input.name, v)}
          disabled={disabled}
          loading={state?.loading}
          searchable={!!input.searchable}
        />
      );
    }

    if (input.type === "multi-select") {
      return (
        <MultiSelectDropdown
          label={input.label}
          options={input.options}
          value={values[input.name] ?? []}
          onChange={(v) => updateValue(input.name, v)}
          disabled={disabled}
        />
      );
    }

    if (input.type === "date") {
      return (
        <input
          type="date"
          required={required}
          disabled={disabled}
          max={input.maxToday ? todayDateString() : undefined}
          value={values[input.name] ?? ""}
          onChange={(e) => updateValue(input.name, e.target.value)}
        />
      );
    }

    return (
      <input
        type={input.type === "password" ? "password" : input.type === "number" ? "number" : "text"}
        step={input.type === "number" ? "any" : undefined}
        placeholder={input.type === "list" ? "comma,separated,values" : input.description}
        required={required}
        disabled={disabled}
        value={values[input.name] ?? ""}
        onChange={(e) => updateValue(input.name, e.target.value)}
      />
    );
  }

  function renderField(input) {
    const required = isRequired(input, values);
    const fieldError = input.type === "dynamic-select" ? dynamicOptions[input.name]?.error : input.type === "async-select" ? asyncOptions[input.name]?.error : null;

    return (
      <div className="form-field" key={input.name}>
        <label>
          <span className="form-field-label-text">
            {input.label}
            {required && <span className="required-mark"> *</span>}
          </span>
          <InfoTooltip text={input.description} />
        </label>
        {renderFieldControl(input)}
        {fieldError && <span className="form-field-hint form-field-error">Couldn't load options: {fieldError}</span>}
      </div>
    );
  }

  const visibleInputs = script.inputs.filter((input) => isVisible(input, values));
  const fieldRows = buildFieldRows(visibleInputs);

  return (
    <div className="script-page">
      <Link to="/" className="back-link">
        ← Back to All Scripts
      </Link>

      <div className="script-page-header">
        <div className="script-page-header-top">
          <h1>
            {script.title}
            <InfoTooltip text={script.description} />
          </h1>
          <div className="script-page-header-actions">
            <div className="accordion-controls">
              <button type="button" className="secondary-button" onClick={expandAll}>
                Expand All
              </button>
              <button type="button" className="secondary-button" onClick={collapseAll}>
                Collapse All
              </button>
              <button
                type="button"
                className="icon-button danger-icon-button"
                onClick={() => setDeleteModalOpen(true)}
                title="Delete script"
              >
                🗑
              </button>
            </div>
            {script.companionPanel && (
              <button
                type="button"
                className="companion-trigger-button"
                onClick={() => setCompanionPanelOpen(true)}
              >
                {script.companionPanel.buttonLabel}
              </button>
            )}
          </div>
        </div>
        <div className="script-page-meta">
          <span className="badge">{script.module}</span>
          {script.cloud && <span className="badge">{script.cloud}</span>}
          <span className="script-card-mono">
            {script.method} {script.endpoint}
          </span>
        </div>
      </div>

      <AccordionSection
        title="Input"
        subtitle={`${script.inputs.length} field${script.inputs.length === 1 ? "" : "s"}`}
        isOpen={inputOpen}
        onToggle={() => setInputOpen((v) => !v)}
      >
        <form className="script-page-form" onSubmit={handleSubmit}>
          {fieldRows.map((row) =>
            row.length === 1 ? (
              renderField(row[0])
            ) : (
              <div className="form-field-row" key={row.map((i) => i.name).join("+")}>
                <div className="form-field-row-toggle">{renderField(row[0])}</div>
                <div className="form-field-row-main">{renderField(row[1])}</div>
              </div>
            )
          )}

          <div className="script-page-form-actions">
            <button type="submit" className="run-button script-page-action-button" disabled={phase === "running"}>
              {phase === "running" ? "Running..." : "▶ Execute"}
            </button>
            <button
              type="button"
              className="secondary-button script-page-action-button"
              onClick={handleClear}
              disabled={phase === "running"}
            >
              Clear
            </button>
          </div>
        </form>
      </AccordionSection>

      <AccordionSection title="Output" subtitle={PHASE_LABEL[phase]} isOpen={outputOpen} onToggle={() => setOutputOpen((v) => !v)}>
        <div className="script-page-output">
          {phase === "idle" && <div className="empty-state">Fill in the inputs and run the script to see results here.</div>}

          {phase === "running" && job && (
            <ProgressBar status="running" processed={job.processed} total={job.total} startedAt={startedAt} />
          )}

          {phase === "failed" && (
            <div className="modal-result modal-result-error">
              <div className="modal-result-title">Error</div>
              <pre>{error}</pre>
            </div>
          )}

          {phase === "completed" && downloadUrl && (
            <div className="download-panel">
              <a href={downloadUrl} download className="run-button download-button">
                ⬇ Download Full File{result?.row_count != null ? ` (${result.row_count} rows)` : ""}
              </a>
              {result?.preview_row_limit != null && (
                <p className="download-panel-note">
                  Showing a preview of the first {result.preview_row_limit} of {result.row_count} rows below — the download
                  above has all of it. This link keeps working even if you refresh the page.
                </p>
              )}
            </div>
          )}

          {phase === "completed" && <ResultView result={displayResult} scriptTitle={script.title} />}
        </div>
      </AccordionSection>

      {companionPanelOpen && script.companionPanel && (
        <CompanionPanel
          script={script}
          onClose={() => setCompanionPanelOpen(false)}
          onApply={handleCompanionApply}
        />
      )}

      {deleteModalOpen && (
        <DeleteScriptModal
          script={script}
          onClose={() => setDeleteModalOpen(false)}
          onDeleted={(result) => {
            setDeleteModalOpen(false);
            setDeleteResult(result);
          }}
        />
      )}
    </div>
  );
}
