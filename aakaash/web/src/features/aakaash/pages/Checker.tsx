import { useState } from "react";
import { Link } from "react-router-dom";
import { Warning, X } from "@phosphor-icons/react";
import { api } from "../api";
import type { CheckerMedicine, CheckerResponse, PairResult } from "../api";
import { Disclaimer } from "../components/Disclaimer";
import { ErrorBox, NotReadyBox } from "../components/Panel";
import { PatientPicker } from "../components/PatientPicker";
import type { PickedPatient } from "../components/PatientPicker";
import { MedicineSearch } from "../components/MedicineSearch";
import type { Recent } from "../components/MedicineSearch";
import { InteractionType } from "../components/InteractionType";
import { Sticker } from "../components/Sticker";

const MIN = 2;
const MAX = 10;

/** A chip. A brand comes from the catalogue (`id`); a sample patient's medicine is a generic name,
 *  checked as that one ingredient. */
type Chosen = { key: string; id?: string; name: string; manufacturer?: string | null; detail: string };

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

const ingList = (m: CheckerMedicine) => m.ingredients.map((g) => g.name).join(" + ");

function MedName({ m }: { m: CheckerMedicine }) {
  return (
    <span>
      {m.catalogue_id ? <Link to={`/medicine/${m.catalogue_id}`} onClick={(e) => e.stopPropagation()}>{m.name}</Link> : m.name}
      <span className="chip-ings">{m.kind === "generic" ? "generic name" : ingList(m)}</span>
    </span>
  );
}

