import { useState } from "react";
import { api, type DDIStatsResponse } from "../api";
import { useApi, type Query } from "../useApi";
import { ClassDistributionChart } from "./ClassDistributionChart";
import { fmt, Panel } from "./Panel";
import { Sticker } from "./Sticker";

const ratio = (v: number | null | undefined) => (v == null ? "n/a" : v.toFixed(2));

function CountsTable({ stats }: { stats: DDIStatsResponse }) {
  const by = Object.fromEntries(stats.splits.map((s) => [s.split, s]));
  const positives = stats.labels.filter((l) => l !== "false");
  return (
    <div className="table-wrap">
      <table>
        <caption>
          Instances per class (table view of the chart), and the imbalance ratio <code>false : class</code>
        </caption>
        <thead>
          <tr>
            <th scope="col">Class</th>
            <th scope="col" className="num">Train</th>
            <th scope="col" className="num">Dev</th>
            <th scope="col" className="num">Test</th>
            <th scope="col" className="num">False : class (train)</th>
            <th scope="col" className="num">(dev)</th>
            <th scope="col" className="num">(test)</th>
          </tr>
        </thead>
        <tbody>
          {stats.labels.map((l) => (
            <tr key={l}>
              <th scope="row">{l}</th>
              {(["train", "dev", "test"] as const).map((s) => (
                <td className="num" key={s}>{fmt(by[s]?.class_counts[l])}</td>
              ))}
              {(["train", "dev", "test"] as const).map((s) => (
                <td className="num" key={"r" + s}>{positives.includes(l) ? ratio(by[s]?.imbalance_false_to_class[l]) : "–"}</td>
              ))}
            </tr>
          ))}
          <tr className="total">
            <th scope="row">Total</th>
            {(["train", "dev", "test"] as const).map((s) => (
              <td className="num" key={s}>{fmt(by[s]?.instances)}</td>
            ))}
            <td colSpan={3} />
          </tr>
        </tbody>
      </table>
    </div>
  );
}

function ParserTable({ stats }: { stats: DDIStatsResponse }) {
  const keys = Array.from(new Set(stats.parser.flatMap((p) => Object.keys(p.counts))));
  return (
    <details>
      <summary>Parser counts and skipped items (before the dev split is carved out of train)</summary>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">Count</th>
              {stats.parser.map((p) => (
                <th key={p.split} scope="col" className="num">{p.split === "train_all" ? "train (incl. dev)" : p.split}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {keys.map((k) => (
              <tr key={k}>
                <th scope="row">{k.replace(/_/g, " ").replace(/^./, (ch) => ch.toUpperCase())}</th>
                {stats.parser.map((p) => (
                  <td key={p.split} className="num">{fmt(p.counts[k] ?? 0)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="small muted">
        <code>pairs</code> is what the corpus contains; <code>instances</code> is what the parser kept. The difference is the
        skipped pairs listed above (for example overlapping drug mentions).
      </p>
    </details>
  );
}

export function DdiStatsPanel({ query: q }: { query: Query<DDIStatsResponse> }) {
  return (
    <Panel
      id="ddi-stats"
      title="DDI Extraction 2013: class distribution"
      hint="Computed live by the project's parser from the corpus files. The test split is the corpus's own; dev is carved from train."
      query={q}
    >
      {(s) => (
        <>
          <ClassDistributionChart stats={s} />
          <CountsTable stats={s} />
          <p className="small muted">
            Dev split: {Math.round((s.dev_frac ?? 0) * 100)}% of train, stratified by class and grouped by document (seed {s.seed}).
            Corpus XML files: {Object.entries(s.files_by_split).map(([k, v]) => `${k.replace(/_/g, " ")} ${v}`).join(", ")}.
          </p>
          <ParserTable stats={s} />
        </>
      )}
    </Panel>
  );
}

/** Highlight the two marked drugs in a real corpus sentence. */
function MarkedText({ text }: { text: string }) {
  const parts = text.split(/(<e1>.*?<\/e1>|<e2>.*?<\/e2>)/g).filter(Boolean);
  return (
    <p className="sentence">
      {parts.map((p, i) => {
        const m = /^<(e[12])>(.*)<\/e[12]>$/.exec(p);
        return m ? (
          <mark key={i} className={m[1]} title={m[1] === "e1" ? "first drug" : "second drug"}>
            {m[2]} <sub>{m[1]}</sub>
          </mark>
        ) : (
          <span key={i}>{p}</span>
        );
      })}
    </p>
  );
}

export function DdiExamplesPanel({ labels }: { labels: string[] }) {
  const [split, setSplit] = useState("test");
  const [label, setLabel] = useState("int");
  const q = useApi(() => api.ddiExamples({ split, label, limit: 5 }), [split, label]);
  return (
    <Panel
      id="ddi-examples"
      title="Real examples"
      hint="Sentences from the corpus with the two drugs of the pair marked. The label is the pair's annotation."
      query={q}
    >
      {(d) => (
        <>
          <div className="filters">
            <label>
              Split{" "}
              <select value={split} onChange={(e) => setSplit(e.target.value)}>
                {["train", "dev", "test"].map((s) => <option key={s}>{s}</option>)}
              </select>
            </label>
            <label>
              Class{" "}
              <select value={label} onChange={(e) => setLabel(e.target.value)}>
                {labels.map((s) => <option key={s}>{s}</option>)}
              </select>
            </label>
            <span className="muted small">showing {d.examples.length} of {fmt(d.total_matching)} matching pairs</span>
          </div>
          <ul className="examples">
            {d.examples.map((e) => (
              <li key={e.pair_id}>
                <div className="example-meta">
                  <Sticker>{e.label}</Sticker>
                  <span className="muted small">{e.source} · {e.pair_id}</span>
                </div>
                <MarkedText text={e.marked_text} />
              </li>
            ))}
          </ul>
        </>
      )}
    </Panel>
  );
}
