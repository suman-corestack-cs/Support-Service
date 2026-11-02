export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

// Turns a server-relative path (e.g. a `download_url` from a job status
// response) into an absolute URL the browser can navigate to directly.
export function absoluteUrl(path) {
  return `${API_BASE_URL}${path}`;
}

export async function getScriptSource(scriptId) {
  const response = await fetch(`${API_BASE_URL}/scripts/${scriptId}/source`);
  const text = await response.text();
  if (!response.ok) {
    const error = new Error(`Could not load script source (status ${response.status})`);
    error.status = response.status;
    throw error;
  }
  return text;
}

// Saves an edit made in the View Script modal. Claude reviews it on the
// server: syntax errors come back already fixed (in `source`/`syntax_fixes`),
// any other mistake rejects the save. A rejection throws an Error carrying
// `errors` (list of messages) and `source` (the code with syntax fixes
// applied) so the editor can show both.
export async function saveScriptSource(scriptId, source) {
  const response = await fetch(`${API_BASE_URL}/admin/scripts/${encodeURIComponent(scriptId)}/source`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source }),
  });
  const data = await parseBody(response);
  if (response.ok) return data;

  const detail = data && data.detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const error = new Error(detail.message || `Save failed with status ${response.status}`);
    error.errors = detail.errors || [];
    error.source = detail.source;
    error.syntaxFixes = detail.syntax_fixes || [];
    throw error;
  }
  throw toRequestError(response, data);
}

async function parseBody(response) {
  const text = await response.text();
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function toRequestError(response, data) {
  const message = (data && data.detail) || `Request failed with status ${response.status}`;
  const error = new Error(message);
  error.data = data;
  error.status = response.status;
  return error;
}

function isInputSubmittable(input, values) {
  if (input.excludeFromSubmit) return false;
  if (input.showWhen && !input.showWhen(values)) return false;
  return true;
}

function buildRequestInit(script, values) {
  if (script.requestType === "multipart/form-data") {
    const formData = new FormData();
    for (const input of script.inputs) {
      if (!isInputSubmittable(input, values)) continue;
      const value = values[input.name];
      if (input.type === "file") {
        if (value) formData.append(input.name, value);
      } else if (value !== undefined && value !== "") {
        formData.append(input.name, value);
      }
    }
    return { method: script.method, body: formData };
  }

  const body = {};
  for (const input of script.inputs) {
    if (!isInputSubmittable(input, values)) continue;
    let value = values[input.name];
    if (value === undefined || value === "") continue;
    if (input.type === "list") {
      value = String(value)
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
    } else if (input.type === "number") {
      value = Number(value);
    }
    body[input.name] = value;
  }
  return {
    method: script.method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

// Shared reader for the app's NDJSON streaming contract: zero or more
// {"status":"running", ...} lines followed by exactly one {"status":
// "completed", "result": ...} or {"status":"failed", "error": ...} line, all
// over a single response body. Used by every endpoint built on
// app/execution.py (script runs and the internal /mongo/query lookups).
async function readNdjsonResult(response, onUpdate) {
  if (!response.ok) {
    throw toRequestError(response, await parseBody(response));
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let newlineIndex;
    while ((newlineIndex = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, newlineIndex).trim();
      buffer = buffer.slice(newlineIndex + 1);
      if (!line) continue;

      const event = JSON.parse(line);
      onUpdate?.(event);

      if (event.status === "completed") return event.result;
      if (event.status === "failed") throw new Error(event.error || "Request failed");
    }
  }

  throw new Error("Connection closed before the request finished.");
}

// Runs the script over a single HTTP request. The backend streams
// newline-delimited progress lines over that one connection and ends with
// exactly one "completed" or "failed" line — no polling, no separate calls.
// onUpdate(event) fires for every line as it arrives; the promise resolves
// with the final result or throws with the script's error message.
export async function runScriptWithProgress(script, values, onUpdate) {
  const response = await fetch(`${API_BASE_URL}${script.endpoint}`, buildRequestInit(script, values));
  return readNdjsonResult(response, onUpdate);
}

// Same NDJSON contract as runScriptWithProgress, but for callers that already
// have the exact JSON body to send (e.g. a body assembled from more than one
// form field, like the companion panel deriving role_arn/external_id from a
// single "Cloud Account" selection) rather than one built straight from a
// script's own `inputs`.
export async function runJsonWithProgress(endpoint, body, onUpdate) {
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readNdjsonResult(response, onUpdate);
}

// Runs a read-only query via POST /mongo/query (see Backend/app/mongo_routes.py)
// and resolves with its result ({"documents": [...], "count": N} or
// {"count": N}). Used to power dropdowns whose options come from Mongo
// (e.g. the master-account list) rather than being fixed in scriptsData.js.
export async function queryMongo(body) {
  const response = await fetch(`${API_BASE_URL}/mongo/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readNdjsonResult(response);
}

// --- Resumable background-job flow (scripts with resultMode: "job") ---
//
// Unlike runScriptWithProgress, this doesn't hold one connection open for the
// whole run: POST starts the job on the server (which keeps running in a
// background thread regardless of what the browser does afterward) and
// returns a job id immediately. The caller polls /status with that id — even
// from a freshly reloaded page — to pick up progress or the finished result.

export async function startJob(script, values) {
  const url = `${API_BASE_URL}${script.endpoint}`;
  const response = await fetch(url, buildRequestInit(script, values));
  const data = await parseBody(response);
  if (!response.ok) throw toRequestError(response, data);
  return data.job_id;
}

export async function getJobStatus(script, jobId) {
  const url = `${API_BASE_URL}${script.endpoint}/${jobId}/status`;
  const response = await fetch(url);
  const data = await parseBody(response);
  if (!response.ok) throw toRequestError(response, data);
  return data;
}

// Polls until the job finishes. onUpdate(status) fires after every poll.
// Resolves with the job's result, or throws with its error message.
export async function pollJobUntilDone(script, jobId, onUpdate, { intervalMs = 800 } = {}) {
  for (;;) {
    const job = await getJobStatus(script, jobId);
    onUpdate?.(job);

    if (job.status === "completed") return job.result;
    if (job.status === "failed") throw new Error(job.error || "Job failed");

    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}

// Submits the "Add Script" wizard: a plain (non-streaming) JSON response,
// since this is a one-shot admin action — not a script run — and the backend
// call it triggers (Claude analyzing the upload) can take a while.
export async function submitAddScript({ scriptName, bundle, cloud, description, scriptFiles, outputFiles }) {
  const formData = new FormData();
  formData.append("script_name", scriptName);
  formData.append("bundle", bundle);
  if (cloud) formData.append("cloud", cloud);
  formData.append("description", description || "");
  for (const file of scriptFiles) formData.append("script_files", file);
  for (const file of outputFiles) formData.append("output_files", file);

  const response = await fetch(`${API_BASE_URL}/admin/add-script`, { method: "POST", body: formData });
  const data = await parseBody(response);
  if (!response.ok) throw toRequestError(response, data);
  return data;
}

// Reverses submitAddScript: removes a script's code and its entries from the
// running app. Same restart caveat as adding one — the route doesn't
// actually disappear until the backend restarts.
export async function deleteScript(scriptId) {
  const response = await fetch(`${API_BASE_URL}/admin/scripts/${encodeURIComponent(scriptId)}`, { method: "DELETE" });
  const data = await parseBody(response);
  if (!response.ok) throw toRequestError(response, data);
  return data;
}
