import { useId, useMemo } from "react";
import type { AnalyzeResponse } from "../../api";
import { layoutGraph, type GraphEdge, type GraphNode } from "../../viz/graph";
import { ChartFrame, reducedMotion } from "./ChartFrame";
import { LevelGlyph } from "./icons";

const clip = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);
const LEVEL_VAR = { Medium: "--c-amber", High: "--c-rose", Critical: "--c-rose" } as const;
const colour = (l: GraphEdge["level"]) => (l ? `rgb(var(${LEVEL_VAR[l]}))` : "rgb(var(--c-subtle))");
const KIND_TEXT = { new: "To add", current: "Current", allergen: "Allergy" } as const;

function go(id: string) {
  const el = document.getElementById(id);
  if (!el) return;
  el.scrollIntoView({ behavior: reducedMotion() ? "auto" : "smooth", block: "center" });
  el.focus({ preventScroll: true });
  el.classList.add("finding-flash");
  window.setTimeout(() => el.classList.remove("finding-flash"), 1600);
}

function NodeMark({ n }: { n: GraphNode }) {
  // three shapes: filled circle (to add), ring (current), diamond (allergy)
  if (n.kind === "allergen") return <path className="gn-mark" d={`M${n.x} ${n.y - 10} L${n.x + 10} ${n.y} L${n.x} ${n.y + 10} L${n.x - 10} ${n.y} Z`} />;
  if (n.kind === "new") return <circle className="gn-mark gn-fill" cx={n.x} cy={n.y} r={9} />;
  return <circle className="gn-mark" cx={n.x} cy={n.y} r={9} />;
}

