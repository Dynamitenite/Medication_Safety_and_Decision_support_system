import { useState, type FormEvent } from "react";
import { Navigate, useSearchParams } from "react-router-dom";
import { ThemeToggle } from "../../../app/ThemeToggle";
import { ClockCounterClockwise, MagnifyingGlass, Scales } from "@phosphor-icons/react";
import { errorText } from "../api";
import { useAuth } from "../auth/AuthContext";
import { Field, FormError } from "../components/Form";

/** Only same-site paths are followed after sign-in. */
const safeNext = (n: string | null) => (n && n.startsWith("/") && !n.startsWith("//") && !n.startsWith("/login") ? n : "/");

/** One form: a known email signs in, a new email creates the account. */
export function Login() {
  const auth = useAuth();
  const [params] = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const next = safeNext(params.get("next"));

  if (auth.state === "ready" && auth.user) return <Navigate to={next} replace />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await auth.signIn(email.trim(), password);
    } catch (err) {
      setError(errorText(err));
      setPassword("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <main className="login-card card" id="main">
        <h1>Medication Safety Support</h1>
        <p className="lead">A place to review your medicines and health history.</p>
        <ul className="login-points">
          <li><Scales size={18} aria-hidden="true" />Check a new medicine against your current ones</li>
          <li><ClockCounterClockwise size={18} aria-hidden="true" />Keep your medical history</li>
          <li><MagnifyingGlass size={18} aria-hidden="true" />Find lower-priced alternatives</li>
        </ul>
        <form onSubmit={submit} noValidate>
          <div className="form-stack">
            <Field label="Email">
              <input type="email" name="email" autoComplete="email" inputMode="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
            </Field>
            <Field label="Password" hint="At least 8 characters. A new email address creates an account.">
              <input
                type="password"
                name="password"
                autoComplete="current-password"
                required
                minLength={8}
                maxLength={128}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </Field>
          </div>
          <FormError message={error} />
          <div className="form-actions">
            <button type="submit" className="btn btn-primary" disabled={busy || !email || !password}>
              {busy ? "Working…" : "Continue"}
            </button>
          </div>
        </form>
        <p className="small muted">Your information is stored in this app's database and can be deleted from your account settings.</p>
        <div className="login-foot">
          <ThemeToggle />
        </div>
      </main>
    </div>
  );
}
