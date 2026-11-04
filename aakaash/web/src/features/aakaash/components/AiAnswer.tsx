import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api, errorText } from "../api";
import type { AnswerSource, AnswerStatusResponse, AskResponse, ExplainFindingRequest, ExplainFindingResponse, SimplifyResponse } from "../api";
import { createStatusCache } from "./answerStatusCache";
import { AltRow } from "./AlternativesView";
import { Disclaimer } from "./Disclaimer";
import { Field } from "./Form";
import { cachedPrediction } from "./InteractionType";
import { ErrorBox, NotReadyBox } from "./Panel";
import { Sticker } from "./Sticker";

/** One shared status request. While it is unknown or not ready, no generated part is shown; a not_ready answer is re-asked after a short wait. */
const loadStatus = createStatusCache(() => api.answerStatus());
export function useAnswerStatus(): AnswerStatusResponse | null {
  const [s, setS] = useState<AnswerStatusResponse | null>(null);
  useEffect(() => {
    let alive = true;
    loadStatus().then((r) => alive && setS(r), () => {});
    return () => {
      alive = false;
    };
  }, []);
  return s;
}

/** The mark on everything the model wrote, with its sources named next to it. */
function AiMark({ s, children }: { s?: { provider?: string | null; model?: string | null }; children?: ReactNode }) {
  return (
    <p className="small ai-mark">
      <Sticker>AI-written from label text</Sticker>
      {s?.provider && <span className="muted"> {s.provider} · {s.model}</span>}
      {children && <span>{children}</span>}
    </p>
  );
}

type Run<T> = { state: "idle" } | { state: "loading" } | { state: "error"; message: string } | { state: "ok"; data: T };

function Outcome<T extends { status: "ready" | "not_ready"; reason?: string | null; fix?: string | null; retry_after?: number | null }>({
  run,
  children,
}: {
  run: Run<T>;
  children: (d: T) => ReactNode;
}) {
  return (
    <div aria-live="polite" aria-busy={run.state === "loading"}>
      {run.state === "loading" && (
        <p className="small muted" role="status">
          <span className="spinner" aria-hidden="true" /> Writing from the label text…
        </p>
      )}
      {run.state === "error" && <ErrorBox message={run.message} />}
      {run.state === "ok" && run.data.status === "not_ready" && <NotReadyBox reason={run.data.reason} fix={run.data.fix} title="AI answer" />}
      {run.state === "ok" && run.data.status === "ready" && children(run.data)}
    </div>
  );
}

async function exec<T>(set: (r: Run<T>) => void, call: () => Promise<T>) {
  set({ state: "loading" });
  try {
    set({ state: "ok", data: await call() });
  } catch (e) {
    set({ state: "error", message: errorText(e) });
  }
}

// ---- Ask about this medicine ---------------------------------------------------------------------
const CITE = /\[([^\[\]]+)\]/g;

function AnswerText({ r, open, onOpen }: { r: AskResponse; open: string | null; onOpen: (id: string) => void }) {
  const num = new Map(r.citations.map((c, i) => [c, i + 1]));
  const text = r.answer ?? "";
  const parts: ReactNode[] = [];
  let at = 0;
  for (const m of text.matchAll(CITE)) {
    parts.push(text.slice(at, m.index));
    const ids = m[1].split(/[;,]/).map((x) => x.trim()).filter(Boolean);
    ids.forEach((id, j) =>
      parts.push(
        <button key={`${m.index}-${j}`} type="button" className="cite-chip" aria-expanded={open === id} aria-label={`Open source ${num.get(id) ?? id}`} onClick={() => onOpen(id)}>
          {num.get(id) ?? "?"}
        </button>,
      ),
    );
    at = (m.index ?? 0) + m[0].length;
  }
  parts.push(text.slice(at));
  return <p className="ai-text">{parts}</p>;
}

