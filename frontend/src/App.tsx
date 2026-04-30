import { NavLink, Route, Routes } from "react-router-dom";
import { Activity, Database, FlaskConical, Gauge, RadioTower } from "lucide-react";
import { RunsPage } from "./pages/RunsPage";
import { RunDetailPage } from "./pages/RunDetailPage";
import { ComparePage } from "./pages/ComparePage";

const links = [{ to: "/", label: "Task Center", icon: Activity }];

export default function App() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">
            <FlaskConical size={22} />
          </div>
          <p className="eyebrow">Trading Agent Ultra</p>
          <h1>Signal Research Terminal</h1>
          <p className="brand-copy">
            Queue experiments, monitor worker execution, and inspect market diagnostics in one research cockpit.
          </p>
        </div>
        <nav className="nav">
          {links.map((link) => (
            <NavLink
              key={link.to}
              className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
              to={link.to}
            >
              <link.icon size={18} aria-hidden="true" />
              {link.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-stack" aria-label="Runtime status">
          <div className="sidebar-note">
            <Gauge size={18} aria-hidden="true" />
            <div>
              <strong>Worker Mode</strong>
              <p>API-managed local worker</p>
            </div>
          </div>
          <div className="sidebar-note">
            <Database size={18} aria-hidden="true" />
            <div>
              <strong>Market Source</strong>
              <p>Postgres daily snapshots</p>
            </div>
          </div>
          <div className="sidebar-note">
            <RadioTower size={18} aria-hidden="true" />
            <div>
              <strong>Refresh Mode</strong>
              <p>Manual dashboard refresh</p>
            </div>
          </div>
        </div>
      </aside>
      <main className="main-panel">
        <Routes>
          <Route path="/" element={<RunsPage />} />
          <Route path="/runs/:runId" element={<RunDetailPage />} />
          <Route path="/runs/:runId/compare" element={<ComparePage />} />
        </Routes>
      </main>
    </div>
  );
}
