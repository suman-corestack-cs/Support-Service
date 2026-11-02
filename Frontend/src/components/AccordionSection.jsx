export default function AccordionSection({ title, subtitle, isOpen, onToggle, children }) {
  return (
    <div className={`accordion-section ${isOpen ? "open" : "closed"}`}>
      <button type="button" className="accordion-header" onClick={onToggle} aria-expanded={isOpen}>
        <span className={`accordion-chevron ${isOpen ? "open" : ""}`}>▸</span>
        <span className="accordion-title">{title}</span>
        {subtitle && <span className="accordion-subtitle">{subtitle}</span>}
      </button>
      {isOpen && <div className="accordion-body">{children}</div>}
    </div>
  );
}
