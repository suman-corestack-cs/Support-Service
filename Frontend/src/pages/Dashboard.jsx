import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import Topbar from "../components/Topbar";
import FilterPanel from "../components/FilterPanel";
import ScriptCard from "../components/ScriptCard";
import { MODULES, SCRIPTS } from "../scriptsData";

const EMPTY_FILTERS = { clouds: [] };

export default function Dashboard() {
  const [searchParams] = useSearchParams();
  const activeModule = searchParams.get("module") || "all";

  const [search, setSearch] = useState("");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [filters, setFilters] = useState(EMPTY_FILTERS);

  const visibleScripts = useMemo(() => {
    return SCRIPTS.filter((script) => {
      if (activeModule !== "all" && script.module !== activeModule) return false;

      if (filters.clouds.length > 0 && !filters.clouds.includes(script.cloud)) return false;

      if (search.trim()) {
        const haystack = `${script.title} ${script.description} ${script.scriptFile}`.toLowerCase();
        if (!haystack.includes(search.trim().toLowerCase())) return false;
      }

      return true;
    });
  }, [activeModule, filters, search]);

  function toggleCloud(cloud) {
    setFilters((prev) => ({
      ...prev,
      clouds: prev.clouds.includes(cloud) ? prev.clouds.filter((c) => c !== cloud) : [...prev.clouds, cloud],
    }));
  }

  const activeModuleLabel =
    activeModule === "all" ? "All Scripts" : MODULES.find((m) => m.key === activeModule)?.label ?? activeModule;

  return (
    <>
      <Topbar
        heading={activeModuleLabel}
        search={search}
        onSearchChange={setSearch}
        onToggleFilters={() => setFiltersOpen((v) => !v)}
        filtersOpen={filtersOpen}
      />

      <div className="app-content">
        <div className="script-grid">
          {visibleScripts.length === 0 ? (
            <div className="empty-state">No scripts match the current filters.</div>
          ) : (
            visibleScripts.map((script) => <ScriptCard key={script.id} script={script} />)
          )}
        </div>

        {filtersOpen && (
          <FilterPanel
            filters={filters}
            onToggleCloud={toggleCloud}
            onClear={() => setFilters(EMPTY_FILTERS)}
          />
        )}
      </div>
    </>
  );
}
