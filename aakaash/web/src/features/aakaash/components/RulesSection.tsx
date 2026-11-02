import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import type { AppmsSummaryResponse } from "../api";
import { useApi } from "../useApi";
import { Panel, fmt } from "./Panel";

const SEV_FILL: Record<string, string> = {
  Critical: "rgb(var(--c-rose))",
  High: "rgb(var(--c-amber))",
  Moderate: "rgb(var(--c-mint))",
};

function SeverityChart({ s }: { s: AppmsSummaryResponse }) {
  const [table, setTable] = useState(false);
  const rows = s.severity.map((r) => ({ name: r.severity, value: r.scenarios }));
  return (
    <>
      <div className="tabs" role="group" aria-label="Chart or table">
        <button type="button" className={table ? "tab" : "tab active"} aria-pressed={!table} onClick={() => setTable(false)}>Chart</button>
        <button type="button" className={table ? "tab active" : "tab"} aria-pressed={table} onClick={() => setTable(true)}>Table</button>
      </div>
      {table ? (
        <div className="table-wrap">
          <table>
            <caption className="sr-only">Sample cases matched by a rule, by severity</caption>
            <thead><tr><th scope="col">Severity</th><th scope="col">Sample cases</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.name}><th scope="row">{r.name}</th><td>{fmt(r.value)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <figure className="chart" aria-label="Sample cases matched by a rule, by severity">
          <ResponsiveContainer width="100%" height={rows.length * 44 + 40}>
            <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 56, left: 4, bottom: 4 }}>
              <CartesianGrid horizontal={false} stroke="rgb(var(--c-line))" />
              <XAxis type="number" allowDecimals={false} tickLine={false} axisLine={{ stroke: "rgb(var(--c-line))" }} tick={{ fill: "rgb(var(--c-muted))", fontSize: 12 }} />
              <YAxis type="category" dataKey="name" width={84} tickLine={false} axisLine={false} tick={{ fill: "rgb(var(--c-soft))", fontSize: 12 }} />
              <Tooltip
                cursor={{ fill: "rgb(var(--c-text) / 0.06)" }}
                content={({ active, payload }) =>
                  active && payload?.length ? (
                    <div className="chart-tooltip"><strong>{payload[0].payload.name}</strong><div>{fmt(payload[0].payload.value)} sample cases</div></div>
                  ) : null
                }
              />
              <Bar dataKey="value" maxBarSize={24} radius={[0, 3, 3, 0]} isAnimationActive={false} stroke="var(--chart-edge)" strokeWidth={1}>
                {rows.map((r) => <Cell key={r.name} fill={SEV_FILL[r.name]} />)}
                <LabelList dataKey="value" position="right" formatter={(v: number) => v.toLocaleString("en-US")} fill="rgb(var(--c-text))" fontSize={12} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </figure>
      )}
    </>
  );
}

/** Interaction-rule summary: counts, severity chart (with a table view) and the not-proof-of-safety note. */
export function RulesSection() {
  const q = useApi(() => api.appmsSummary());
  return (
    <Panel id="rules" title="Interaction rules" query={q} hint="Rules for drug pairs, each with a severity, and the sample cases used to test them.">
      {(s) => {
        const cards: [string, number][] = [
          ["Rules", s.rules],
          ["Sample patients", s.patients],
          ["Medication rows", s.medication_rows],
          ["Drug-pair cases", s.scenarios],
          ["Matched by a rule", s.flagged_scenarios],
          ["No rule matched", s.not_flagged_scenarios],
        ];
        return (
          <>
            <dl className="stat-cards">
              {cards.map(([k, v]) => (
                <div key={k} className="stat-card"><dt>{k}</dt><dd>{fmt(v)}</dd></div>
              ))}
            </dl>
            <h3>Matched cases by severity</h3>
            <SeverityChart s={s} />
            <p className="small muted">
              {s.note} The cases carry {s.distinct_explanations} distinct explanation texts; {s.orphan_medication_rows} medication rows have no patient.
            </p>
          </>
        );
      }}
    </Panel>
  );
}
