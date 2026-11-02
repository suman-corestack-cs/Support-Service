import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

// A checkbox-list dropdown for fields that take more than one value at once
// (e.g. Resource Types) — same look and portal-positioning approach as
// SearchableSelect (see there for why: the Input section's overflow:hidden
// would otherwise clip the panel), except the panel stays open across
// clicks so several options can be toggled in one go, and the trigger shows
// a summary of the current selection instead of a single value.
export default function MultiSelectDropdown({ label, options, value, onChange, disabled, placeholder }) {
  const [open, setOpen] = useState(false);
  const [rect, setRect] = useState(null);
  const triggerRef = useRef(null);
  const panelRef = useRef(null);
  const selected = value ?? [];

  function updateRect() {
    if (triggerRef.current) {
      setRect(triggerRef.current.getBoundingClientRect());
    }
  }

  useEffect(() => {
    if (!open) return undefined;
    updateRect();

    function handleOutsideClick(e) {
      if (triggerRef.current?.contains(e.target) || panelRef.current?.contains(e.target)) return;
      setOpen(false);
    }
    function handleReposition() {
      updateRect();
    }

    document.addEventListener("mousedown", handleOutsideClick);
    window.addEventListener("scroll", handleReposition, true);
    window.addEventListener("resize", handleReposition);
    return () => {
      document.removeEventListener("mousedown", handleOutsideClick);
      window.removeEventListener("scroll", handleReposition, true);
      window.removeEventListener("resize", handleReposition);
    };
  }, [open]);

  function toggleOption(optionValue) {
    if (selected.includes(optionValue)) {
      onChange(selected.filter((v) => v !== optionValue));
    } else {
      onChange([...selected, optionValue]);
    }
  }

  const selectedLabels = options.filter((opt) => selected.includes(opt.value)).map((opt) => opt.label);
  const triggerText =
    selectedLabels.length === 0
      ? placeholder || `Select ${label}`
      : selectedLabels.length <= 2
      ? selectedLabels.join(", ")
      : `${selectedLabels.length} selected`;

  return (
    <div className={`searchable-select ${disabled ? "disabled" : ""}`}>
      <button
        type="button"
        ref={triggerRef}
        className={`searchable-select-trigger ${open ? "open" : ""}`}
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
      >
        <span className={`searchable-select-trigger-text ${selectedLabels.length ? "" : "placeholder"}`}>
          {triggerText}
        </span>
        <span className={`searchable-select-chevron ${open ? "open" : ""}`}>⌄</span>
      </button>

      {open &&
        !disabled &&
        rect &&
        createPortal(
          <div
            ref={panelRef}
            className="searchable-select-panel"
            style={{ position: "fixed", top: rect.bottom + 6, left: rect.left, width: rect.width }}
          >
            <ul className="searchable-select-list">
              {options.map((opt) => (
                <li
                  key={opt.value}
                  className={`searchable-select-option multi-select-option ${
                    selected.includes(opt.value) ? "selected" : ""
                  }`}
                  onClick={() => toggleOption(opt.value)}
                >
                  <input
                    type="checkbox"
                    className="multi-select-checkbox"
                    checked={selected.includes(opt.value)}
                    readOnly
                  />
                  {opt.label}
                </li>
              ))}
            </ul>
          </div>,
          document.body
        )}
    </div>
  );
}
