import { useState } from "react";
import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar";
import AddScriptWizard from "./AddScriptWizard";
import { MODULES, SCRIPTS } from "../scriptsData";

export default function Layout() {
  const [collapsed, setCollapsed] = useState(false);
  const [addScriptOpen, setAddScriptOpen] = useState(false);

  const counts = { all: SCRIPTS.length };
  for (const module of MODULES) {
    counts[module.key] = SCRIPTS.filter((s) => s.module === module.key).length;
  }

  return (
    <div className={`app-shell ${collapsed ? "sidebar-collapsed" : ""}`}>
      <Sidebar
        counts={counts}
        collapsed={collapsed}
        onToggleCollapsed={() => setCollapsed((v) => !v)}
        onAddScript={() => setAddScriptOpen(true)}
      />
      <div className="app-main">
        <Outlet />
      </div>
      {addScriptOpen && <AddScriptWizard onClose={() => setAddScriptOpen(false)} />}
    </div>
  );
}
