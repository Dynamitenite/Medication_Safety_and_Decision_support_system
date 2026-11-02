import { api } from "../api";
import type { DDIMetricsResponse, DDIRun, DDISplitMetrics } from "../api";
import { useApi } from "../useApi";
import { CLASS_NAME } from "./InteractionType";
import { ErrorBox, fmt, LoadingBox, NotReadyBox } from "./Panel";
import { Sticker } from "./Sticker";

const pct = (x: number | null | undefined) => (x == null ? "n/a" : (x * 100).toFixed(1));
const POSITIVE = ["effect", "mechanism", "advise", "int"];

/** Class definitions: a paraphrase of arXiv 1701.08303, not the official annotation guideline text. */
const DEFINITIONS: [string, string][] = [
  ["advise", "an opinion or recommendation about using the drugs together"],
  ["effect", "the effect of the interaction, or a pharmacodynamic mechanism"],
  ["mechanism", "a pharmacokinetic mechanism"],
  ["int", "an interaction is mentioned without other information"],
  ["false", "no interaction stated"],
];

function Side({ runs, pick, title }: { runs: DDIRun[]; pick: (r: DDIRun) => DDISplitMetrics | null | undefined; title: string }) {
  const ce = runs.find((r) => r.name === "ce");
  const fl = runs.find((r) => r.name === "focal");
  const sm = runs.find((r) => r.name === "smoke");
  const cols = [ce && { n: "Cross-entropy", r: ce }, fl && { n: "Focal loss", r: fl }, sm && { n: "Smoke test", r: sm }].filter(Boolean) as { n: string; r: DDIRun }[];
  const cols2 = cols.filter((c) => pick(c.r));
  if (!cols2.length) return null;
  const rows = ["precision", "recall", "f1"] as const;
  return (
    <div className="table-wrap">
      <table>
        <caption>{title}</caption>
        <thead>
          <tr>
            <th scope="col">Class</th>
            {cols2.map((c) => (
              <th key={c.n} scope="col" colSpan={3} className="num">{c.n}</th>
            ))}
            <th scope="col" className="num">Support</th>
          </tr>
          <tr>
            <th scope="col"><span className="sr-only">Metric</span></th>
            {cols2.flatMap((c) => rows.map((k) => <th key={c.n + k} scope="col" className="num">{k === "f1" ? "F1" : k === "precision" ? "P" : "R"}</th>))}
            <th scope="col" />
          </tr>
        </thead>
        <tbody>
          <tr className="total">
            <th scope="row">Micro (4 positive classes)</th>
            {cols2.flatMap((c) => rows.map((k) => <td key={c.n + k} className="num">{pct(pick(c.r)!.micro[k])}</td>))}
            <td className="num">{fmt(pick(cols2[0].r)!.per_class.filter((p) => POSITIVE.includes(p.label)).reduce((a, p) => a + p.support, 0))}</td>
          </tr>
          {pick(cols2[0].r)!.per_class.map((p) => (
            <tr key={p.label}>
              <th scope="row">{p.label}</th>
              {cols2.flatMap((c) => {
                const row = pick(c.r)!.per_class.find((x) => x.label === p.label)!;
                return rows.map((k) => <td key={c.n + k} className="num">{pct(row[k])}</td>);
              })}
              <td className="num">{fmt(p.support)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Confusion({ m, name }: { m: DDISplitMetrics; name: string }) {
  return (
    <div className="table-wrap">
      <table className="cm">
        <caption>{name}: confusion matrix (rows: true class, columns: predicted)</caption>
        <thead>
          <tr>
            <th scope="col" />
            {m.labels.map((l) => (
              <th key={l} scope="col" className="num">{l}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {m.labels.map((l, i) => (
            <tr key={l}>
              <th scope="row">{l}</th>
              {m.confusion_matrix[i].map((v, j) => (
                <td key={j} className={`num${i === j ? " cm-diag" : ""}`}>{fmt(v)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Results({ d }: { d: DDIMetricsResponse }) {
  const ce = d.runs.find((r) => r.name === "ce");
  const fl = d.runs.find((r) => r.name === "focal");
  const smoke = d.runs.some((r) => r.smoke_test);
  const both = ce?.test && fl?.test;
  const dF = fl && ce && both ? fl.test!.micro.f1 - ce.test!.micro.f1 : null;
  return (
    <>
      {smoke && (
        <p>
          <Sticker tone="danger">Smoke-test result, not for reporting</Sticker> These numbers come from a pipeline check with a tiny
          random model, a few hundred training sentences and one epoch. They say nothing about the method.
        </p>
      )}
      {both && dF != null && (
        <p>
          <strong>Result on the test set:</strong>{" "}
          {dF > 0
            ? `focal loss reached a higher micro-F1 than cross-entropy (${pct(fl!.test!.micro.f1)} against ${pct(ce!.test!.micro.f1)}).`
            : dF < 0
              ? `focal loss did not beat cross-entropy: its micro-F1 was ${pct(fl!.test!.micro.f1)} against ${pct(ce!.test!.micro.f1)}.`
              : `focal loss and cross-entropy have the same micro-F1 (${pct(fl!.test!.micro.f1)}).`}{" "}
          One seed ({fl!.seed}) and one split; the difference may be within run-to-run variation.
        </p>
      )}
      <Side runs={d.runs} pick={(r) => r.test} title="Test set (read once, for the final models): precision, recall and F1, %" />
      <Side runs={d.runs} pick={(r) => r.dev} title="Dev set (used to choose the settings): precision, recall and F1, %" />
      <div className="grid-2">
        {d.runs.filter((r) => r.test).map((r) => (
          <Confusion key={r.name} m={r.test!} name={`${r.name === "ce" ? "Cross-entropy" : r.name === "focal" ? "Focal loss" : "Smoke test"} (test)`} />
        ))}
      </div>
      <p className="small muted">
        Settings: {d.runs.map((r) => `${r.name}: ${r.loss}${r.loss === "focal" ? ` γ=${r.gamma}, α=${r.alpha}` : ""}, encoder lr ${r.lr_encoder}, head lr ${r.lr_head}, best epoch ${r.best_epoch}`).join("; ")}. Encoder:{" "}
        {d.runs[0].encoder}. Training sentences: {fmt(d.runs[0].n_train)}; dev: {fmt(d.runs[0].n_dev)}
        {d.runs[0].n_test != null ? `; test: ${fmt(d.runs[0].n_test)}` : ""}.
      </p>
      {d.search.length > 0 && (
        <details>
          <summary>Settings search on the dev set ({d.search.length} runs{d.search_smoke_test ? ", smoke test" : ""})</summary>
          <div className="table-wrap">
            <table>
              <caption>Each row is one short run; micro-F1 is on the dev set only</caption>
              <thead>
                <tr>
                  <th scope="col">Loss</th><th scope="col" className="num">γ</th><th scope="col">α</th>
                  <th scope="col" className="num">Encoder lr</th><th scope="col" className="num">Head lr</th>
                  <th scope="col" className="num">Best epoch</th><th scope="col" className="num">Dev micro-F1 %</th>
                </tr>
              </thead>
              <tbody>
                {d.search.map((s, i) => (
                  <tr key={i}>
                    <th scope="row">{s.loss}</th>
                    <td className="num">{s.loss === "focal" ? s.gamma : "–"}</td><td>{s.loss === "focal" ? s.alpha : "–"}</td>
                    <td className="num">{s.lr_encoder}</td><td className="num">{s.lr_head}</td>
                    <td className="num">{s.best_epoch}</td><td className="num">{pct(s.dev_micro_f1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
      {fl?.faithfulness && (
        <>
          <h3>Faithfulness proxy</h3>
          <div className="table-wrap">
            <table>
              <caption>
                {fl.faithfulness.label}: mean drop in the predicted-class probability when words are deleted ({fl.faithfulness.n_sentences}{" "}
                {fl.faithfulness.source}; {fl.faithfulness.random_draws} random draws, seed {fl.faithfulness.seed})
              </caption>
              <thead>
                <tr>
                  <th scope="col" className="num">Words deleted (k)</th>
                  <th scope="col" className="num">Top-k attributed</th>
                  <th scope="col" className="num">k random words</th>
                  <th scope="col" className="num">Sentences used</th>
                  <th scope="col" className="num">Skipped</th>
                </tr>
              </thead>
              <tbody>
                {fl.faithfulness.by_k.map((k) => (
                  <tr key={k.k}>
                    <th scope="row" className="num">{k.k}</th>
                    <td className="num">{k.mean_drop_top_k == null ? "n/a" : k.mean_drop_top_k.toFixed(3)}</td>
                    <td className="num">{k.mean_drop_random_k == null ? "n/a" : k.mean_drop_random_k.toFixed(3)}</td>
                    <td className="num">{fmt(k.n)}</td>
                    <td className="num">{fmt(k.skipped)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="small muted">
            A faithfulness proxy, not proof that an explanation is correct. If deleting the top-attributed words lowers the probability more
            than deleting random words, the explanation points at words the model does use.
          </p>
        </>
      )}
    </>
  );
}

export function DdiModelSection() {
  const q = useApi(api.ddiMetrics);
  return (
    <section className="card" aria-labelledby="clf-h">
      <h2 id="clf-h">Interaction-type model (Focal Loss)</h2>
      <p>
        <strong>Algorithm.</strong> BioBERT, then a bidirectional LSTM, then a classifier over the [CLS] state and the mean state of each
        drug mention. The two drug names are marked with <code>&lt;e1&gt;</code> and <code>&lt;e2&gt;</code>. It is trained with the focal loss
        of Jia et al. (2026), <code>FL = −α<sub>t</sub> (1 − p<sub>t</sub>)<sup>γ</sup> log p<sub>t</sub></code>, and compared with plain
        cross-entropy using the same seed and split. The dual graph, GCN and GAN parts of that paper are not implemented. The
        model labels the type of interaction a sentence states. It does not set any risk level: levels come only from our interaction
        rules.
      </p>
      <p>
        <strong>Data.</strong> DDI Extraction 2013 (research abstracts and DrugBank text): one instance per drug pair per sentence, five
        classes, dev set carved from train, the official test set read once. Settings (γ, α, learning rates) were chosen on the dev set only.
      </p>
      <h3>Measured results</h3>
      {q.state === "loading" && !q.data && <LoadingBox what="model metrics" />}
      {q.state === "error" && <ErrorBox message={q.message} onRetry={q.reload} />}
      {q.data?.status === "not_ready" && <NotReadyBox reason={q.data.reason} fix={q.data.fix} title="No measured results yet" />}
      {q.data?.status === "ready" && <Results d={q.data} />}
      <h3>Class definitions</h3>
      <p className="small muted">A paraphrase from arXiv 1701.08303, not the official annotation guideline text.</p>
      <dl className="defs">
        {DEFINITIONS.map(([k, v]) => (
          <div key={k}>
            <dt>{CLASS_NAME[k]} <code>{k}</code></dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
      <h3>How the “Why?” view works</h3>
      <p>
        It uses Integrated Gradients (Captum) over the input tokens for the predicted class, with an all-padding baseline. Word-piece scores
        are added back into whole words. The check of this view is deletion-based: remove the top-k attributed words and measure the drop in the
        predicted-class probability, compared with removing k random words. That is a faithfulness proxy, not proof that the explanation is
        right.
      </p>
      <h3>Limits</h3>
      <ul>
        <li>Trained on DDI 2013 text, not on our interaction rules. Its output is a model estimate of the type of interaction a sentence describes.</li>
        <li>Not a clinical judgement. It never changes a risk level and is never shown as one.</li>
        <li>
          Domain shift: the training sentences come from research abstracts and DrugBank descriptions. The sentences in US drug labels are written
          in a different style, so the estimate can be wrong in ways the test numbers above do not show.
        </li>
        <li>Only label sentences that name both drugs can be marked. Sentences that say “this drug” are not classified.</li>
        <li>No accuracy claim is made for the Indian medicine catalogue. The model has not been evaluated on it.</li>
      </ul>
    </section>
  );
}
