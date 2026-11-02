import { BrowserRouter, Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import ScriptPage from "./pages/ScriptPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/scripts/:id" element={<ScriptPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