function Sources({ sources, open, onOpen }: { sources: AnswerSource[]; open: string | null; onOpen: (id: string) => void }) {
  const cited = sources.filter((s) => s.cited);
  const rest = sources.filter((s) => !s.cited);
  const item = (s: AnswerSource, n?: number) => (
    <li key={s.chunk_id} className="evidence">
      <div className="evidence-head">
        {n && <span className="cite-chip cite-static">{n}</span>}
        <Sticker>{s.section_label}</Sticker>
        <span className="small muted"><Link to={`/label/${s.set_id}`}>{s.product}</Link></span>
        <button type="button" className="btn btn-plain btn-sm" aria-expanded={open === s.chunk_id} onClick={() => onOpen(s.chunk_id)}>
          {open === s.chunk_id ? "Hide passage" : "Show passage"}
        </button>
      </div>
      {open === s.chunk_id && <p className="evidence-text label-text" id={`src-${s.chunk_id}`}>{s.text}</p>}
    </li>
  );
  return (
    <div className="ai-sources">
      {cited.length > 0 && (
        <>
          <h3 className="small">Sources cited</h3>
          <ul className="evidence-list">{cited.map((s, i) => item(s, i + 1))}</ul>
        </>
      )}
      {rest.length > 0 && (
        <details>
          <summary className="small">Other passages the model was given ({rest.length})</summary>
          <ul className="evidence-list">{rest.map((s) => item(s))}</ul>
        </details>
      )}
    </div>
  );
}

/** A price or alternatives question, answered from the catalogue with no model: the Alternatives page's own cheapest list. */
function AlternativesAnswer({ r, medicineId }: { r: AskResponse; medicineId: string }) {
  return (
    <div className="ai-box alt-answer">
      <p><strong>{r.alt_note}</strong></p>
      {r.alt_total === 0 ? (
        <p className="muted">No other brand in our database has the same ingredients, strength and form.</p>
      ) : (
        <>
          <p className="small muted">
            {r.alt_total} {r.alt_total === 1 ? "brand" : "brands"}, cheapest first. Prices are per pack as listed and may be out of date.
          </p>
          <ul className="alt-rows">
            {r.alternatives.map((a) => (
              <AltRow key={a.id} a={a} />
            ))}
          </ul>
        </>
      )}
      <p><Link to={`/alternatives?id=${encodeURIComponent(medicineId)}`}>See all alternatives</Link></p>
    </div>
  );
}

/** "Ask about this medicine": the model answers only from this medicine's retrieved label passages. No history is kept. */
export function AskMedicine({ medicineId, medicineName }: { medicineId: string; medicineName: string }) {
  const status = useAnswerStatus();
  const [q, setQ] = useState("");
  const [scope, setScope] = useState<"default" | "all">("default");
  const [run, setRun] = useState<Run<AskResponse>>({ state: "idle" });
  const [open, setOpen] = useState<string | null>(null);
  if (status?.status !== "ready") return null;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!q.trim()) return;
    setOpen(null);
    void exec(setRun, () => api.answerAsk(medicineId, q.trim(), scope));
  };
  const toggle = (id: string) => setOpen((o) => (o === id ? null : id));
  return (
    <section className="card" aria-labelledby="ask-h">
      <h2 id="ask-h">Ask about this medicine</h2>
      <p className="small muted">
        Ask in your own words. The answer is written from the US label text for {medicineName} that matches your question, and cites it. Your
        question is sent to {status.provider === "gemini" ? "Google Gemini" : status.provider}. Do not type your name or health details. Questions about price or alternatives are answered from our brand list instead, without the AI.
      </p>
      <form onSubmit={submit} className="ls-form">
        <Field label="Your question">
          <input type="text" value={q} maxLength={300} onChange={(e) => setQ(e.target.value)} placeholder="For example: can I take it with food?" />
        </Field>
        <button type="submit" className="btn btn-primary" disabled={!q.trim() || run.state === "loading"}>
          {run.state === "loading" ? "Writing…" : "Ask"}
        </button>
      </form>
      <div className="seg" role="group" aria-label="Which labels to use">
        {(["default", "all"] as const).map((s) => (
          <button key={s} type="button" className="btn btn-secondary btn-sm" aria-pressed={scope === s} onClick={() => setScope(s)}>
            {s === "default" ? "Default label only" : "All linked labels"}
          </button>
        ))}
      </div>
      <Outcome run={run}>
        {(r) => r.kind === "alternatives" ? <AlternativesAnswer r={r} medicineId={medicineId} /> : (
          <div className="ai-box">
            <AiMark s={r}>
              {" "}· from {r.sources.length} label {r.sources.length === 1 ? "passage" : "passages"}
            </AiMark>
            <AnswerText r={r} open={open} onOpen={toggle} />
            {r.not_found && r.note && <p className="small muted">{r.note}</p>}
            {r.dropped_sentences > 0 && <p className="small"><Sticker wrap>Checked</Sticker> {r.note}</p>}
            {r.uncited_sentences > 0 && (
              <p className="small"><Sticker wrap>Check</Sticker> {r.uncited_sentences} sentence(s) have no source. Rely on the label passages below.</p>
            )}
            <Sources sources={r.sources} open={open} onOpen={toggle} />
            <Disclaimer />
          </div>
        )}
      </Outcome>
    </section>
  );
}