function PairCard({ p }: { p: PairResult }) {
  const [open, setOpen] = useState(false);
  const tone = pairTone(p);
  const n = p.text_match.matches_total;
  const id = `pair-${p.a.key}-${p.b.key}`.replace(/[^A-Za-z0-9-]/g, "-");
  return (
    <li className={`pair pair-${tone}`}>
      <button type="button" className="pair-head" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}>
        <span className="pair-names">
          {p.a.name} <span className="muted">+</span> {p.b.name}
          <span className="chip-ings">
            {p.a.kind === "generic" ? "generic name" : ingList(p.a)} · {p.b.kind === "generic" ? "generic name" : ingList(p.b)}
          </span>
        </span>
        <span className="pair-tags">
          <span className={`badge badge-sev sev-${tone}`}>{TONE_TEXT[tone]}</span>
          <Sticker>{n ? `${n} label text ${n === 1 ? "mention" : "mentions"}` : "no label text mention"}</Sticker>
          {p.shared_ingredients.length > 0 && <Sticker tone="danger">Same ingredient</Sticker>}
        </span>
      </button>
      <div id={id} className="pair-body" hidden={!open}>
        <p className="small muted">
          <MedName m={p.a} /> <MedName m={p.b} />
        </p>
        {p.shared_ingredients.length > 0 && (
          <p className="small">
            <Warning size={14} aria-hidden="true" /> Both contain {p.shared_ingredients.join(", ")}. Taking both may double the dose of
            that ingredient.
          </p>
        )}
        {p.notes.map((t) => (
          <p key={t} className="small">
            <Sticker wrap>Check</Sticker> {t}
          </p>
        ))}
        <section aria-label="Interaction rules">
          <h3>Interaction rules</h3>
          {p.appms.status === "not_ready" ? (
            <NotReadyBox reason={p.appms.reason} fix={p.appms.fix} />
          ) : p.appms.hits.length ? (
            <ul className="evidence">
              {p.appms.hits.map((h, i) => (
                <li key={i}>
                  <p>
                    <strong>{TONE_TEXT[h.severity]}.</strong> {h.explanation}
                  </p>
                  <p className="small muted">
                    Matched ingredients: {h.a_ingredient} and {h.b_ingredient}.
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <p>No known interaction found in our rules. This does not mean the combination is safe.</p>
          )}
        </section>
        <section aria-label="Label text">
          <h3>Label text (US FDA)</h3>
          <p className="small muted">{p.text_match.source_label}</p>
          {n === 0 ? (
            <p>No sentence in these labels' Drug Interactions sections names the other medicine. This does not mean the combination is safe.</p>
          ) : (
            <ul className="evidence">
              {p.text_match.matches.map((m, i) => (
                <li key={i}>
                  <blockquote>
                    <Highlight text={m.sentence} term={m.matched_term} />
                  </blockquote>
                  {m.source_term && <InteractionType sentence={m.sentence} drug1={m.source_term} drug2={m.matched_term} active={open} />}
                  <p className="small muted">
                    From the US label for <strong>{m.source_ingredient}</strong> (
                    <Link to={`/label/${m.in_label_set_id}`}>{m.in_label_name}</Link>), section “{m.section}”. Names{" "}
                    <strong>{m.named_ingredient}</strong>, in {m.names_drug}.
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
        {p.secondary.hits.length > 0 && (
          <section aria-label="Interactions listed with the product">
            <h3>Interactions listed with the product</h3>
            <p className="small muted">{p.secondary.source_label}</p>
            <ul className="evidence">
              {p.secondary.hits.map((h, i) => (
                <li key={i}>
                  {h.in_product} lists <strong>{h.drug}</strong>
                  {h.effect ? ` (listed effect: ${h.effect})` : ""}, which matches {h.matches_ingredient}.
                </li>
              ))}
            </ul>
          </section>
        )}
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
    if (chosen.some((c) => c.key === s.id)) {
      setNote(`${s.name} is already in the list.`);
      return;
    }
    if (chosen.length >= MAX) {
      setNote(`The limit is ${MAX} medicines.`);
      return;
    }
    setNote(`${s.name} added.`);
    setChosen([...chosen, { key: s.id, id: s.id, name: s.name, manufacturer: s.manufacturer, detail: s.composition }]);
    setResult({ state: "idle" });
  };
  const remove = (key: string) => {
    const c = chosen.find((x) => x.key === key);
    setChosen(chosen.filter((x) => x.key !== key));
    setResult({ state: "idle" });
    setNote(c ? `${c.name} removed.` : "");
  };
  // Replaces the list with the patient's medicines. Each is a generic name, checked as that ingredient.
  const loadPatient = ({ patient, medications }: PickedPatient) => {
    const seen = new Set<string>();
    const list: Chosen[] = [];
    for (const m of medications) {
      const k = `name:${m.drug_name.toLowerCase()}`;
      if (seen.has(k)) continue;
      seen.add(k);
      list.push({ key: k, name: m.drug_name, detail: `generic name · ${m.strength}` });
    }
    setChosen(list.slice(0, MAX));
    setResult({ state: "idle" });
    setNote(`Loaded ${list.length} medicines from patient ${patient.patient_id}.`);
  };
  const run = () => {
    setResult({ state: "loading" });
    api
      .check(chosen.flatMap((c) => (c.id ? [c.id] : [])), chosen.flatMap((c) => (c.id ? [] : [c.name])))
      .then((data) => setResult({ state: "ok", data }))
      .catch((e: unknown) => setResult({ state: "error", message: e instanceof Error ? e.message : String(e) }));
  };
  const pairCount = (chosen.length * (chosen.length - 1)) / 2;

  return (
    <>
      <h1>Interaction checker</h1>
      <p className="lead">
        Add {MIN} to {MAX} medicines. Each medicine is checked by its ingredients: every pair is looked up in our interaction rules and
        in the US label text for each ingredient. The results are shown separately. The checker does not save the medicines you enter.
      </p>
      <section className="card" aria-labelledby="pick-h">
        <h2 id="pick-h">Medicines</h2>
        <MedicineSearch
          label="Add a medicine"
          placeholder="Search by brand or ingredient"
          value={text}
          onValueChange={setText}
          onSelect={add}
          clearOnSelect
          hint="Each pick is one brand. Its ingredients are what is checked."
        />
        <ul className="chip-list" aria-label="Selected medicines">
          {chosen.map((c) => (
            <li key={c.key} className="chip">
              <span>
                {c.name}
                {c.id && <span className="small muted"> · {c.manufacturer ?? "manufacturer not stated"}</span>}
                <span className="chip-ings">{c.detail}</span>
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
        <p className="panel-hint">
          Fills the list above with that patient's medicines (generic names). It replaces what is there now; you can then add brands.
        </p>
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
                  <Sticker>Unavailable</Sticker>
                  {result.data.appms.source_label}
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
                <PairCard key={p.a.key + "|" + p.b.key} p={p} />
              ))}
            </ul>
            <Disclaimer />
          </>
        )}
      </section>
    </>
  );
}
