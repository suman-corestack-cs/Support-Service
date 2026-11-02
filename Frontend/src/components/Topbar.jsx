export default function Topbar({ heading, search, onSearchChange, onToggleFilters, filtersOpen }) {
  return (
    <header className="topbar">
      <div className="topbar-heading">{heading}</div>

      <div className="topbar-actions">
        <div className="search-box">
          <span className="search-icon">⌕</span>
          <input
            type="text"
            placeholder="Search scripts..."
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
          />
        </div>

        <button
          className={`icon-button ${filtersOpen ? "active" : ""}`}
          title="Toggle filters"
          onClick={onToggleFilters}
        >
          <svg
            width="15"
            height="15"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
          </svg>
        </button>
      </div>
    </header>
  );
}
