import { useState } from "react";
import { Link } from "react-router-dom";
import { Warning, X } from "@phosphor-icons/react";
import { api } from "../api";
import type { CheckerResponse, PairResult } from "../api";
import { ErrorBox, NotReadyBox } from "../components/Panel";
import { MedicineSearch } from "../components/MedicineSearch";
import type { Recent } from "../components/MedicineSearch";
import { Sticker } from "../components/Sticker";

const MIN = 2;
const MAX = 10;

type Chosen = { set_id: string; name: string; manufacturer: string | null };

type Tone = "critical" | "high" | "moderate" | "none";
const TONE_TEXT: Record<Tone, string> = {
  critical: "Critical",
  high: "High",
  moderate: "Moderate",
  none: "Not flagged by APPMS",
};

function pairTone(p: PairResult): Tone {
  return p.appms.status === "ready" && p.appms.severity ? p.appms.severity : "none";
}

function Highlight({ text, term }: { text: string; term: string }) {
  const i = text.toLowerCase().indexOf(term.toLowerCase());
  if (i < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, i)}
      <mark className="find-hit">{text.slice(i, i + term.length)}</mark>
      {text.slice(i + term.length)}
    </>
  );
}

function PairCard({ p }: { p: PairResult }) {
  const [open, setOpen] = useState(false);
  const tone = pairTone(p);
  const n = p.text_match.matches_total;
  const id = `pair-${p.a.set_id}-${p.b.set_id}`;
  return (
    <li className={`pair pair-${tone}`}>
      <button type="button" className="pair-head" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}>
        <span className="pair-names">
          {p.a.name} <span className="muted">+</span> {p.b.name}
        </span>
        <span className="pair-tags">
          <span className={`badge badge-sev sev-${tone}`}>{TONE_TEXT[tone]}</span>
          <Sticker>{n ? `${n} label text ${n === 1 ? "match" : "matches"}` : "no label text match"}</Sticker>
        </span>
      </button>
      <div id={id} className="pair-body" hidden={!open}>
        <section aria-label="APPMS rule lookup">
          <h3>APPMS rule lookup</h3>
          <p className="small muted">{p.appms.source_label}</p>
          {p.appms.status === "not_ready" ? (
            <NotReadyBox reason={p.appms.reason} fix={p.appms.fix} />
          ) : p.appms.severity ? (
            <p>
              <strong>{TONE_TEXT[tone]}.</strong> {p.appms.explanation}
            </p>
          ) : (
            <p>No rule matched, which is not proof of safety.</p>
          )}
        </section>
        <section aria-label="DailyMed text match">
          <h3>DailyMed text match</h3>
          <p className="small muted">{p.text_match.source_label}</p>
          {p.same_active_moiety && (
            <p className="small">
              <Warning size={14} aria-hidden="true" /> Both labels share an active moiety.
            </p>
          )}
          {n === 0 ? (
            <p>
              No sentence in either Drug Interactions section names the other medicine. This is not proof of safety.
            </p>
          ) : (
            <ul className="evidence">
              {p.text_match.matches.map((m, i) => (
                <li key={i}>
                  <blockquote>
                    <Highlight text={m.sentence} term={m.matched_term} />
                  </blockquote>
                  <p className="small muted">
                    From the label for <Link to={`/medicine/${m.in_label_set_id}`}>{m.in_label_name}</Link>, section “{m.section}”.
                    Names: {m.names_drug}.
                  </p>
                </li>
              ))}
            </ul>
          )}
          {n > p.text_match.matches.length && (
            <p className="small muted">Showing {p.text_match.matches.length} of {n} matching sentences.</p>
          )}
          {p.text_match.notes.map((t) => (
            <p key={t} className="small muted">
              {t}
            </p>
          ))}
        </section>
      </div>
    </li>
  );
}

type Result = { state: "idle" } | { state: "loading" } | { state: "error"; message: string } | { state: "ok"; data: CheckerResponse };

