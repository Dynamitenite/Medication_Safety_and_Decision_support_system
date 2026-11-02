import { Bar, BarChart, CartesianGrid, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { DDIStatsResponse } from "../api";

// One lavender hue in four lightness steps for the interaction classes, grey for "false".
// Two middle steps also carry hatching so they stay apart without relying on colour.
const CLASS_FILL: Record<string, string> = {
  effect: "var(--chart-effect)",
  mechanism: "url(#hatch-mechanism)",
  advise: "var(--chart-advise)",
  int: "url(#hatch-int)",
  false: "var(--chart-false)",
};
const HATCHED: Record<string, string> = { mechanism: "var(--chart-mechanism)", int: "var(--chart-int)" };
const fillFor = (label: string) => CLASS_FILL[label] ?? "var(--chart-false)";

const compact = (v: number) => (v >= 1000 ? `${v / 1000}K` : String(v));
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

type Row = { name: string; label: string; split: string; value: number; plot: number };

function ChartTooltip({ active, payload }: { active?: boolean; payload?: { payload: Row }[] }) {
  if (!active || !payload?.length) return null;
  const r = payload[0].payload;
  return (
    <div className="chart-tooltip">
      <strong>{r.name}</strong>
      <div>{r.value.toLocaleString("en-US")} instances</div>
    </div>
  );
}

/** Instances per class, one bar per split and class, on a LOG axis so `int` is visible beside `false`.
 *  Each bar is labelled directly (class on the left, count at the end), so there is no legend. */
export function ClassDistributionChart({ stats }: { stats: DDIStatsResponse }) {
  const rows: Row[] = stats.splits.flatMap((s) =>
    stats.labels.map((label) => {
      const value = s.class_counts[label] ?? 0;
      return { name: `${cap(s.split)} · ${label}`, label, split: s.split, value, plot: Math.max(value, 1) };
    }),
  );
  const max = Math.max(...rows.map((r) => r.value), 10);
  const top = 10 ** Math.ceil(Math.log10(max + 1));
  const ticks: number[] = [];
  for (let t = 1; t <= top; t *= 10) ticks.push(t);

  return (
    <figure className="chart" aria-label="DDI instances per class and split on a logarithmic axis">
      <ResponsiveContainer width="100%" height={rows.length * 26 + 56}>
        <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 56, left: 4, bottom: 4 }} barCategoryGap="18%">
          <defs>
            {Object.entries(HATCHED).map(([label, color]) => (
              <pattern key={label} id={`hatch-${label}`} patternUnits="userSpaceOnUse" width="6" height="6" patternTransform="rotate(45)">
                <rect width="6" height="6" style={{ fill: color }} />
                <line x1="0" y1="0" x2="0" y2="6" strokeWidth="2.5" style={{ stroke: "rgb(var(--c-card))" }} />
              </pattern>
            ))}
          </defs>
          <CartesianGrid horizontal={false} stroke="rgb(var(--c-line))" strokeWidth={1} />
          <XAxis
            type="number"
            scale="log"
            domain={[1, top]}
            ticks={ticks}
            allowDataOverflow
            tickFormatter={compact}
            tickLine={false}
            axisLine={{ stroke: "rgb(var(--c-line))" }}
            tick={{ fill: "rgb(var(--c-muted))", fontSize: 12 }}
            label={{ value: "Instances (log scale)", position: "insideBottom", offset: -2, fill: "rgb(var(--c-muted))", fontSize: 12 }}
            height={44}
          />
          <YAxis
            type="category"
            dataKey="name"
            width={132}
            interval={0}
            tickLine={false}
            axisLine={false}
            tick={{ fill: "rgb(var(--c-soft))", fontSize: 12 }}
          />
          <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgb(var(--c-text) / 0.06)" }} />
          <Bar dataKey="plot" maxBarSize={16} radius={[0, 3, 3, 0]} isAnimationActive={false} stroke="var(--chart-edge)" strokeWidth={1}>
            {rows.map((r) => (
              <Cell key={r.name} fill={fillFor(r.label)} />
            ))}
            <LabelList
              dataKey="value"
              position="right"
              formatter={(v: number) => v.toLocaleString("en-US")}
              fill="rgb(var(--c-text))"
              fontSize={12}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </figure>
  );
}
