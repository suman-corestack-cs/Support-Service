import { useRef, useState } from "react";

const TOOLTIP_WIDTH = 230;
const MARGIN = 16;
// The tooltip's own height varies with text length, and it isn't in the DOM
// yet when deciding which way to open it — this is a conservative stand-in
// for "enough room to read a few lines of text comfortably", not an attempt
// to predict the exact rendered height.
const ASSUMED_TOOLTIP_HEIGHT = 120;

// The small "ⓘ" hover tooltip used next to a field label or a script title.
// A fixed-size box anchored to one side/direction of the icon can't just
// always open the same way — an icon near the left edge of the screen needs
// it growing rightward, one near the top edge (e.g. a script's own title,
// which sits right at the top of the page) needs it growing downward instead
// of its usual upward, and which is which depends on the actual viewport
// size and the icon's real position, not on where it happens to sit in the
// layout (that changes as the page scrolls or the grid reflows). So this
// measures the icon's own position on hover/focus and picks whichever
// side/direction actually has room, the same way SearchableSelect's dropdown
// panel decides whether to open upward or downward.
export default function InfoTooltip({ text }) {
  const [align, setAlign] = useState({ horizontal: "left", vertical: "above" });
  const iconRef = useRef(null);

  function updateAlign() {
    const el = iconRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();

    const spaceRight = window.innerWidth - rect.left - MARGIN;
    const spaceLeft = rect.right - MARGIN;
    const horizontal = spaceRight < TOOLTIP_WIDTH && spaceLeft > spaceRight ? "right" : "left";

    const spaceAbove = rect.top - MARGIN;
    const spaceBelow = window.innerHeight - rect.bottom - MARGIN;
    const vertical = spaceAbove < ASSUMED_TOOLTIP_HEIGHT && spaceBelow > spaceAbove ? "below" : "above";

    setAlign({ horizontal, vertical });
  }

  if (!text) return null;

  const className = [
    "info-tooltip",
    align.horizontal === "right" ? "align-right" : "",
    align.vertical === "below" ? "align-below" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <span className="info-icon" tabIndex={0} ref={iconRef} onMouseEnter={updateAlign} onFocus={updateAlign}>
      ⓘ
      <span className={className}>{text}</span>
    </span>
  );
}
