import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Route, Routes, useLocation, useParams } from "react-router-dom";
import { Bell, Info, List, MagnifyingGlass, Moon, Pill, ArrowsLeftRight, SquaresFour, GitBranch, Sun, X } from "@phosphor-icons/react";
import type { Icon } from "@phosphor-icons/react";
import { ComingSoon } from "../features/aakaash/pages/ComingSoon";
import { DataMethods } from "../features/aakaash/pages/DataMethods";
import { MedicinePage } from "../features/aakaash/pages/MedicinePage";
import { MODULE_COMPONENTS, modulePath, SCREENS } from "../features/aakaash/registry";
import { StatusProvider, useStatus } from "../features/aakaash/StatusContext";
import { Sticker } from "../features/aakaash/components/Sticker";
import { applyTheme, readTheme, type Theme } from "./theme";

const ICONS: Record<string, Icon> = {
  home: MagnifyingGlass,
  checker: Pill,
  dashboard: SquaresFour,
  interaction_risk: ArrowsLeftRight,
  personalized_alert: Bell,
  trace: GitBranch,
  about: Info,
};

/** Screens whose tables and charts use the full width; the others are text pages. */
const WIDE_PATHS = new Set(["/dashboard", "/trace"]);

function ModuleRoute() {
  const { id = "" } = useParams();
  const Custom = MODULE_COMPONENTS[id];
  return Custom ? <Custom /> : <ComingSoon id={id} />;
}

function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(readTheme);
  const next: Theme = theme === "dark" ? "light" : "dark";
  const Glyph = next === "dark" ? Moon : Sun;
  return (
    <button
      type="button"
      className="btn btn-secondary theme-toggle"
      onClick={() => {
        applyTheme(next);
        setTheme(next);
      }}
    >
      <Glyph size={16} />
      {next === "dark" ? "Dark theme" : "Light theme"}
    </button>
  );
}

function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const q = useStatus();
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (open) closeRef.current?.focus();
  }, [open]);
  const link = ({ isActive }: { isActive: boolean }) => (isActive ? "nav-link nav-active active font-nav" : "nav-link font-nav");
  const soonLink = ({ isActive }: { isActive: boolean }) => (isActive ? "nav-link nav-soon nav-active active" : "nav-link nav-soon");
  return (
    <aside className={open ? "sidebar open" : "sidebar"} id="navigation" aria-label="Navigation">
      <div className="sidebar-head">
        <div>
          <div className="sidebar-title">Medication Safety Support</div>
          <div className="sidebar-sub font-nav">Subareas A and B</div>
        </div>
        <button ref={closeRef} type="button" className="btn btn-plain btn-icon btn-sm mobile-only" aria-label="Close menu" onClick={onClose}>
          <X size={18} />
        </button>
      </div>
      <nav className="sidebar-nav" aria-label="Main">
        <ul>
          {SCREENS.map((s) => {
            const Glyph = ICONS[s.id];
            return (
              <li key={s.id}>
                <NavLink to={s.path} end={s.path === "/"} className={link}>
                  {Glyph && <Glyph size={18} aria-hidden="true" />}
                  {s.label}
                </NavLink>
              </li>
            );
          })}
        </ul>
        <h2 className="nav-heading font-nav">Coming soon</h2>
        {q.state === "loading" && !q.data && <p className="small muted nav-note">Loading…</p>}
        {q.state === "error" && (
          <p className="small nav-note">
            Module list unavailable. <button type="button" className="btn btn-plain btn-sm" onClick={q.reload}>Retry</button>
          </p>
        )}
        <ul>
          {q.data?.modules.map((m) => (
            <li key={m.id}>
              <NavLink to={modulePath(m.id)} className={soonLink}>
                <span>{m.label}</span>
                <Sticker>Soon</Sticker>
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      <div className="sidebar-foot">
        <ThemeToggle />
      </div>
    </aside>
  );
}

export function App() {
  const [drawer, setDrawer] = useState(false);
  const { pathname } = useLocation();
  useEffect(() => setDrawer(false), [pathname]);
  useEffect(() => {
    document.body.classList.toggle("drawer-open", drawer);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setDrawer(false);
    window.addEventListener("keydown", esc);
    return () => {
      window.removeEventListener("keydown", esc);
      document.body.classList.remove("drawer-open");
    };
  }, [drawer]);
  return (
    <StatusProvider>
      <a className="skip-link" href="#main">Skip to content</a>
      <div className="app">
        <Sidebar open={drawer} onClose={() => setDrawer(false)} />
        <div className="main-col">
          <header className="mobile-bar">
            <button type="button" className="btn btn-secondary btn-icon btn-sm" aria-label="Open menu" aria-expanded={drawer} aria-controls="navigation" onClick={() => setDrawer(true)}>
              <List size={18} />
            </button>
            <strong>Medication Safety Support</strong>
          </header>
          <div className="banner" role="note">Research prototype. Decision support only. Not medical advice.</div>
          <main className={WIDE_PATHS.has(pathname) ? "content wide" : "content"} id="main" tabIndex={-1}>
            <Routes>
              {SCREENS.map((s) => (
                <Route key={s.id} path={s.path} element={<s.Component />} />
              ))}
              <Route path="/about/data" element={<DataMethods />} />
              <Route path="/medicine/:setId" element={<MedicinePage />} />
              <Route path="/modules/:id" element={<ModuleRoute />} />
              <Route path="*" element={<><h1>Page not found</h1><p>Use the menu to go to a screen.</p></>} />
            </Routes>
            <footer className="app-foot">
              <Link to="/about/data">Data &amp; methods</Link>
            </footer>
          </main>
        </div>
      </div>
    </StatusProvider>
  );
}
