import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

// A custom dropdown: a bordered "Label : Value" trigger button that opens a
// panel with an optional filter box and an option list (selected option
// highlighted). Options are always [{value, label}, ...] — used for every
// select-like field (plain "select", "dynamic-select", "async-select") so
// all dropdowns in the app share one look, with `searchable` opting a
// specific field into the filter box.
//
// The panel is rendered through a portal, positioned from the trigger's own
// bounding rect, rather than plain `position: absolute` — the Input section
// lives inside an accordion with `overflow: hidden` (for its rounded
// corners), which would otherwise clip the panel.
export default function SearchableSelect({
  label,
  options,
  value,
  onChange,
  disabled,
  searchable,
  placeholder,
  loading,
  compact,
}) {
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("");
  const [rect, setRect] = useState(null);
  const triggerRef = useRef(null);
  const panelRef = useRef(null);

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
      setFilter("");
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

  const selectedOption = options.find((opt) => opt.value === value);
  const filteredOptions =
    searchable && filter.trim()
      ? options.filter((opt) => opt.label.toLowerCase().includes(filter.trim().toLowerCase()))
      : options;

  function selectOption(opt) {
    onChange(opt.value);
    setOpen(false);
    setFilter("");
  }

  return (
    <div className={`searchable-select ${disabled ? "disabled" : ""} ${compact ? "compact" : ""}`}>
      <button
        type="button"
        ref={triggerRef}
        className={`searchable-select-trigger ${open ? "open" : ""}`}
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
      >
        <span className={`searchable-select-trigger-text ${selectedOption ? "" : "placeholder"}`}>
          {loading ? "Loading…" : selectedOption ? selectedOption.label : placeholder || `Select ${label}`}
        </span>
        <span className={`searchable-select-chevron ${open ? "open" : ""}`}>⌄</span>
      </button>

      {open &&
        !disabled &&
        rect &&
        (() => {
          // If the trigger lives inside an element marked
          // data-select-boundary (e.g. a modal's scrollable body), the panel
          // is confined to that element's own box instead of the whole
          // viewport — otherwise, inside a modal, it can visually spill out
          // past the modal's edges into whatever's behind it.
          const boundaryEl = triggerRef.current?.closest("[data-select-boundary]");
          const boundaryRect = boundaryEl ? boundaryEl.getBoundingClientRect() : null;
          const viewportTop = boundaryRect ? boundaryRect.top : 0;
          const viewportBottom = boundaryRect ? boundaryRect.bottom : window.innerHeight;

          const margin = 10;
          const spaceBelow = viewportBottom - rect.bottom - margin;
          const spaceAbove = rect.top - viewportTop - margin;
          const openUpward = spaceBelow < 160 && spaceAbove > spaceBelow;
          const maxHeight = Math.max(100, Math.min(280, openUpward ? spaceAbove : spaceBelow));
          const panelStyle = openUpward
            ? { position: "fixed", bottom: window.innerHeight - rect.top + 6, left: rect.left, width: rect.width, maxHeight }
            : { position: "fixed", top: rect.bottom + 6, left: rect.left, width: rect.width, maxHeight };

          return createPortal(
            <div ref={panelRef} className={`searchable-select-panel ${compact ? "compact" : ""}`} style={panelStyle}>
              {searchable && (
                <input
                  type="text"
                  autoFocus
                  className="searchable-select-filter"
                  placeholder="Filter..."
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                />
              )}
              <ul className="searchable-select-list">
                {filteredOptions.length === 0 && <li className="searchable-select-empty">No options found</li>}
                {filteredOptions.map((opt) => (
                  <li
                    key={opt.value}
                    className={`searchable-select-option ${opt.value === value ? "selected" : ""}`}
                    onClick={() => selectOption(opt)}
                  >
                    {opt.label}
                  </li>
                ))}
              </ul>
            </div>,
            document.body
          );
        })()}
    </div>
  );
}
