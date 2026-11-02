import { useState } from "react";
import { createPortal } from "react-dom";
import { deleteScript } from "../api";

const CONFIRM_WORD = "delete";

export default function DeleteScriptModal({ script, onClose, onDeleted }) {
  const [confirmText, setConfirmText] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState(null);

  const canDelete = confirmText.trim().toLowerCase() === CONFIRM_WORD;

  async function handleDelete() {
    if (!canDelete) return;
    setDeleting(true);
    setError(null);
    try {
      const result = await deleteScript(script.id);
      onDeleted(result);
    } catch (err) {
      setError(err.message || "Something went wrong.");
      setDeleting(false);
    }
  }

  return createPortal(
    <div className="source-modal-overlay" onClick={deleting ? undefined : onClose}>
      <div className="delete-script-modal" onClick={(e) => e.stopPropagation()}>
        <div className="source-modal-header">
          <h3>Delete script</h3>
          {!deleting && (
            <button type="button" className="icon-button" onClick={onClose} title="Close">
              ✕
            </button>
          )}
        </div>

        <div className="delete-script-body">
          <div className="note-callout note-callout-warning">
            <p>
              <strong>⚠</strong>&nbsp;
              This action will permanently delete <b>{script.title}</b> scripts and remove it from this console. This includes the script file, API route, and all associated backend and frontend code generated for it. <b>This action cannot be undone from the UI.</b>
            </p>
          </div>

          <p>
            Are you sure you want to delete <strong>{script.title}</strong>?
          </p>

          <div className="form-field">
            <label>
              <span className="form-field-label-text">
                Type <code>delete</code> to confirm
              </span>
            </label>
            <input
              type="text"
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder="delete"
              autoFocus
              disabled={deleting}
            />
          </div>

          {error && <div className="form-field-hint form-field-error">{error}</div>}
        </div>

        <div className="add-script-footer">
          <button type="button" className="link-button" onClick={onClose} disabled={deleting}>
            Cancel
          </button>
          <button type="button" className="danger-button" onClick={handleDelete} disabled={!canDelete || deleting}>
            {deleting ? "Deleting…" : "Delete"}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
