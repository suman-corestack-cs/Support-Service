# Service Support Project - Frontend

React + Vite dashboard for browsing and running the backend's support scripts.

## Setup

```bash
npm install
npm run dev
```

Runs at `http://localhost:5173`. Make sure the backend is running (see `Backend/README.md`) — the API base URL is configured in `.env` as `VITE_API_BASE_URL`.

## Structure

- `src/scriptsData.js` — one entry per backend endpoint: title, description, inputs, outputs. This is what drives the sidebar counts, the dashboard cards, and the auto-generated run form. Add a script here when a new backend endpoint is implemented.
- `src/components/Sidebar.jsx` — module bundles (Core, FinOps, SecOps, CloudOps, Reports, Settings).
- `src/components/ScriptCard.jsx` — the dashboard tile: title, module/cloud/script/endpoint, description, inputs, output.
- `src/components/FilterPanel.jsx` — cloud and HTTP method checkboxes.
- `src/components/RunModal.jsx` — dynamically builds a form from a script's `inputs` and calls the backend via `src/api.js`.
