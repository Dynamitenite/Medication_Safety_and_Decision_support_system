import { useEffect, useRef, type ReactNode } from "react";

/** A label with its control inside it, plus an optional hint. Text, number, date, select and textarea
 *  controls inside `.field` get the Cluster input look from styles.css. */
export function Field({ label, hint, children, wide }: { label: string; hint?: string; children: ReactNode; wide?: boolean }) {
  return (
    <label className={wide ? "field field-wide" : "field"}>
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="field-hint small muted">{hint}</span>}
    </label>
  );
}

export function FormError({ message }: { message?: string | null }) {
  return message ? (
    <div className="notice notice-error" role="alert">
      <p>{message}</p>
    </div>
  ) : null;
}

export function EmptyState({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="empty">
      <p className="empty-title">{title}</p>
      {hint && <p className="small muted">{hint}</p>}
      {action}
    </div>
  );
}

/** Native modal dialog: focus is trapped, Escape closes it, and Cancel is focused first. */
export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel,
  busy,
  error,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  children: ReactNode;
  confirmLabel: string;
  busy?: boolean;
  error?: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog ref={ref} className="dialog" aria-labelledby="dialog-title" onCancel={(e) => (e.preventDefault(), !busy && onCancel())}>
      <h2 id="dialog-title">{title}</h2>
      <div>{children}</div>
      <FormError message={error} />
      <div className="form-actions">
        <button type="button" className="btn btn-secondary" autoFocus onClick={onCancel} disabled={busy}>
          Cancel
        </button>
        <button type="button" className="btn btn-primary" onClick={onConfirm} disabled={busy}>
          {busy ? "Working…" : confirmLabel}
        </button>
      </div>
    </dialog>
  );
}
