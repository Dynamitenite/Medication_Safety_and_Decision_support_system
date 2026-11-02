import { Fragment } from "react";
import type { ComponentStatus } from "../api";
import { StatusBadge } from "./Panel";

const gigabytes = (n: number) => `${(n / 1e9).toFixed(2)} GB`;

/** "xml_train" -> "XML train", "zip_files" -> "Zip files": sentence case. */
function fieldLabel(k: string): string {
  const words = k.replace(/_/g, " ");
  const text = words.charAt(0).toUpperCase() + words.slice(1);
  return text.replace(/^Xml\b/, "XML");
}

function fieldValue(k: string, v: string | number): string {
  if (k === "total_bytes" && typeof v === "number") return gigabytes(v);
  return typeof v === "number" ? v.toLocaleString("en-US") : v;
}

/** The DailyMed figures go on one plain line under the component's row. */
const FILE_KEYS = ["zip_files", "total_bytes", "files"];

function fileLine(c: ComponentStatus): string | null {
  const d = c.detail ?? {};
  if (!("zip_files" in d)) return null;
  return FILE_KEYS.filter((k) => k in d)
    .map((k) => `${k === "total_bytes" ? "Total size" : k === "files" ? "File" : fieldLabel(k)}: ${fieldValue(k, d[k])}`)
    .join(" · ");
}

function found(c: ComponentStatus, hasLine: boolean): string {
  if (c.status !== "ready") return c.reason ?? "";
  const entries = Object.entries(c.detail ?? {}).filter(([k]) => !(hasLine && FILE_KEYS.includes(k)));
  if (entries.length === 0) return hasLine ? "Label files are present." : "Ready.";
  return entries.map(([k, v]) => `${fieldLabel(k)}: ${fieldValue(k, v)}`).join(" · ");
}

/** One row per system component, exactly as /api/status reports it. */
export function StatusTable({ components }: { components: ComponentStatus[] }) {
  return (
    <div className="table-wrap">
      <table className="status-table">
        <thead>
          <tr>
            <th scope="col">Component</th>
            <th scope="col">Status</th>
            <th scope="col">What it found</th>
            <th scope="col">What is needed</th>
          </tr>
        </thead>
        <tbody>
          {components.map((c) => {
            const line = fileLine(c);
            return (
              <Fragment key={c.id}>
                <tr className={line ? "has-sub" : undefined}>
                  <th scope="row" data-label="Component">{c.label}</th>
                  <td data-label="Status"><StatusBadge status={c.status} /></td>
                  <td data-label="What it found">{found(c, !!line)}</td>
                  <td data-label="What is needed" className={c.fix ? undefined : "need-none"}>{c.fix || "Nothing."}</td>
                </tr>
                {line && (
                  <tr className="sub-row">
                    <td colSpan={4}>{line}</td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
