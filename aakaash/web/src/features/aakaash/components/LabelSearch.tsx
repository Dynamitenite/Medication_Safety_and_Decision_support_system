import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import type { SearchLabelsResponse, SearchResult } from "../api";
import { Field } from "./Form";
import { ErrorBox, NotReadyBox } from "./Panel";
import { Sticker } from "./Sticker";

const escapeRx = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** The text with the query words (whole words, any case) wrapped in <mark>. The text itself is never changed. */
function Marked({ text, terms }: { text: string; terms: string[] }) {
  if (!terms.length) return <>{text}</>;
  const rx = new RegExp(`\\b(${terms.map(escapeRx).join("|")})\\b`, "gi");
  const parts = text.split(rx);
  return (
    <>
      {parts.map((p, i) =>
        i % 2 ? (
          <mark key={i} className="find-hit">
            {p}
          </mark>
        ) : (
          <span key={i}>{p}</span>
        ),
      )}
    </>
  );
}

const formLine = (r: SearchResult) =>
  r.form ? (r.route ? `${r.form} · ${r.route}` : r.form) : "form not stated";

/** One retrieved passage: section, cosine score, which label it is from, and its form and route. */
export function EvidenceCard({ r }: { r: SearchResult }) {
  return (
    <li className="evidence">
      <div className="evidence-head">
        <Sticker>{r.section_label}</Sticker>
        <span className="evidence-score" title="Cosine similarity between your words and this passage">
          score {r.score.toFixed(3)}
        </span>
        {r.is_default_label && <Sticker tone="good">Default label</Sticker>}
      </div>
      <p className="small muted">
        <Link to={`/label/${r.set_id}`}>{r.product}</Link> · {r.manufacturer ?? "manufacturer not stated"} ·{" "}
        <strong>Form:</strong> {formLine(r)}
      </p>
      {r.mismatch_note && (
        <p className="small">
          <Sticker wrap>Check form</Sticker> {r.mismatch_note}
        </p>
      )}
      {r.withheld ? (
        <p className="small">
          <Sticker wrap>Text not shown</Sticker> {r.withheld_note}
        </p>
      ) : (
        <p className="evidence-text">
          <Marked text={r.text} terms={r.match_terms} />
        </p>
      )}
    </li>
  );
}

/** "Search this label": cosine search over the US label text linked to this medicine. No generated answer. */
export function LabelSearch({ medicineId, medicineName }: { medicineId: string; medicineName: string }) {
  const [q, setQ] = useState("");
  const [scope, setScope] = useState<"default" | "all">("default");
  const [state, setState] = useState<"idle" | "loading" | "error">("idle");
  const [error, setError] = useState("");
  const [res, setRes] = useState<SearchLabelsResponse | null>(null);
  const [asked, setAsked] = useState("");

  async function run(e: FormEvent, nextScope = scope) {
    e.preventDefault();
    const query = q.trim();
    if (!query) return;
    setState("loading");
    try {
      setRes(await api.searchLabels({ query, medicine_id: medicineId, k: 5, scope: nextScope }));
      setAsked(query);
      setState("idle");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed.");
      setState("error");
    }
  }

  return (
    <section className="card" aria-labelledby="ls-h">
      <h2 id="ls-h">Search this label</h2>
      <p className="small muted">
        Search the label text (US FDA) linked to {medicineName}. Passages are ranked by similarity to your words; nothing is written for
        you.
      </p>
      <form onSubmit={run} className="ls-form" role="search">
        <Field label="Your question or words">
          <input type="search" value={q} maxLength={300} onChange={(e) => setQ(e.target.value)} placeholder="For example: bleeding, kidney, missed dose" />
        </Field>
        <button type="submit" className="btn btn-primary" disabled={!q.trim() || state === "loading"}>
          {state === "loading" ? "Searching…" : "Search"}
        </button>
      </form>
      <div className="seg" role="group" aria-label="Which labels to search">
        {(["default", "all"] as const).map((s) => (
          <button key={s} type="button" className="btn btn-secondary btn-sm" aria-pressed={scope === s}
            onClick={(e) => { setScope(s); if (res) void run(e, s); }}>
            {s === "default" ? "Default label only" : "All linked labels"}
          </button>
        ))}
      </div>
      <div aria-live="polite">
        {state === "error" && <ErrorBox message={error} />}
        {res?.status === "not_ready" && <NotReadyBox reason={res.reason} fix={res.fix} />}
        {res?.status === "ready" && (
          <>
            <p className="small muted">
              {res.results.length ? `Top ${res.results.length} passages for “${asked}”` : `No passage matched “${asked}”`} · searched{" "}
              {res.restricted_to} ({res.labels_searched} {res.labels_searched === 1 ? "label" : "labels"}) · {res.encoder_label} ·{" "}
              {res.elapsed_ms} ms
            </p>
            {res.results.length > 0 && <ul className="evidence-list">{res.results.map((r) => <EvidenceCard key={r.chunk_id} r={r} />)}</ul>}
            <p className="small muted">{res.note}</p>
          </>
        )}
      </div>
    </section>
  );
}