/** One node per medicine and allergen, one edge per finding. Click or press Enter on an edge to jump to its card. */
export function InteractionGraph({ data }: { data: AnalyzeResponse }) {
  const graphId = useId().replace(/:/g, "");
  const layout = useMemo(
    () =>
      layoutGraph(
        {
          medicines: data.medicines.map((m) => ({ key: m.medicine.key, name: m.medicine.name, role: m.role })),
          pairs: data.pairs.map((p) => ({ a: p.a.key, b: p.b.key, level: p.level ?? null })),
          allergies: data.allergy_findings.map((f) => ({ medicineKey: f.medicine.key, allergyId: f.allergy_id, allergen: f.allergen, level: f.level })),
        },
        460,
      ),
    [data],
  );
  const count = data.pairs.length + data.allergy_findings.length;
  if (count === 0) return null;
  const name = (id: string) => (layout.mode === "circular" ? layout.nodes.find((n) => n.id === id)?.label ?? id : id);

  const rows = layout.mode === "circular" ? layout.edges : [];
  const table = (
    <table>
      <caption className="sr-only">Findings of the risk analysis</caption>
      <thead>
        <tr>
          <th scope="col">Between</th>
          <th scope="col">And</th>
          <th scope="col">Level</th>
        </tr>
      </thead>
      <tbody>
        {(layout.mode === "circular"
          ? rows.map((e) => ({ k: e.id, a: name(e.from), b: name(e.to), l: e.label }))
          : [
              ...data.pairs.map((p) => ({ k: `${p.a.key}|${p.b.key}`, a: p.a.name, b: p.b.name, l: p.level ?? "No level" })),
              ...data.allergy_findings.map((f) => ({ k: `a${f.allergy_id}${f.medicine.key}`, a: f.medicine.name, b: `Allergy: ${f.allergen}`, l: f.level })),
            ]
        ).map((r) => (
          <tr key={r.k}>
            <td>{r.a}</td>
            <td>{r.b}</td>
            <td>{r.l}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );

  let chart;
  if (layout.mode === "list-only") {
    chart = <p className="muted">{layout.reason}</p>;
  } else {
    const S = layout.size;
    const H = 400;
    const cx = S / 2;
    chart = (
      <div className="graph-wrap">
        <svg viewBox={`0 0 ${S} ${H}`} className="graph-svg" role="group" aria-label={`Interaction graph: ${layout.nodes.length} items and ${layout.edges.length} findings`} focusable="false">
          <g transform={`translate(0 ${(H - S) / 2})`}>
            {layout.edges.map((e, i) => {
              const p = layout.nodes.find((n) => n.id === e.from)!;
              const q = layout.nodes.find((n) => n.id === e.to)!;
              const text = `${e.label}: ${p.label} and ${q.label}. Go to this finding.`;
              const act = () => go(e.targetId);
              const w = e.label.length * 6.6 + 30;
              return (
                <g
                  key={e.id}
                  className="ge"
                  tabIndex={0}
                  role="link"
                  aria-labelledby={`${graphId}-edge-${i}-label`}
                  aria-description={text}
                  onClick={act}
                  onKeyDown={(ev) => {
                    if (ev.key === "Enter" || ev.key === " ") {
                      ev.preventDefault();
                      act();
                    }
                  }}
                >
                  <line className="ge-hit" x1={p.x} y1={p.y} x2={q.x} y2={q.y} />
                  <line className="ge-line" x1={p.x} y1={p.y} x2={q.x} y2={q.y} style={{ stroke: colour(e.level), strokeWidth: e.level === "Critical" ? 3.5 : 2, strokeDasharray: e.level === "Medium" ? "7 4" : e.level === null ? "2 4" : undefined }} />
                  <g transform={`translate(${e.lx} ${e.ly})`} style={{ color: colour(e.level) }}>
                    <rect className="ge-pill" x={-w / 2} y={-11} width={w} height={22} rx={4} style={{ stroke: colour(e.level) }} />
                    <g transform={`translate(${-w / 2 + 6} -8)`}>
                      <LevelGlyph level={e.level} size={16} />
                    </g>
                    <text id={`${graphId}-edge-${i}-label`} className="ge-text" x={-w / 2 + 26} y={4}>
                      {e.label}
                    </text>
                  </g>
                </g>
              );
            })}
            {layout.nodes.map((n) => {
              const dx = n.x - cx;
              const dy = n.y - S / 2;
              const len = Math.hypot(dx, dy) || 1;
              const lx = n.x + (dx / len) * 18;
              const ly = n.y + (dy / len) * 18 + (Math.abs(dy / len) > 0.5 ? (dy > 0 ? 8 : -2) : 4);
              const anchor = Math.abs(dx / len) < 0.3 ? "middle" : dx > 0 ? "start" : "end";
              return (
                <g key={n.id} className="gn">
                  <title>{`${KIND_TEXT[n.kind]}: ${n.label}`}</title>
                  <NodeMark n={n} />
                  <text className="gn-text" x={lx} y={ly} textAnchor={anchor}>
                    {clip(n.label, 20)}
                  </text>
                </g>
              );
            })}
          </g>
        </svg>
        <ul className="graph-key small" aria-label="Key">
          <li><svg width="18" height="18" aria-hidden="true"><circle cx="9" cy="9" r="7" className="gn-mark gn-fill" /></svg>To add</li>
          <li><svg width="18" height="18" aria-hidden="true"><circle cx="9" cy="9" r="7" className="gn-mark" /></svg>Current</li>
          <li><svg width="18" height="18" aria-hidden="true"><path d="M9 1.5 16.5 9 9 16.5 1.5 9Z" className="gn-mark" /></svg>Allergy</li>
          <li><svg width="30" height="10" aria-hidden="true"><line x1="0" y1="5" x2="30" y2="5" style={{ stroke: "rgb(var(--c-amber))", strokeWidth: 2, strokeDasharray: "7 4" }} /></svg>Medium (dashed)</li>
          <li><svg width="30" height="10" aria-hidden="true"><line x1="0" y1="5" x2="30" y2="5" style={{ stroke: "rgb(var(--c-rose))", strokeWidth: 2 }} /></svg>High</li>
          <li><svg width="30" height="10" aria-hidden="true"><line x1="0" y1="5" x2="30" y2="5" style={{ stroke: "rgb(var(--c-rose))", strokeWidth: 3.5 }} /></svg>Critical (thick)</li>
        </ul>
      </div>
    );
  }

  return (
    <ChartFrame
      title="Interaction graph"
      description="Each circle is a medicine and each diamond is a recorded allergy. A line is one finding, named with its level. Select a line to jump to its card. The same findings are listed below."
      chart={chart}
      table={table}
      views={["Graph", "Table"]}
    />
  );
}
