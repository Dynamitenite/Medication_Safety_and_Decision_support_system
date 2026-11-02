import type { ReactNode } from "react";
import type { Readiness } from "../api";
import type { Query } from "../useApi";
import { Sticker } from "./Sticker";

export function NotReadyBox({ reason, fix, title }: { reason?: string | null; fix?: string | null; title?: string }) {
  return (
    <div className="notice" role="status">
      <div className="notice-title">
        <Sticker>Unavailable</Sticker>
        {title}
      </div>
      {reason && <p>{reason}</p>}
      {fix && (
        <p className="muted">
          <strong>What is needed:</strong> {fix}
        </p>
      )}
    </div>
  );
}

export function LoadingBox({ what }: { what: string }) {
  return (
    <div className="notice" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" /> Loading {what}…
    </div>
  );
}

export function ErrorBox({ message, onRetry }: { message?: string; onRetry?: () => void }) {
  return (
    <div className="notice notice-error" role="alert">
      <div className="notice-title">
        <Sticker tone="danger">Error</Sticker>
        The request failed.
      </div>
      <p>{message}</p>
      {onRetry && (
        <button type="button" className="btn btn-secondary btn-sm" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

/** A titled section whose body handles loading, error and not_ready before showing real data. */
export function Panel<T extends Readiness>({
  title,
  hint,
  query,
  children,
  id,
}: {
  title: string;
  hint?: ReactNode;
  query: Query<T>;
  children: (data: T) => ReactNode;
  id?: string;
}) {
  let body: ReactNode;
  if (query.state === "loading" && !query.data) body = <LoadingBox what={title.toLowerCase()} />;
  else if (query.state === "error") body = <ErrorBox message={query.message} onRetry={query.reload} />;
  else if (query.data && query.data.status === "not_ready")
    body = <NotReadyBox reason={query.data.reason} fix={query.data.fix} />;
  else if (query.data) body = children(query.data);
  return (
    <section className="card" aria-labelledby={id ? `${id}-h` : undefined} id={id}>
      <h2 id={id ? `${id}-h` : undefined}>{title}</h2>
      {hint && <p className="panel-hint">{hint}</p>}
      {body}
    </section>
  );
}

export function StatusBadge({ status }: { status: "ready" | "not_ready" | "coming_soon" }) {
  if (status === "ready") return <Sticker tone="good">Ready</Sticker>;
  return <Sticker>{status === "not_ready" ? "Not ready" : "Coming soon"}</Sticker>;
}

export function KeyValues({ items }: { items: [string, ReactNode][] }) {
  return (
    <dl className="kv">
      {items.map(([k, v]) => (
        <div key={k}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}

export const fmt = (n: number | null | undefined) => (n == null ? "–" : n.toLocaleString("en-US"));
