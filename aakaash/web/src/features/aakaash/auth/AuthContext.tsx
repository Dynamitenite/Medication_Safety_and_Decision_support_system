import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { api, ApiError, errorText, SIGNED_OUT_EVENT, type LoginResponse, type MeResponse } from "../api";
import { ErrorBox } from "../components/Panel";
import { Skeleton } from "../components/LabelTabs";

type Auth = {
  /** loading until /api/auth/me answers; then the signed-in person or null */
  state: "loading" | "error" | "ready";
  user: MeResponse | null;
  message?: string;
  retry: () => void;
  signIn: (email: string, password: string) => Promise<LoginResponse>;
  signOut: () => Promise<void>;
  /** Forget the session locally (after the account is deleted, or when the server says it ended). */
  clear: () => void;
};

const Ctx = createContext<Auth | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<Auth["state"]>("loading");
  const [user, setUser] = useState<MeResponse | null>(null);
  const [message, setMessage] = useState<string>();
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let alive = true;
    setState("loading");
    api
      .me()
      .then((me) => alive && (setUser(me), setState("ready")))
      .catch((e: unknown) => {
        if (!alive) return;
        if (e instanceof ApiError && e.status === 401) {
          setUser(null);
          setState("ready");
        } else {
          setMessage(errorText(e));
          setState("error");
        }
      });
    return () => {
      alive = false;
    };
  }, [tick]);

  const clear = useCallback(() => setUser(null), []);
  useEffect(() => {
    window.addEventListener(SIGNED_OUT_EVENT, clear);
    return () => window.removeEventListener(SIGNED_OUT_EVENT, clear);
  }, [clear]);

  const value = useMemo<Auth>(
    () => ({
      state,
      user,
      message,
      retry: () => setTick((n) => n + 1),
      signIn: async (email, password) => {
        const res = await api.login(email, password);
        setUser(await api.me());
        setState("ready");
        return res;
      },
      signOut: async () => {
        try {
          await api.logout();
        } finally {
          setUser(null);
        }
      },
      clear,
    }),
    [state, user, message, clear],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): Auth {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth must be used inside AuthProvider");
  return v;
}

/** Only signed-in people see the children; everyone else goes to /login and comes back afterwards. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const loc = useLocation();
  if (auth.state === "loading") {
    return (
      <div aria-busy="true" aria-label="Loading">
        <div className="skeleton skeleton-title" />
        <Skeleton lines={4} />
      </div>
    );
  }
  if (auth.state === "error") return <ErrorBox message={auth.message} onRetry={auth.retry} />;
  if (!auth.user) return <Navigate to={`/login?next=${encodeURIComponent(loc.pathname + loc.search)}`} replace />;
  return <>{children}</>;
}
