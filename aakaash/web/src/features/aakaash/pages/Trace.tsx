import { useMemo, useState } from "react";
import { api, type TraceRow } from "../api";
import { Panel } from "../components/Panel";
import { Sticker, type StickerTone } from "../components/Sticker";
import { useApi } from "../useApi";

const CATEGORY_LABEL: Record<TraceRow["category"], string> = {
  from_papers: "FROM PAPERS",
  from_baseline_review: "FROM BASELINE REVIEW (ICMLAS 2025)",
  not_in_papers: "NOT IN PAPERS",
  unclassified: "Unclassified",
};
const CATEGORY_TONE: Record<TraceRow["category"], StickerTone> = {
  from_papers: "neutral",
  from_baseline_review: "neutral",
  not_in_papers: "neutral",
  unclassified: "danger",
};
const STATUS_TONE: Record<TraceRow["status_kind"], StickerTone> = {
  untested: "neutral",
  ran: "neutral",
  verified: "good",
  unknown: "danger",
};
const STATUS_LABEL: Record<TraceRow["status_kind"], string> = {
  untested: "UNTESTED",
  ran: "RAN",
  verified: "VERIFIED",
  unknown: "Unknown",
};

export function Trace() {
  const q = useApi(api.trace);
  const [cat, setCat] = useState<string>("all");
  const [st, setSt] = useState<string>("all");
  const [text, setText] = useState("");
  const rows = useMemo(() => {
    const t = text.trim().toLowerCase();
    return (q.data?.rows ?? []).filter(
      (r) =>
        (cat === "all" || r.category === cat) &&
        (st === "all" || r.status_kind === st) &&
        (!t || [r.component, r.file, r.source, r.note, r.status ?? ""].join(" ").toLowerCase().includes(t)),
    );
  }, [q.data, cat, st, text]);

  return (
    <>
      <h1>Trace</h1>
      <p className="lead">
        What each component rests on: taken <strong>from papers</strong>, from the <strong>baseline review</strong>, or{" "}
        <strong>not in papers</strong> (our own choice), and whether it has been run or checked. This is{" "}
        <code>PAPER_TRACE.md</code>, read live from the repository.
      </p>
      <Panel id="trace" title="Components" query={q}>
        {(d) => (
          <>
            <div className="chips" role="group" aria-label="Summary">
              {Object.entries(d.counts_by_category).map(([k, v]) => (
                <Sticker key={k} tone={CATEGORY_TONE[k as TraceRow["category"]]}>
                  {CATEGORY_LABEL[k as TraceRow["category"]]}: {v}
                </Sticker>
              ))}
              {Object.entries(d.counts_by_status).map(([k, v]) => (
                <Sticker key={k} tone={STATUS_TONE[k as TraceRow["status_kind"]]}>
                  {STATUS_LABEL[k as TraceRow["status_kind"]]}: {v}
                </Sticker>
              ))}
            </div>
            {d.malformed_rows.length > 0 && (
              <div className="notice">
                {d.malformed_rows.length} table row(s) in PAPER_TRACE.md did not fit the expected five columns and are not shown.
              </div>
            )}
            <div className="filters">
              <label>
                Source{" "}
                <select value={cat} onChange={(e) => setCat(e.target.value)}>
                  <option value="all">All</option>
                  {Object.entries(CATEGORY_LABEL).map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
                </select>
              </label>
              <label>
                Status{" "}
                <select value={st} onChange={(e) => setSt(e.target.value)}>
                  <option value="all">All</option>
                  {Object.entries(STATUS_LABEL).map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
                </select>
              </label>
              <label>
                Search <input type="search" value={text} onChange={(e) => setText(e.target.value)} placeholder="component, file, note…" />
              </label>
              <span className="muted small">{rows.length} of {d.rows.length} rows</span>
            </div>
            <div className="table-wrap">
              <table className="trace-table">
                <thead>
                  <tr>
                    <th scope="col">Component</th>
                    <th scope="col">Source</th>
                    <th scope="col">Note</th>
                    <th scope="col">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={i}>
                      <th scope="row">
                        {r.component}
                        <div className="small muted"><code>{r.file}</code></div>
                      </th>
                      <td>
                        <Sticker tone={CATEGORY_TONE[r.category]}>{CATEGORY_LABEL[r.category]}</Sticker>
                        <div className="small">{r.source}</div>
                      </td>
                      <td className="small">{r.note || "–"}</td>
                      <td>
                        <Sticker tone={STATUS_TONE[r.status_kind]}>{STATUS_LABEL[r.status_kind]}</Sticker>
                        {r.status && <div className="small muted">{r.status}</div>}
                      </td>
                    </tr>
                  ))}
                  {rows.length === 0 && (
                    <tr><td colSpan={4} className="muted">No rows match the filters.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
            {d.preamble.length > 0 && (
              <ul className="small muted">
                {d.preamble.map((l) => <li key={l}>{l}</li>)}
              </ul>
            )}
          </>
        )}
      </Panel>
    </>
  );
}