// ---- Explain in simple words ---------------------------------------------------------------------
/** Button under a verbatim details section. The original stays on the page; the rewrite appears beside or below it. */
export function SimplifyButton({ medicineId, ingredientIndex, sectionKey }: { medicineId: string; ingredientIndex: number; sectionKey: string }) {
  const status = useAnswerStatus();
  const [run, setRun] = useState<Run<SimplifyResponse>>({ state: "idle" });
  if (status?.status !== "ready") return null;
  return (
    <div className="ai-slot">
      <button type="button" className="btn btn-secondary btn-sm" disabled={run.state === "loading"}
        onClick={() => void exec(setRun, () => api.answerSimplify(medicineId, ingredientIndex, sectionKey))}>
        {run.state === "loading" ? "Writing…" : run.state === "ok" ? "Explain again" : "Explain in simple words"}
      </button>
      <Outcome run={run}>
        {(r) => (
          <div className="ai-box">
            <AiMark s={r}> · plain-words rewrite of the full “{r.section_label}” section</AiMark>
            {r.flagged && (
              <p className="notice-inline" role="alert">
                <Sticker tone="danger" >Not verified</Sticker> These numbers or units are not in the original: <strong>{r.unmatched.join(", ")}</strong>.
                Rely on the original text.
              </p>
            )}
            <p className="ai-text">{r.simplified}</p>
            <details>
              <summary className="small">Original text that was rewritten</summary>
              <blockquote className="label-text">{r.original}</blockquote>
            </details>
            <Disclaimer />
          </div>
        )}
      </Outcome>
    </div>
  );
}

// ---- Explain this finding ------------------------------------------------------------------------
export type FindingInput = Omit<ExplainFindingRequest, "predicted_class"> & { classify?: { sentence: string; drug1: string; drug2: string } };

/** "Explain this finding": plain words for why a pair, or an allergen and ingredient, may matter. The level is shown unchanged. */
export function ExplainFinding({ input }: { input: FindingInput }) {
  const status = useAnswerStatus();
  const [run, setRun] = useState<Run<ExplainFindingResponse>>({ state: "idle" });
  if (status?.status !== "ready") return null;
  const go = () =>
    void exec(setRun, async () => {
      const { classify, ...body } = input;
      const predicted = classify ? await cachedPrediction(classify.sentence, classify.drug1, classify.drug2) : null;
      return api.answerExplainFinding({ ...body, predicted_class: predicted });
    });
  return (
    <div className="ai-slot">
      <button type="button" className="btn btn-secondary btn-sm" disabled={run.state === "loading"} onClick={go}>
        {run.state === "loading" ? "Writing…" : "Explain this finding"}
      </button>
      <Outcome run={run}>
        {(r) => (
          <div className="ai-box">
            <AiMark s={r}> · from the rule text and label sentences shown here. Level stays <strong>{r.level}</strong>.</AiMark>
            {r.flagged && (
              <p className="notice-inline" role="alert">
                <Sticker tone="danger">Not verified</Sticker> These numbers are not in the texts above: <strong>{r.unmatched.join(", ")}</strong>.
              </p>
            )}
            <p className="ai-text">{r.text}</p>
            <Disclaimer />
          </div>
        )}
      </Outcome>
    </div>
  );
}
