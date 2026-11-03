import type { ReactNode } from "react";

/** A closed-by-default "Show details" block: native details/summary, so Enter and Space toggle it. */
export function Disclosure({ title, children, className = "", open = false, onToggle }: { title: ReactNode; children: ReactNode; className?: string; open?: boolean; onToggle?: (open: boolean) => void }) {
  return (
    <details className={`disclosure ${className}`.trim()} open={open || undefined} onToggle={onToggle ? (e) => onToggle((e.currentTarget as HTMLDetailsElement).open) : undefined}>
      <summary>{title}</summary>
      <div className="disclosure-body">{children}</div>
    </details>
  );
}
