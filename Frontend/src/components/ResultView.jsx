import { useMemo, useState } from "react";

function toCsvValue(value) {
  if (value === null || value === undefined) return "";
  const s = typeof value === "object" ? JSON.stringify(value) : String(value);
  if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

function rowsToCsv(columns, rows) {
  const header = columns.map(toCsvValue).join(",");
  const body = rows.map((row) => columns.map((col) => toCsvValue(row[col])).join(",")).join("\n");
  return `${header}\n${body}`;
}

function downloadText(filename, content, mime) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

// An empty array counts too (vacuously — .every() on [] is true) so a
// section that genuinely came back with zero rows still renders as an
// (empty) table instead of falling back to a raw JSON dump.
function isArrayOfObjects(value) {
  return Array.isArray(value) && value.every((item) => isPlainObject(item));
}

function collectColumns(rows) {
  const columns = [];
  const seen = new Set();
  for (const row of rows) {
    for (const key of Object.keys(row)) {
      if (!seen.has(key)) {
        seen.add(key);
        columns.push(key);
      }
    }
  }
  return columns;
}

// Plain-text form of a cell's value, used for filtering/search — not for display.
function cellSearchText(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

// Renders any JSON value as a readable nested list instead of a JSON string —
// arrays become bullet lists, objects become "key: value" lists, recursively.
// This is what lets something like an IAM policy document (nested objects and
// arrays of statements) show up as an actual readable list instead of one
// long unreadable stringified blob.
function NestedValue({ value }) {
  if (value === null || value === undefined || value === "") {
    return <span className="nested-empty">—</span>;
  }

  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="nested-empty">[]</span>;
    return (
      <ul className="nested-list">
        {value.map((item, i) => (
          <li key={i}>{typeof item === "object" && item !== null ? <NestedValue value={item} /> : String(item)}</li>
        ))}
      </ul>
    );
  }

  if (typeof value === "object") {
    const entries = Object.entries(value);
    if (entries.length === 0) return <span className="nested-empty">{"{}"}</span>;
    return (
      <ul className="nested-list nested-object">
        {entries.map(([key, val]) => (
          <li key={key}>
            <span className="nested-key">{key}:</span>{" "}
            {typeof val === "object" && val !== null ? <NestedValue value={val} /> : String(val)}
          </li>
        ))}
      </ul>
    );
  }

  return String(value);
}

// Long text (e.g. a raw HTML/JSON error response) is truncated with an
// ellipsis by default so rows stay compact — click the cell to expand it in
// place and read the complete value, click again to collapse.
function TableCell({ value }) {
  const [expanded, setExpanded] = useState(false);

  if (value !== null && typeof value === "object") {
    return (
      <td className="result-table-cell-nested">
        <NestedValue value={value} />
      </td>
    );
  }

  const text = value === null || value === undefined ? "" : String(value);
  return (
    <td
      className={`result-table-cell-text ${expanded ? "expanded" : ""}`}
      onClick={() => text && setExpanded((v) => !v)}
      title={text && !expanded ? "Click to view the complete value" : undefined}
    >
      {text}
    </td>
  );
}

function slug(text) {
  return text.replace(/\s+/g, "-").toLowerCase();
}

// A few domain acronyms that should stay all-caps in a section title even
// after the generic title-casing below (e.g. "ri_current" -> "Ri Current"
// -> "RI Current"). Keep this list short and specific — it's a display-only
// fixup, not a general abbreviation dictionary.
const KEY_TITLE_ACRONYMS = { Ri: "RI" };

// "available_blobs" -> "Available Blobs". Only used for titles derived from
// object keys — actual filenames are shown as-is.
function prettifyKey(key) {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .split(" ")
    .map((word) => KEY_TITLE_ACRONYMS[word] || word)
    .join(" ");
}

// The backend sends CSV rows as plain value arrays (not one object per row
// repeating every column name) to keep large exports small on the wire.
// Zip them back into { column: value } objects for the table to render.
function normalizeRows(columns, rows) {
  if (rows.length > 0 && Array.isArray(rows[0])) {
    return rows.map((row) => Object.fromEntries(columns.map((col, i) => [col, row[i]])));
  }
  return rows;
}

// Pulls array-of-object fields out into their own table sections; whatever's
// left (scalars, nested objects) falls back to a plain JSON block.
function extractTableSections(obj) {
  const sections = [];
  const rest = {};
  for (const [key, value] of Object.entries(obj)) {
    if (isArrayOfObjects(value)) {
      sections.push({ title: prettifyKey(key), columns: collectColumns(value), rows: value });
    } else {
      rest[key] = value;
    }
  }
  return { sections, rest };
}

function DataTable({ title, columns, rows, downloadName }) {
  const [filter, setFilter] = useState("");

  const filteredRows = useMemo(() => {
    if (!filter.trim()) return rows;
    const needle = filter.trim().toLowerCase();
    return rows.filter((row) => columns.some((col) => cellSearchText(row[col]).toLowerCase().includes(needle)));
  }, [rows, columns, filter]);

  return (
    <div className="result-table-section">
      <div className="result-table-header">
        <h4>
          {title}{" "}
          <span className="result-table-count">
            ({filteredRows.length}
            {filteredRows.length !== rows.length ? ` of ${rows.length}` : ""})
          </span>
        </h4>
        <div className="result-table-actions">
          <input
            type="text"
            className="result-filter-input"
            placeholder="Filter rows..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
          <button
            className="icon-button"
            title="Download CSV"
            onClick={() =>
              downloadText(
                downloadName.endsWith(".csv") ? downloadName : `${downloadName}.csv`,
                rowsToCsv(columns, filteredRows),
                "text/csv"
              )
            }
          >
            ⬇
          </button>
        </div>
      </div>
      <div className="result-table-scroll">
        <table className="result-table">
          <thead>
            <tr>
              {columns.map((col) => (
                <th key={col}>{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filteredRows.map((row, idx) => (
              <tr key={idx}>
                {columns.map((col) => (
                  <TableCell key={col} value={row[col]} />
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {filteredRows.length === 0 && (
          <div className="result-table-empty">{rows.length === 0 ? "No data for this section." : "No rows match this filter."}</div>
        )}
      </div>
    </div>
  );
}

export default function ResultView({ result, scriptTitle }) {
  if (result === null || result === undefined) {
    return <div className="result-empty">No data returned.</div>;
  }

  const sections = [];
  let leftover = null;

  if (isPlainObject(result) && Array.isArray(result.columns) && Array.isArray(result.rows)) {
    // Already-tabular shape, e.g. { filename, columns, rows, row_count }
    sections.push({
      title: result.filename || "Data",
      columns: result.columns,
      rows: normalizeRows(result.columns, result.rows),
    });
    const remaining = Object.fromEntries(
      Object.entries(result).filter(([key]) => !["columns", "rows", "filename", "row_count"].includes(key))
    );
    const extra = extractTableSections(remaining);
    sections.push(...extra.sections);
    leftover = Object.keys(extra.rest).length > 0 ? extra.rest : null;
  } else if (isArrayOfObjects(result)) {
    sections.push({ title: "Results", columns: collectColumns(result), rows: result });
  } else if (isPlainObject(result)) {
    const extra = extractTableSections(result);
    sections.push(...extra.sections);
    leftover = Object.keys(extra.rest).length > 0 ? extra.rest : null;
  } else {
    leftover = result;
  }

  const hasLeftover = leftover !== null && leftover !== undefined;

  return (
    <div className="result-view">
      {sections.map((section) => (
        <DataTable
          key={section.title}
          title={section.title}
          columns={section.columns}
          rows={section.rows}
          downloadName={slug(`${scriptTitle}-${section.title}`)}
        />
      ))}

      {hasLeftover && (
        <div className="result-json-section">
          <div className="result-table-header">
            <h4>{sections.length > 0 ? "Additional Data" : "Response"}</h4>
            <button
              className="icon-button"
              title="Download JSON"
              onClick={() => downloadText(`${slug(scriptTitle)}.json`, JSON.stringify(leftover, null, 2), "application/json")}
            >
              ⬇
            </button>
          </div>
          <pre className="result-json">{JSON.stringify(leftover, null, 2)}</pre>
        </div>
      )}

      {sections.length === 0 && !hasLeftover && <div className="result-empty">No data returned.</div>}
    </div>
  );
}
