import { useEffect, useState } from "react";

function formatBytes(n) {
  if (n >= 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(2)} MiB`;
  if (n >= 1024) return `${(n / 1024).toFixed(2)} KiB`;
  return `${n} B`;
}

// If total looks like a byte count rather than a small step count, show it as MiB/KiB.
function formatCount(n, total) {
  if (total && total > 10000) return formatBytes(n);
  return String(n);
}

export default function ProgressBar({ status, processed, total, startedAt }) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (status !== "running") return undefined;
    const interval = setInterval(() => {
      setElapsed(Math.round((performance.now() - startedAt) / 1000));
    }, 500);
    return () => clearInterval(interval);
  }, [status, startedAt]);

  if (status === "idle") return null;

  const known = typeof total === "number" && total > 0;
  const percent = known ? Math.min(100, Math.round((processed / total) * 100)) : null;

  return (
    <div className={`progress-box progress-${status}`}>
      <div className="progress-track">
        <div
          className={`progress-fill ${known ? "" : "progress-indeterminate"}`}
          style={known ? { width: `${percent}%` } : undefined}
        />
      </div>
      <div className="progress-label">
        {status === "running" && known && `${percent}% (${formatCount(processed, total)} / ${formatCount(total, total)})`}
        {status === "running" && !known && `Running… ${elapsed}s elapsed`}
        {status === "completed" && "Completed"}
        {status === "failed" && "Failed"}
      </div>
    </div>
  );
}
