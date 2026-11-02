import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { API_BASE_URL, runJsonWithProgress } from "../api";
import { useDynamicSelectOptions } from "../hooks/useDynamicSelectOptions";
import InfoTooltip from "./InfoTooltip";
import SearchableSelect from "./SearchableSelect";

function initialValues(inputs) {
  const initial = {};
  for (const input of inputs) {
    if (input.default !== undefined) initial[input.name] = input.default;
  }
  return initial;
}

// Persists the last-generated result (e.g. temporary AWS credentials) across
// a panel close/reopen and a full page refresh, for as long as it's still
// valid — sessionStorage rather than localStorage, since these are sensitive
// short-lived credentials that shouldn't outlive the browser tab.
function companionStorageKey(scriptId) {
  return `companion:${scriptId}`;
}

function loadStoredResult(scriptId) {
  try {
    const raw = sessionStorage.getItem(companionStorageKey(scriptId));
    if (!raw) return null;
    const stored = JSON.parse(raw);
    if (!stored?.expiration || new Date(stored.expiration).getTime() <= Date.now()) {
      sessionStorage.removeItem(companionStorageKey(scriptId));
      return null;
    }
    return stored;
  } catch {
    return null;
  }
}

function saveStoredResult(scriptId, result) {
  try {
    sessionStorage.setItem(companionStorageKey(scriptId), JSON.stringify(result));
  } catch {
    // Storage full/unavailable — the result still shows for this session, it just won't survive a refresh.
  }
}

function clearStoredResult(scriptId) {
  try {
    sessionStorage.removeItem(companionStorageKey(scriptId));
  } catch {
    // Nothing to do if storage itself is unavailable.
  }
}

// A read-only value with a one-click "copy the whole thing" button —
// used for credentials the user needs to paste elsewhere in full.
function CopyField({ label, value }) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(value ?? "");
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard permission denied/unavailable — nothing more to do here.
    }
  }

  return (
    <div className="copy-field">
      <div className="copy-field-label">{label}</div>
      <div className="copy-field-row">
        <code className="copy-field-value">{value}</code>
        <button type="button" className="icon-button copy-field-button" onClick={handleCopy} title="Copy to clipboard">
          {copied ? "✓" : "⧉"}
        </button>
      </div>
    </div>
  );
}

// A read-only value with no copy action — for details that are only ever
// looked at, not pasted elsewhere (expiry, generation time, role identity).
function ViewField({ label, value }) {
  return (
    <div className="copy-field">
      <div className="copy-field-label">{label}</div>
      <div className="copy-field-value copy-field-value-plain" style={{ whiteSpace: "pre-line" }}>
        {value}
      </div>
    </div>
  );
}

