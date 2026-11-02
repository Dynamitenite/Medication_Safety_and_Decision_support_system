import { useEffect, useState } from "react";
import { api } from "../api";
import type { DDIClassifyResponse, DDIWord } from "../api";
import { useStatus } from "../StatusContext";
import { Sticker } from "./Sticker";

/** Names shown for the five classes of the model. */
export const CLASS_NAME: Record<string, string> = {
  effect: "Effect",
  mechanism: "Mechanism",
  advise: "Advice",
  int: "Interaction mentioned",
  false: "No interaction stated",
};

/** One request per distinct (sentence, drug pair, explain) in this page session. */
const cache = new Map<string, Promise<DDIClassifyResponse>>();
function classify(sentence: string, d1: string, d2: string, explain: boolean) {
  const key = `${explain}|${d1}|${d2}|${sentence}`;
  let p = cache.get(key);
  if (!p) {
    p = api.ddiClassify(sentence, d1, d2, explain);
    p.catch(() => cache.delete(key));
    cache.set(key, p);
  }
  return p;
}

/** The sentence with each word shaded by its Integrated Gradients score for the predicted class.
 *  Shade strength = |score| / largest |score|. Pushing toward the class: filled. Against: dotted underline. */
export function AttributedSentence({ text, words }: { text: string; words: DDIWord[] }) {
  const max = Math.max(1e-12, ...words.map((w) => Math.abs(w.attribution)));
  const parts: JSX.Element[] = [];
  let at = 0;
  const ordered = [...words].sort((a, b) => a.start - b.start);
  ordered.forEach((w, i) => {
    if (w.start > at) parts.push(<span key={`g${i}`}>{text.slice(at, w.start)}</span>);
    const strength = w.is_drug ? 0 : Math.abs(w.attribution) / max;
    const cls = `attr${w.is_drug ? " attr-drug" : w.attribution > 0 ? " attr-pos" : " attr-neg"}`;
    parts.push(
      <span key={`w${i}`} className={cls} style={{ ["--a" as string]: strength.toFixed(2) }}
        title={w.is_drug ? "Drug name (not scored)" : `Score ${w.attribution.toExponential(2)}`}>
        {text.slice(w.start, w.end)}
      </span>,
    );
    at = w.end;
  });
  if (at < text.length) parts.push(<span key="tail">{text.slice(at)}</span>);
  return <p className="attr-sentence">{parts}</p>;
}

function Why({ sentence, d1, d2 }: { sentence: string; d1: string; d2: string }) {
  const [open, setOpen] = useState(false);
  const [res, setRes] = useState<DDIClassifyResponse | "error" | null>(null);
  useEffect(() => {
    if (!open || res) return;
    let alive = true;
    classify(sentence, d1, d2, true).then((r) => alive && setRes(r), () => alive && setRes("error"));
    return () => {
      alive = false;
    };
  }, [open, res, sentence, d1, d2]);
  return (
    <details className="ddi-why" onToggle={(e) => setOpen((e.currentTarget as HTMLDetailsElement).open)}>
      <summary>Why?</summary>
      {open && !res && <p className="small muted" role="status">Working out which words matter… this can take a few seconds.</p>}
      {res === "error" && <p className="small muted">The explanation could not be made.</p>}
      {res && res !== "error" && res.status === "ready" && res.words && res.ig && (
        <>
          <AttributedSentence text={sentence} words={res.words} />
          <p className="small muted">
            Shaded words pushed the model toward “{CLASS_NAME[res.predicted ?? ""]}”; darker means more. Dotted underline: pushed against it. Drug
            names are not scored. Method: Integrated Gradients over the input tokens ({res.ig.n_steps} steps, convergence delta{" "}
            {res.ig.delta.toExponential(1)}). This shows what the model used, not a clinical reason.
          </p>
        </>
      )}
    </details>
  );
}

/** "Interaction type" for one label sentence that names both drugs: the model's predicted class and
 *  probability, labelled as a model estimate, with a "Why?" expander. It is never used to set a risk
 *  level. Runs only when asked: `active` (a card was opened) or, in `disclosure` mode, when the person
 *  opens it. Renders nothing when the model is not ready, the sentence cannot be marked, or a request fails. */
export function InteractionType({ sentence, drug1, drug2, active = false, disclosure = false }: {
  sentence: string; drug1: string; drug2: string; active?: boolean; disclosure?: boolean;
}) {
  const status = useStatus();
  const ready = status.data?.components.find((c) => c.id === "ddi_model")?.status === "ready";
  const [opened, setOpened] = useState(false);
  const [res, setRes] = useState<DDIClassifyResponse | "error" | null>(null);
  const want = ready && (disclosure ? opened : active);
  useEffect(() => {
    if (!want || res) return;
    let alive = true;
    classify(sentence, drug1, drug2, false).then((r) => alive && setRes(r), () => alive && setRes("error"));
    return () => {
      alive = false;
    };
  }, [want, res, sentence, drug1, drug2]);

  if (!ready) return null;
  if (res === "error" || (res && res.status !== "ready")) return null;
  const body = res && res.status === "ready" && res.predicted && res.probability != null && (
    <div className="ddi-type">
      <p className="ddi-type-line">
        <strong>Interaction type:</strong> {CLASS_NAME[res.predicted]} · {Math.round(res.probability * 100)}%{" "}
        <Sticker>Model estimate</Sticker>
        {res.model?.smoke_test && <Sticker tone="danger">Smoke-test model, not for reporting</Sticker>}
      </p>
      <Why sentence={sentence} d1={drug1} d2={drug2} />
    </div>
  );
  if (disclosure) {
    return (
      <details className="ddi-disclosure" onToggle={(e) => setOpened((e.currentTarget as HTMLDetailsElement).open)}>
        <summary>Interaction type · model estimate</summary>
        {opened && !res && <p className="small muted" role="status">Classifying…</p>}
        {body}
      </details>
    );
  }
  return active && !res ? <p className="small muted" role="status">Classifying…</p> : body || null;
}
