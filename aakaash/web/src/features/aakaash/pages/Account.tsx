import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, errorText } from "../api";
import { useAuth } from "../auth/AuthContext";
import { ConfirmDialog } from "../components/Form";
import { KeyValues } from "../components/Panel";
import { fmtDate } from "../format";

export function Account() {
  const auth = useAuth();
  const navigate = useNavigate();
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function remove() {
    setBusy(true);
    setError(null);
    try {
      await api.deleteAccount();
      auth.clear();
      navigate("/login", { replace: true });
    } catch (e) {
      setError(errorText(e));
      setBusy(false);
    }
  }

  return (
    <>
      <h1>Account settings</h1>
      <section className="card" aria-label="Account">
        <h2>Account</h2>
        <KeyValues items={[["Email", auth.user?.email ?? ""], ["Created", fmtDate(auth.user?.created_at) || "–"]]} />
        <div className="form-actions start">
          <button type="button" className="btn btn-secondary" onClick={() => auth.signOut()}>
            Log out
          </button>
        </div>
      </section>
      <section className="card" aria-label="Delete my data">
        <h2>Delete my data</h2>
        <p>
          Your information is stored in this app's database. Deleting your account removes your profile, allergies, conditions and
          medicines, and signs you out. This cannot be undone.
        </p>
        <div className="form-actions start">
          <button type="button" className="btn btn-primary" onClick={() => setAsking(true)}>
            Delete my data and account
          </button>
        </div>
      </section>
      <ConfirmDialog
        open={asking}
        title="Delete your account?"
        confirmLabel="Delete everything"
        busy={busy}
        error={error}
        onConfirm={remove}
        onCancel={() => (setAsking(false), setError(null))}
      >
        <p>Everything stored for {auth.user?.email} will be deleted now, and you will be signed out.</p>
      </ConfirmDialog>
    </>
  );
}
