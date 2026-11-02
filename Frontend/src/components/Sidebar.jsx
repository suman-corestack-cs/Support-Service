import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { MODULES, SCRIPTS } from "../scriptsData";

const ICONS = {
  core: "◆",
  finops: "◈",
  secops: "◉",
  cloudops: "☁",
  reports: "▤",
  settings: "⚙",
};

export default function Sidebar({ counts, collapsed, onToggleCollapsed, onAddScript }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const { id: scriptId } = useParams();

  let activeModule = "all";
  if (location.pathname === "/") {
    activeModule = searchParams.get("module") || "all";
  } else if (scriptId) {
    const script = SCRIPTS.find((s) => s.id === scriptId);
    activeModule = script?.module ?? null;
  }

  function selectModule(moduleKey) {
    navigate(moduleKey === "all" ? "/" : `/?module=${moduleKey}`);
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="sidebar-logo"> <img src="./src/logo-corestack.png" alt="Support Siren" /></div>
        <div className="sidebar-brand-text">
          <div className="sidebar-title">Support Service</div>
          <div className="sidebar-subtitle">Console</div>
        </div>
        <button
          type="button"
          className="sidebar-collapse-toggle"
          onClick={onToggleCollapsed}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? "»" : "«"}
        </button>
      </div>

      <nav className="sidebar-nav">
        <button
          className={`sidebar-item ${activeModule === "all" ? "active" : ""}`}
          onClick={() => selectModule("all")}
          title="All Scripts"
        >
          <span className="sidebar-icon">{"▦"}</span>
          <span className="sidebar-item-label">All Scripts</span>
          <span className="sidebar-count">{counts.all ?? 0}</span>
        </button>

        <div className="sidebar-section-label">Bundles</div>

        {MODULES.map((module) => (
          <button
            key={module.key}
            className={`sidebar-item ${activeModule === module.key ? "active" : ""}`}
            onClick={() => selectModule(module.key)}
            title={module.label}
          >
            <span className="sidebar-icon">{ICONS[module.key] ?? "▦"}</span>
            <span className="sidebar-item-label">{module.label}</span>
            <span className="sidebar-count">{counts[module.key] ?? 0}</span>
          </button>
        ))}
      </nav>

      <div className="sidebar-footer">
        <button type="button" className="sidebar-add-script" onClick={onAddScript} title="Add Script">
          <span className="sidebar-icon">+</span>
          <span className="sidebar-item-label">Add Script</span>
        </button>
      </div>
    </aside>
  );
}
