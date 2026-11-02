import { useState } from "react";
import { Link } from "react-router-dom";
import { Warning, X } from "@phosphor-icons/react";
import { api } from "../api";
import type { CheckerResponse, NamePairResult, PairResult } from "../api";
import { Disclaimer } from "../components/Disclaimer";
import { ErrorBox, NotReadyBox } from "../components/Panel";
import { PatientPicker } from "../components/PatientPicker";
import type { PickedPatient } from "../components/PatientPicker";
import { MedicineSearch } from "../components/MedicineSearch";
import type { Recent } from "../components/MedicineSearch";
import { Sticker } from "../components/Sticker";

const MIN = 2;
const MAX = 10;

/** A chip. `set_id` is absent for a medicine with no label in our database: it is still looked up in the
 *  interaction rules, by name. */
type Chosen = { key: string; set_id?: string; name: string; manufacturer?: string | null };

type Tone = "critical" | "high" | "moderate" | "none";
const TONE_TEXT: Record<Tone, string> = {
  critical: "Critical",
  high: "High",
  moderate: "Moderate",
  none: "No known interaction",
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
          <Sticker>{n ? `${n} label text ${n === 1 ? "mention" : "mentions"}` : "no label text mention"}</Sticker>
        </span>
      </button>
      <div id={id} className="pair-body" hidden={!open}>
        <section aria-label="Interaction rules">
          <h3>Interaction rules</h3>
          <p className="small muted">{p.appms.source_label}</p>
          {p.appms.status === "not_ready" ? (
            <NotReadyBox reason={p.appms.reason} fix={p.appms.fix} />
          ) : p.appms.severity ? (
            <p>
              <strong>{TONE_TEXT[tone]}.</strong> {p.appms.explanation}
            </p>
          ) : (
            <p>No known interaction found in our rules. This does not mean the combination is safe.</p>
          )}
        </section>
        <section aria-label="Label text">
          <h3>Label text</h3>
          <p className="small muted">{p.text_match.source_label}</p>
          {p.same_active_moiety && (
            <p className="small">
              <Warning size={14} aria-hidden="true" /> Both labels share an active moiety.
            </p>
          )}
          {n === 0 ? (
            <p>
              No sentence in either label's Drug Interactions section names the other medicine. This does not mean the combination is safe.
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
        <Disclaimer />
      </div>
    </li>
  );
}

function NamePairCard({ p }: { p: NamePairResult }) {
  const [open, setOpen] = useState(false);
  const tone: Tone = p.appms.status === "ready" && p.appms.severity ? p.appms.severity : "none";
  const id = `name-pair-${p.a}-${p.b}`.replace(/\s+/g, "-");
  const missing = [!p.a_in_database && p.a, !p.b_in_database && p.b].filter(Boolean).join(" and ");
  return (
    <li className={`pair pair-${tone}`}>
      <button type="button" className="pair-head" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}>
        <span className="pair-names">
          {p.a} <span className="muted">+</span> {p.b}
        </span>
        <span className="pair-tags">
          <span className={`badge badge-sev sev-${tone}`}>{TONE_TEXT[tone]}</span>
          <Sticker>interaction rules only</Sticker>
        </span>
      </button>
      <div id={id} className="pair-body" hidden={!open}>
        <section aria-label="Interaction rules">
          <h3>Interaction rules</h3>
          {p.appms.status === "not_ready" ? (
            <NotReadyBox reason={p.appms.reason} fix={p.appms.fix} />
          ) : p.appms.severity ? (
            <p>
              <strong>{TONE_TEXT[tone]}.</strong> {p.appms.explanation}
            </p>
          ) : (
            <p>No known interaction found in our rules. This does not mean the combination is safe.</p>
          )}
        </section>
        <p className="small muted">
          {missing} {missing.includes(" and ") ? "are" : "is"} not in our database, so there is no label text to check for this pair.
        </p>
        <Disclaimer />
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

  const add = (s: Recent) => {
    if (chosen.some((c) => c.key === s.set_id)) {
      setNote(`${s.name} is already in the list.`);
      return;
    }
    if (chosen.length >= MAX) {
      setNote(`The limit is ${MAX} medicines.`);
      return;
    }
    setNote(`${s.name} added.`);
    setChosen([...chosen, { key: s.set_id, set_id: s.set_id, name: s.name, manufacturer: s.manufacturer }]);
    setResult({ state: "idle" });
  };
  const remove = (key: string) => {
    const c = chosen.find((x) => x.key === key);
    setChosen(chosen.filter((x) => x.key !== key));
    setResult({ state: "idle" });
    setNote(c ? `${c.name} removed.` : "");
  };
  // Replaces the list with the patient's medicines. A medicine with no label stays as a name-only chip.
  const loadPatient = ({ patient, medications }: PickedPatient) => {
    const seen = new Set<string>();
    const list: Chosen[] = [];
    for (const m of medications) {
      const k = m.label?.set_id ?? `name:${m.drug_name.toLowerCase()}`;
      if (seen.has(k)) continue;
      seen.add(k);
      list.push(m.label
        ? { key: k, set_id: m.label.set_id, name: m.label.name, manufacturer: m.label.manufacturer }
        : { key: k, name: m.drug_name });
    }
    setChosen(list.slice(0, MAX));
    setResult({ state: "idle" });
    const missing = list.filter((c) => !c.set_id).length;
    setNote(`Loaded ${list.length} medicines from patient ${patient.patient_id}.${missing ? ` ${missing} not in our database.` : ""}`);
  };
  const run = () => {
    setResult({ state: "loading" });
    api
      .check(chosen.flatMap((c) => (c.set_id ? [c.set_id] : [])), chosen.flatMap((c) => (c.set_id ? [] : [c.name])))
      .then((data) => setResult({ state: "ok", data }))
      .catch((e: unknown) => setResult({ state: "error", message: e instanceof Error ? e.message : String(e) }));
  };
  const pairCount = (chosen.length * (chosen.length - 1)) / 2;

  return (
    <>
      <h1>Interaction checker</h1>
      <p className="lead">
        Add {MIN} to {MAX} medicines. Each pair is checked against our interaction rules and against the label text. The two results
        are shown separately. Nothing is stored.
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
          hint="Each pick is one specific label (a product from one manufacturer)."
        />
        <ul className="chip-list" aria-label="Selected medicines">
          {chosen.map((c) => (
            <li key={c.key} className="chip">
              <span>
                {c.name}
                {c.set_id ? (
                  <span className="small muted"> · {c.manufacturer ?? "manufacturer not stated"}</span>
                ) : (
                  <span className="chip-flag small"> · not in our database</span>
                )}
              </span>
              <button type="button" className="btn btn-plain btn-icon btn-sm" aria-label={`Remove ${c.name}`} onClick={() => remove(c.key)}>
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

      <section className="card" aria-labelledby="patient-h">
        <h2 id="patient-h">Load a sample patient</h2>
        <p className="panel-hint">Fills the list above with that patient's medicines. It replaces what is there now.</p>
        <PatientPicker label="Find a sample patient" showCard={false} onPick={loadPatient} />
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
                  <Sticker>Unavailable</Sticker>{result.data.appms.source_label}
                </div>
                <p>{result.data.appms.reason}</p>
                <p className="muted">
                  <strong>What is needed:</strong> {result.data.appms.fix}
                </p>
                <p className="small muted">So no pair is flagged by a rule. Only the label text is available.</p>
              </div>
            )}
            <ul className="pair-list">
              {result.data.pairs.map((p) => (
                <PairCard key={p.a.set_id + p.b.set_id} p={p} />
              ))}
              {result.data.name_pairs.map((p) => (
                <NamePairCard key={p.a + "|" + p.b} p={p} />
              ))}
            </ul>
            <Disclaimer />
          </>
        )}
      </section>
    </>
  );
}