export function Checker() {
  const [text, setText] = useState("");
  const [chosen, setChosen] = useState<Chosen[]>([]);
  const [result, setResult] = useState<Result>({ state: "idle" });
  const [note, setNote] = useState("");

  const add = (s: Chosen | Recent) => {
    if (chosen.some((c) => c.set_id === s.set_id)) {
      setNote(`${s.name} is already in the list.`);
      return;
    }
    if (chosen.length >= MAX) {
      setNote(`The limit is ${MAX} medicines.`);
      return;
    }
    setNote(`${s.name} added.`);
    setChosen([...chosen, { set_id: s.set_id, name: s.name, manufacturer: s.manufacturer }]);
    setResult({ state: "idle" });
  };
  const remove = (id: string) => {
    const c = chosen.find((x) => x.set_id === id);
    setChosen(chosen.filter((x) => x.set_id !== id));
    setResult({ state: "idle" });
    setNote(c ? `${c.name} removed.` : "");
  };
  const run = () => {
    setResult({ state: "loading" });
    api
      .check(chosen.map((c) => c.set_id))
      .then((data) => setResult({ state: "ok", data }))
      .catch((e: unknown) => setResult({ state: "error", message: e instanceof Error ? e.message : String(e) }));
  };
  const pairCount = (chosen.length * (chosen.length - 1)) / 2;

  return (
    <>
      <h1>Interaction checker</h1>
      <p className="lead">
        Add {MIN} to {MAX} medicines. Each pair is looked up in two separate sources that are never merged into one score. Nothing is
        stored; the list is sent with the request only.
      </p>
      <section className="card" aria-labelledby="pick-h">
        <h2 id="pick-h">Medicines</h2>
        <MedicineSearch
          label="Add a medicine"
          placeholder="Search by brand, generic name or ingredient"
          value={text}
          onValueChange={setText}
          onSelect={add}
          clearOnSelect
          hint="Each pick is one specific DailyMed label (a product from one manufacturer)."
        />
        <ul className="chip-list" aria-label="Selected medicines">
          {chosen.map((c) => (
            <li key={c.set_id} className="chip">
              <span>
                {c.name}
                <span className="small muted"> · {c.manufacturer ?? "manufacturer not stated"}</span>
              </span>
              <button type="button" className="btn btn-plain btn-icon btn-sm" aria-label={`Remove ${c.name}`} onClick={() => remove(c.set_id)}>
                <X size={14} />
              </button>
            </li>
          ))}
        </ul>
        <div className="check-row">
          <button type="button" className="btn btn-primary" disabled={chosen.length < MIN || result.state === "loading"} onClick={run}>
            {result.state === "loading" ? "Checking…" : "Check"}
          </button>
          <span className="small muted">
            {chosen.length < MIN
              ? `Add at least ${MIN} medicines (${chosen.length} selected).`
              : `${chosen.length} medicines, ${pairCount} ${pairCount === 1 ? "pair" : "pairs"}.`}
          </span>
        </div>
        <span className="sr-only" role="status" aria-live="polite">
          {note}
        </span>
      </section>

      <section aria-labelledby="res-h" aria-busy={result.state === "loading"}>
        <h2 id="res-h">Results</h2>
        {result.state === "idle" && <p className="muted">Results appear here after you press Check.</p>}
        {result.state === "loading" && (
          <ul className="pair-list" aria-hidden="true">
            {Array.from({ length: Math.min(pairCount, 3) }, (_, i) => (
              <li key={i} className="pair">
                <div className="pair-head">
                  <div className="skeleton" style={{ width: "45%", margin: 0 }} />
                </div>
              </li>
            ))}
          </ul>
        )}
        {result.state === "error" && <ErrorBox message={result.message} onRetry={run} />}
        {result.state === "ok" && result.data.status === "not_ready" && (
          <NotReadyBox reason={result.data.reason} fix={result.data.fix} />
        )}
        {result.state === "ok" && result.data.status === "ready" && (
          <>
            {result.data.appms.status === "not_ready" && (
              <div className="notice" role="status">
                <div className="notice-title">
                  <Sticker>Not ready</Sticker>APPMS rule lookup ({result.data.appms.source_label})
                </div>
                <p>{result.data.appms.reason}</p>
                <p className="muted">
                  <strong>What is needed:</strong> {result.data.appms.fix}
                </p>
                <p className="small muted">So no pair is flagged by APPMS. Only the label text match below is available.</p>
              </div>
            )}
            <ul className="pair-list">
              {result.data.pairs.map((p) => (
                <PairCard key={p.a.set_id + p.b.set_id} p={p} />
              ))}
            </ul>
          </>
        )}
      </section>
    </>
  );
}
