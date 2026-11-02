import { CLOUDS } from "../scriptsData";

export default function FilterPanel({ filters, onToggleCloud, onClear }) {
  return (
    <aside className="filter-panel">
      <div className="filter-panel-header">
        <span>Script Filters</span>
        <button className="link-button" onClick={onClear}>
          Clear
        </button>
      </div>

      <div className="filter-group">
        <div className="filter-group-title">Cloud</div>
        {CLOUDS.map((cloud) => (
          <label key={cloud} className="filter-checkbox">
            <input
              type="checkbox"
              checked={filters.clouds.includes(cloud)}
              onChange={() => onToggleCloud(cloud)}
            />
            <span className="filter-dot" data-cloud={cloud} />
            {cloud}
          </label>
        ))}
      </div>
    </aside>
  );
}
