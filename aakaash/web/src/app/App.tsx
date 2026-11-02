import { lazy, Suspense, useEffect, useRef, useState, type ReactNode } from "react";
import { Link, NavLink, Navigate, Route, Routes, useLocation, useNavigate, useParams } from "react-router-dom";
import { Gear, List, SignIn, SignOut, X } from "@phosphor-icons/react";
import { MENU_ICONS } from "../features/aakaash/pages/MenuIcons";
import { AuthProvider, RequireAuth, useAuth } from "../features/aakaash/auth/AuthContext";
import { Disclaimer } from "../features/aakaash/components/Disclaimer";
import { MENU, MODULE_COMPONENTS, SCREENS } from "../features/aakaash/registry";
import { StatusProvider } from "../features/aakaash/StatusContext";
import { ThemeToggle } from "./ThemeToggle";

/** Screens whose tables and charts use the full width; the others are text pages. */
const WIDE_PATHS = new Set(["/about/data", "/about/trace"]);
const ComingSoon = lazy(() => import("../features/aakaash/pages/ComingSoon").then(m => ({ default: m.ComingSoon })));
const Account = lazy(() => import("../features/aakaash/pages/Account").then(m => ({ default: m.Account })));
const AddMedicine = lazy(() => import("../features/aakaash/pages/AddMedicine").then(m => ({ default: m.AddMedicine })));
const Alternatives = lazy(() => import("../features/aakaash/pages/Alternatives").then(m => ({ default: m.Alternatives })));
const DataMethods = lazy(() => import("../features/aakaash/pages/DataMethods").then(m => ({ default: m.DataMethods })));
const History = lazy(() => import("../features/aakaash/pages/History").then(m => ({ default: m.History })));
const LabelPage = lazy(() => import("../features/aakaash/pages/LabelPage").then(m => ({ default: m.LabelPage })));
const Login = lazy(() => import("../features/aakaash/pages/Login").then(m => ({ default: m.Login })));
const MedicinePage = lazy(() => import("../features/aakaash/pages/MedicinePage").then(m => ({ default: m.MedicinePage })));
const Menu = lazy(() => import("../features/aakaash/pages/Menu").then(m => ({ default: m.Menu })));
const Profile = lazy(() => import("../features/aakaash/pages/Profile").then(m => ({ default: m.Profile })));
const Trace = lazy(() => import("../features/aakaash/pages/Trace").then(m => ({ default: m.Trace })));

function ModuleRoute() {
  const { id = "" } = useParams();
  const Custom = MODULE_COMPONENTS[id];
  return Custom ? <Custom /> : <ComingSoon id={id} />;
}

function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const auth = useAuth();
  const navigate = useNavigate();
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (open) closeRef.current?.focus();
  }, [open]);
  const link = ({ isActive }: { isActive: boolean }) => (isActive ? "nav-link nav-active active font-nav" : "nav-link font-nav");
  const plainLink = ({ isActive }: { isActive: boolean }) => (isActive ? "nav-link nav-active active" : "nav-link");
  async function logOut() {
    await auth.signOut();
    navigate("/login", { replace: true });
  }
  return (
    <aside className={open ? "sidebar open" : "sidebar"} id="navigation" aria-label="Navigation">
      <div className="sidebar-head">
        <div>
          <Link to="/" className="sidebar-title">Medication Safety Support</Link>
        </div>
        <button ref={closeRef} type="button" className="btn btn-plain btn-icon btn-sm mobile-only" aria-label="Close menu" onClick={onClose}>
          <X size={18} />
        </button>
      </div>
      <nav className="sidebar-nav" aria-label="Main">
        {auth.user ? (
          <ul>
            {MENU.map((m) => {
              const Glyph = MENU_ICONS[m.id];
              return (
                <li key={m.id}>
                  <NavLink to={m.path} className={link}>
                    <Glyph size={18} aria-hidden="true" />
                    {m.label}
                  </NavLink>
                </li>
              );
            })}
          </ul>
        ) : (
          <ul>
            <li>
              <NavLink to="/login" className={link}>
                <SignIn size={18} aria-hidden="true" />
                Sign in
              </NavLink>
            </li>
          </ul>
        )}
      </nav>
      <div className="sidebar-foot">
        {auth.user && (
          <div className="account-menu">
            <div className="account-email small muted" title={auth.user.email}>
              {auth.user.email}
            </div>
            <NavLink to="/account" className={plainLink}>
              <Gear size={18} aria-hidden="true" />
              Account settings
            </NavLink>
            <button type="button" className="nav-link nav-button" onClick={logOut}>
              <SignOut size={18} aria-hidden="true" />
              Log out
            </button>
          </div>
        )}
        <ThemeToggle />
      </div>
    </aside>
  );
}

const guard = (page: ReactNode) => <RequireAuth>{page}</RequireAuth>;

function Shell() {
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
          <main className={WIDE_PATHS.has(pathname) ? "content wide" : "content"} id="main" tabIndex={-1}>
            <Suspense fallback={<p className="muted" role="status">Loading page…</p>}>
            <Routes>
              <Route path="/" element={guard(<Menu />)} />
              <Route path="/profile" element={guard(<Profile />)} />
              <Route path="/history" element={guard(<History />)} />
              <Route path="/add" element={guard(<AddMedicine />)} />
              <Route path="/alternatives" element={guard(<Alternatives />)} />
              <Route path="/account" element={guard(<Account />)} />
              {SCREENS.map((s) => (
                <Route key={s.id} path={s.path} element={guard(<s.Component />)} />
              ))}
              <Route path="/about/data" element={<DataMethods />} />
              <Route path="/about/trace" element={<Trace />} />
              <Route path="/about" element={<Navigate to="/about/data" replace />} />
              <Route path="/dashboard" element={<Navigate to="/about/data" replace />} />
              <Route path="/trace" element={<Navigate to="/about/trace" replace />} />
              <Route path="/medicine/:id" element={guard(<MedicinePage />)} />
              <Route path="/label/:setId" element={guard(<LabelPage />)} />
              <Route path="/modules/:id" element={guard(<ModuleRoute />)} />
              <Route path="*" element={<><h1>Page not found</h1><p>Use the menu to go to a screen.</p></>} />
            </Routes>
            </Suspense>
          </main>
          <footer className="app-foot">
            <Disclaimer />
            <Link to="/about/data">Data &amp; methods</Link>
          </footer>
        </div>
      </div>
    </StatusProvider>
  );
}

export function App() {
  return (
    <AuthProvider>
      <Suspense fallback={<div className="login-wrap"><p role="status">Loading…</p></div>}><Routes>
        <Route path="/login" element={<Login />} />
        <Route path="*" element={<Shell />} />
      </Routes></Suspense>
    </AuthProvider>
  );
}