// Fetches and shows the fixed, server-side credentials this action uses
// (e.g. the STS caller's own access key) on demand — never editable, so the
// operator can double check what's configured without typing it in every
// time. Collapsed until clicked; fetched once per panel open.
function FixedCredentialsViewer({ endpoint, label }) {
  const [open, setOpen] = useState(false);
  const [creds, setCreds] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  async function toggle() {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    if (creds || loading) return;

    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}${endpoint}`);
      if (!response.ok) throw new Error(`Could not load (status ${response.status})`);
      setCreds(await response.json());
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed-creds-viewer">
      <button type="button" className="secondary-button fixed-creds-toggle" onClick={toggle}>
        {label}
      </button>
      {open && (
        <div className="fixed-creds-popover">
          {loading && <div className="empty-state">Loading…</div>}
          {error && (
            <div className="modal-result modal-result-error">
              <pre>{error}</pre>
            </div>
          )}
          {creds && (
            <>
              <ViewField label="Access Key ID" value={creds.access_key_id || "—"} />
              <ViewField label="Secret Access Key" value={creds.secret_access_key || "—"} />
              <ViewField label="Region" value={creds.region_name || "—"} />
            </>
          )}
        </div>
      )}
    </div>
  );
}

// Renders a script-defined `companionPanel` (see scriptsData.js) as a slide-in
// side panel rather than its own page — for an action that's a natural
// follow-on to the script it's attached to (e.g. assuming an AWS role to get
// temporary credentials, or decrypting an Azure account's stored secret).
// Everything action-specific comes from the panel config: `sourceField` (the
// input whose selected option carries the data to send), `buildRequestBody`,
// `enrichResult`, `resultFields`, `applyValues`, and the button labels.
export default function CompanionPanel({ script, onClose, onApply }) {
  const panel = script.companionPanel;

  const [values, setValues] = useState(() => initialValues(panel.inputs));
  const [phase, setPhase] = useState(() => (loadStoredResult(script.id) ? "completed" : "idle")); // idle | running | completed | failed
  const [result, setResult] = useState(() => loadStoredResult(script.id));
  const [error, setError] = useState(null);

  const dynamicOptions = useDynamicSelectOptions(panel.inputs, values, setValues);

  function updateValue(name, value) {
    setValues((prev) => ({ ...prev, [name]: value }));
  }

  function reset() {
    clearStoredResult(script.id);
    setValues(initialValues(panel.inputs));
    setPhase("idle");
    setResult(null);
    setError(null);
  }

  // If the panel is left open past the shown credentials' expiration, flip
  // back to the generate form on its own rather than silently keeping stale
  // (now-rejected) credentials on screen.
  useEffect(() => {
    if (phase !== "completed" || !result?.expiration) return undefined;
    const msUntilExpiry = new Date(result.expiration).getTime() - Date.now();
    if (msUntilExpiry <= 0) {
      reset();
      return undefined;
    }
    const timer = setTimeout(reset, msUntilExpiry);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, result?.expiration]);

  function findMissingSelects() {
    return panel.inputs
      .filter((input) => ["select", "dynamic-select"].includes(input.type))
      .filter((input) => input.required && !values[input.name])
      .map((input) => input.label);
  }

  // Human-readable names of what was picked (e.g. "US", the master account's
  // name, the cloud account's name), captured at submit time so the result
  // always says which account it was generated for — even after the
  // dropdowns change or the page is refreshed.
  function buildContext() {
    return (panel.contextFields ?? [])
      .map(({ field, label }) => {
        const input = panel.inputs.find((i) => i.name === field);
        const options = input?.type === "dynamic-select" ? dynamicOptions[field]?.options ?? [] : input?.options ?? [];
        const match = options.find((opt) => opt.value === values[field]);
        return { label, value: match?.label ?? values[field] ?? "—" };
      });
  }

  async function handleSubmit(e) {
    e.preventDefault();

    const missing = findMissingSelects();
    if (missing.length > 0) {
      setResult(null);
      setError(`Please select: ${missing.join(", ")}`);
      setPhase("failed");
      return;
    }

    // The field named by `sourceField` (Cloud Account) is what actually
    // carries the data to send (role ARN, encrypted secret, ...) — via its
    // selected option, not as separate visible fields.
    const sourceOptions = dynamicOptions[panel.sourceField]?.options ?? [];
    const selected = sourceOptions.find((opt) => opt.value === values[panel.sourceField]);
    if (!selected) {
      setResult(null);
      setError(panel.sourceMissingMessage || "Could not find the selected option's details. Try reselecting it.");
      setPhase("failed");
      return;
    }

    const body = { ...(panel.buildRequestBody ? panel.buildRequestBody(selected) : {}) };
    for (const input of panel.inputs) {
      if (input.excludeFromSubmit) continue;
      const value = values[input.name];
      if (value !== undefined && value !== "") body[input.name] = value;
    }

    setResult(null);
    setError(null);
    setPhase("running");

    try {
      const finalResult = await runJsonWithProgress(panel.endpoint, body);
      if (finalResult && finalResult.error) {
        setError(finalResult.error);
        setPhase("failed");
        return;
      }
      const enrichedResult = {
        ...(panel.enrichResult ? panel.enrichResult(finalResult, selected) : finalResult),
        _context: buildContext(),
      };
      setResult(enrichedResult);
      setPhase("completed");
      // Only results with an expiry (temporary AWS keys) survive a refresh —
      // a decrypted permanent secret is never written to storage.
      if (finalResult?.expiration) saveStoredResult(script.id, enrichedResult);
    } catch (err) {
      setError(err.message);
      setPhase("failed");
    }
  }

  function handleApply() {
    onApply?.(panel.applyValues ? panel.applyValues(result) : {});
    onClose();
  }

  function renderResultField(field) {
    const raw = result[field.key];
    if (field.copy) return <CopyField key={field.key} label={field.label} value={raw ?? ""} />;
    const shown = field.format ? field.format(raw, result) : raw;
    return <ViewField key={field.key} label={field.label} value={shown || "—"} />;
  }

  function renderFieldControl(input) {
    if (input.type === "select") {
      return (
        <SearchableSelect
          label={input.label}
          options={input.options}
          value={values[input.name] ?? ""}
          onChange={(v) => updateValue(input.name, v)}
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
          disabled={!dependencyValue}
          loading={state?.loading}
          searchable={!!input.searchable}
          placeholder={
            !dependencyValue
              ? `Select ${panel.inputs.find((i) => i.name === input.dependsOn)?.label ?? "a value"} first`
              : undefined
          }
        />
      );
    }

    return (
      <input
        type={input.type === "password" ? "password" : "text"}
        required={input.required}
        value={values[input.name] ?? ""}
        onChange={(e) => updateValue(input.name, e.target.value)}
      />
    );
  }

  function renderField(input) {
    const state = input.type === "dynamic-select" ? dynamicOptions[input.name] : null;
    return (
      <div className="form-field" key={input.name}>
        <label>
          <span className="form-field-label-text">
            {input.label}
            {input.required && <span className="required-mark"> *</span>}
          </span>
          <InfoTooltip text={input.description} />
        </label>
        {renderFieldControl(input)}
        {state?.error && <span className="form-field-hint form-field-error">Couldn't load options: {state.error}</span>}
      </div>
    );
  }

  return createPortal(
    <div className="side-panel-overlay" onClick={onClose}>
      <div className="side-panel" onClick={(e) => e.stopPropagation()}>
        <div className="side-panel-header">
          <h3>{panel.title}</h3>
          <div className="side-panel-header-actions">
            {panel.fixedCredentials && (
              <FixedCredentialsViewer endpoint={panel.fixedCredentials.endpoint} label={panel.fixedCredentials.label} />
            )}
            <button type="button" className="icon-button" onClick={onClose} title="Close">
              ✕
            </button>
          </div>
        </div>

        <div className="side-panel-body">
          {phase !== "completed" && (
            <form onSubmit={handleSubmit} className="side-panel-form">
              {panel.inputs.map((input) => renderField(input))}

              {phase === "failed" && (
                <div className="modal-result modal-result-error">
                  <div className="modal-result-title">Error</div>
                  <pre>{error}</pre>
                </div>
              )}

              <div className="side-panel-actions">
                <button type="submit" className="run-button" disabled={phase === "running"}>
                  {phase === "running" ? panel.runningLabel || "Running..." : panel.submitLabel || "▶ Run"}
                </button>
              </div>
            </form>
          )}

          {phase === "completed" && result && (
            <div className="side-panel-result">
              {result._context?.length > 0 && (
                <div className="companion-result-context">
                  {result._context.map(({ label, value }) => (
                    <span key={label}>
                      <span className="companion-result-context-label">{label}:</span> {value}
                    </span>
                  ))}
                </div>
              )}
              {(panel.resultFields ?? []).map(renderResultField)}

              <div className="side-panel-actions side-panel-actions-row">
                <button type="button" className="run-button" onClick={handleApply} disabled={!onApply}>
                  Apply
                </button>
                <button type="button" className="secondary-button" onClick={reset}>
                  {panel.againLabel || "Run Again"}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>,
    document.body
  );
}
