import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { getScriptSource, saveScriptSource } from "../api";

const INDENT = "    ";

export default function ScriptSourceModal({ script, onClose }) {
  const [source, setSource] = useState(null);
  const [error, setError] = useState(null);

  // Edit mode: `draft` is the text being edited; null when just viewing.
  const [draft, setDraft] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null); // { message, errors: [] }
  const [notice, setNotice] = useState(null); // { summary, syntaxFixes: [] } after a successful save
  const textareaRef = useRef(null);

  const editing = draft !== null;
  const dirty = editing && draft !== source;

  useEffect(() => {
    let cancelled = false;
    setSource(null);
    setError(null);
    getScriptSource(script.id)
      .then((text) => {
        if (!cancelled) setSource(text);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [script.id]);

  // Closing while editing would silently throw away the edit — ask first.
  function requestClose() {
    if (saving) return;
    if (dirty && !window.confirm("Discard your unsaved changes to this script?")) return;
    onClose();
  }

  useEffect(() => {
    function handleKeyDown(e) {
      if (e.key === "Escape") requestClose();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  });

  function startEditing() {
    setDraft(source);
    setSaveError(null);
    setNotice(null);
    setTimeout(() => textareaRef.current?.focus(), 0);
  }

  function cancelEditing() {
    if (saving) return;
    setDraft(null);
    setSaveError(null);
  }

  async function handleSave() {
    setSaving(true);
    setSaveError(null);
    try {
      const result = await saveScriptSource(script.id, draft);
      setSource(result.source);
      setDraft(null);
      setNotice({ summary: result.summary, syntaxFixes: result.syntax_fixes || [] });
    } catch (err) {
      // Keep any syntax fixes Claude already applied so they aren't lost.
      if (typeof err.source === "string") setDraft(err.source);
      setSaveError({ message: err.message, errors: err.errors || [], syntaxFixes: err.syntaxFixes || [] });
    } finally {
      setSaving(false);
    }
  }

  // Tab inserts spaces instead of moving focus out of the editor.
  function handleEditorKeyDown(e) {
    if (e.key !== "Tab") return;
    e.preventDefault();
    const el = e.target;
    const { selectionStart, selectionEnd } = el;
    const next = draft.slice(0, selectionStart) + INDENT + draft.slice(selectionEnd);
    setDraft(next);
    requestAnimationFrame(() => {
      el.selectionStart = el.selectionEnd = selectionStart + INDENT.length;
    });
  }

  const lines = source ? source.split("\n") : [];
  const draftLineCount = editing ? draft.split("\n").length : 0;

  return createPortal(
    // stopPropagation: React bubbles portal clicks up to ScriptCard, whose
    // own onClick would otherwise navigate away to the script page.
    <div
      className="source-modal-overlay"
      onClick={(e) => {
        e.stopPropagation();
        requestClose();
      }}
    >
      <div className="source-modal" onClick={(e) => e.stopPropagation()}>
        <div className="source-modal-header">
          <div>
            <h3>{script.title}</h3>
            <span className="script-card-mono">{script.scriptFile}</span>
          </div>
          <div className="source-modal-header-actions">
            {source !== null && !editing && (
              <button type="button" className="icon-button" onClick={startEditing} title="Edit script">
                ✎
              </button>
            )}
            <button type="button" className="icon-button" onClick={requestClose} title="Close" disabled={saving}>
              ✕
            </button>
          </div>
        </div>

        {notice && !editing && (
          <div className="source-modal-notice success">
            <strong>Script saved.</strong> {notice.summary}
            {notice.syntaxFixes.length > 0 && (
              <>
                <div className="source-modal-notice-title">Claude fixed these syntax errors for you:</div>
                <ul>
                  {notice.syntaxFixes.map((fix, i) => (
                    <li key={i}>{fix}</li>
                  ))}
                </ul>
              </>
            )}
          </div>
        )}

        {saveError && editing && (
          <div className="source-modal-notice error">
            <strong>{saveError.message}</strong>
            {saveError.errors.length > 0 && (
              <ul>
                {saveError.errors.map((msg, i) => (
                  <li key={i}>{msg}</li>
                ))}
              </ul>
            )}
            {saveError.syntaxFixes.length > 0 && (
              <>
                <div className="source-modal-notice-title">Syntax errors already fixed in the editor below:</div>
                <ul>
                  {saveError.syntaxFixes.map((fix, i) => (
                    <li key={i}>{fix}</li>
                  ))}
                </ul>
              </>
            )}
          </div>
        )}

        <div className="source-modal-body">
          {error && <div className="empty-state">Couldn't load script source: {error}</div>}
          {!error && source === null && <div className="empty-state">Loading script…</div>}

          {editing && (
            <div className="source-editor">
              <div className="source-editor-gutter" aria-hidden="true">
                {Array.from({ length: draftLineCount }, (_, i) => (
                  <div key={i}>{i + 1}</div>
                ))}
              </div>
              <textarea
                ref={textareaRef}
                className="source-editor-input"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={handleEditorKeyDown}
                rows={draftLineCount + 1}
                wrap="off"
                spellCheck={false}
                readOnly={saving}
              />
            </div>
          )}

          {!editing && source !== null && (
            <pre className="source-code">
              <code>
                {lines.map((line, i) => (
                  <span className="source-code-line" key={i}>
                    <span className="source-code-line-number">{i + 1}</span>
                    <span className="source-code-line-text">{line}</span>
                  </span>
                ))}
              </code>
            </pre>
          )}
        </div>

        {editing && (
          <div className="source-modal-footer">
            <span className="source-modal-footer-hint">
              {saving ? "Claude is reviewing your changes…" : "On save, Claude fixes syntax errors and flags any other mistakes."}
            </span>
            <div className="source-modal-footer-actions">
              <button type="button" className="secondary-button" onClick={cancelEditing} disabled={saving}>
                Cancel
              </button>
              <button type="button" className="run-button" onClick={handleSave} disabled={saving || !dirty}>
                {saving ? "Saving…" : "Save"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>,
    document.body
  );
}
