import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, NavLink, Route, Routes, useLocation } from "react-router-dom";
import "./styles.css";
import { ToastProvider, usePoll } from "./ui";
import Dashboard from "./pages/Dashboard";
import Create from "./pages/Create";
import Scripts from "./pages/Scripts";
import Production from "./pages/Production";
import Library from "./pages/Library";
import Community from "./pages/Community";
import Validations from "./pages/Validations";
import Archives from "./pages/Archives";
import Publication from "./pages/Publication";
import Settings from "./pages/Settings";
import Bible from "./pages/Bible";

const NAV = [
  ["/", "Dashboard"],
  ["/creation", "Création"],
  ["/scenarios", "Scénarios"],
  ["/production", "Production"],
  ["/bibliotheque", "Bibliothèque"],
  ["/communaute", "Communauté"],
  ["/validations", "Validations"],
  ["/archives", "Archives"],
  ["/publication", "Publication"],
  ["/parametres", "Paramètres"],
];

function Shell() {
  const [open, setOpen] = useState(false);
  const loc = useLocation();
  const { data: status } = usePoll<any>("/api/status", 6000);
  const { data: vals } = usePoll<any[]>("/api/validations", 4000);
  return (
    <div className="shell">
      <button className="menu-btn" onClick={() => setOpen(!open)} aria-label="Menu">
        ☰ Menu
      </button>
      <nav className={`sidebar ${open ? "open" : ""}`} onClick={() => setOpen(false)}>
        <div className="brand">
          <div className="brand-core" />
          <div>
            <b>MULTIVERSE</b>
            <span>STUDIO · LOCAL</span>
          </div>
        </div>
        <div className="nav">
          {NAV.map(([to, label], i) => (
            <NavLink key={to} to={to} end={to === "/"}>
              <span className="num">{String(i + 1).padStart(2, "0")}</span>
              {label}
              {to === "/validations" && vals && vals.length > 0 && <span className="badge">{vals.length}</span>}
            </NavLink>
          ))}
          <NavLink to="/bible">
            <span className="num">◇</span>Bibles des séries
          </NavLink>
        </div>
        <div className="sidebar-foot">
          {status ? (
            <>
              <div className="row">
                <span className={`dot ${status.queue_paused ? "" : "live"}`} />
                {status.queue_paused ? "File en pause" : "File active"}
              </div>
              <div>IA : {status.demo_mode ? "mode démo (gratuit)" : status.llm.active}</div>
              <div>Voix : {status.tts.active === "none" ? "désactivées" : status.tts.active}</div>
            </>
          ) : (
            "Connexion au serveur local…"
          )}
        </div>
      </nav>
      <main key={loc.pathname}>
        {status?.demo_mode && (
          <div className="demo-banner">
            ◆ MODE DÉMO — scénarios et critiques générés localement par gabarits, sans IA et sans facturation.
            Configurez un fournisseur dans Paramètres pour l'écriture par IA.
          </div>
        )}
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/creation" element={<Create />} />
          <Route path="/scenarios" element={<Scripts />} />
          <Route path="/production" element={<Production />} />
          <Route path="/bibliotheque" element={<Library />} />
          <Route path="/communaute" element={<Community />} />
          <Route path="/validations" element={<Validations />} />
          <Route path="/archives" element={<Archives />} />
          <Route path="/publication" element={<Publication />} />
          <Route path="/parametres" element={<Settings />} />
          <Route path="/bible" element={<Bible />} />
          <Route path="*" element={<p>Page introuvable.</p>} />
        </Routes>
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <ToastProvider>
        <Shell />
      </ToastProvider>
    </BrowserRouter>
  </StrictMode>,
);
