import { useState } from "react";
import { useNavigate } from "react-router-dom";
import ScriptSourceModal from "./ScriptSourceModal";

const DESCRIPTION_LIMIT = 130;

export default function ScriptCard({ script }) {
  const navigate = useNavigate();
  const [sourceOpen, setSourceOpen] = useState(false);
  const isLongDescription = script.description.length > DESCRIPTION_LIMIT;

  return (
    <div className="script-card" onClick={() => navigate(`/scripts/${script.id}`)}>
      <div className="script-card-bar" data-cloud={script.cloud ?? "none"} />

      <div className="script-card-body">
        <div className="script-card-header">
          <span className="script-card-icon">◆</span>
          <h3 className="script-card-title">{script.title}</h3>
        </div>

        <div className="script-card-row">
          <span className="script-card-label">Module:</span>
          <span className="script-card-value">{script.module}</span>
        </div>
        {script.cloud && (
          <div className="script-card-row">
            <span className="script-card-label">Cloud:</span>
            <span className="script-card-value">{script.cloud}</span>
          </div>
        )}
        <div className="script-card-row">
          <span className="script-card-label">Script:</span>
          <span className="script-card-value script-card-mono">{script.scriptFile}</span>
        </div>
        <div className="script-card-row">
          <span className="script-card-label">Endpoint:</span>
          <span className="script-card-value script-card-mono">
            {script.method} {script.endpoint}
          </span>
        </div>

        <div className="script-card-description-wrap">
          <p className="script-card-description">{script.description}</p>
          {isLongDescription && (
            <span className="more-trigger" onClick={(e) => e.stopPropagation()}>
              more…
              <span className="tooltip">{script.description}</span>
            </span>
          )}
        </div>
      </div>

      <div className="script-card-footer">
        <button
          type="button"
          className="secondary-button"
          onClick={(e) => {
            e.stopPropagation();
            setSourceOpen(true);
          }}
        >
          View Script
        </button>
        <button className="run-button" onClick={(e) => { e.stopPropagation(); navigate(`/scripts/${script.id}`); }}>
          Open ▶
        </button>
      </div>

      {sourceOpen && <ScriptSourceModal script={script} onClose={() => setSourceOpen(false)} />}
    </div>
  );
}
