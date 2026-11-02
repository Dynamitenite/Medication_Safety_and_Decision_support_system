import { useId, useMemo, useState } from "react";
import { fmtDate, fmtDuration } from "../../format";
import { layoutTimeline, type Bar, type TimelineInput } from "../../viz/timeline";
import { useWidth } from "./ChartFrame";

/** Outcome styles. Colour is never alone: each outcome has a text label, and the fill pattern differs too. */
export type OutcomeStyle = { label: string; tone: "mint" | "rose" | "amber" | "grey"; pattern: "solid" | "hatch" | "dashed"; shape: "check" | "plus" | "alert" | "stop" | "arrow" | "unknown" };

export const MEDICINE_OUTCOME_STYLE: Record<string, OutcomeStyle> = {
  cured: { label: "Cured", tone: "mint", pattern: "solid", shape: "check" },
  improved: { label: "Improved", tone: "mint", pattern: "hatch", shape: "plus" },
  not_cured: { label: "Not cured", tone: "rose", pattern: "solid", shape: "alert" },
  stopped: { label: "Stopped", tone: "amber", pattern: "hatch", shape: "stop" },
  unknown: { label: "Outcome not known", tone: "grey", pattern: "dashed", shape: "unknown" },
  ongoing: { label: "Ongoing", tone: "grey", pattern: "solid", shape: "arrow" },
};
export const CONDITION_OUTCOME_STYLE: Record<string, OutcomeStyle> = {
  cured: MEDICINE_OUTCOME_STYLE.cured,
  ongoing: MEDICINE_OUTCOME_STYLE.ongoing,
  not_cured: MEDICINE_OUTCOME_STYLE.not_cured,
  unknown: MEDICINE_OUTCOME_STYLE.unknown,
};

const TONE = { mint: "var(--c-mint)", rose: "var(--c-rose)", amber: "var(--c-amber)", grey: "var(--c-subtle)" } as const;

function Swatch({ s }: { s: OutcomeStyle }) {
  const color = `rgb(${TONE[s.tone]})`;
  return <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true" focusable="false" className="outcome-glyph" style={{ color }}>
    {s.shape === "check" && <><circle cx="9" cy="9" r="7"/><path d="m5.5 9 2.2 2.2 4.8-5"/></>}
    {s.shape === "plus" && <><circle cx="9" cy="9" r="7"/><path d="M9 5v8M5 9h8"/></>}
    {s.shape === "alert" && <><path d="M9 2 16 15H2z"/><path d="M9 6v4M9 12.5v.1"/></>}
    {s.shape === "stop" && <><rect x="3" y="3" width="12" height="12" rx="2"/><path d="M6 9h6"/></>}
    {s.shape === "arrow" && <><path d="M2 9h12M10 5l4 4-4 4"/></>}
    {s.shape === "unknown" && <><circle cx="9" cy="9" r="7" strokeDasharray="2 2"/><path d="M7 7a2 2 0 1 1 2.7 1.9c-.5.2-.7.6-.7 1.1M9 12.8v.1"/></>}
  </svg>;
}

function paint(s: OutcomeStyle, pid: string) {
  const c = `rgb(${TONE[s.tone]})`;
  if (s.pattern === "solid") return { fill: c, stroke: c, strokeWidth: 1.5 };
  if (s.pattern === "hatch") return { fill: `url(#${pid}-${s.tone})`, stroke: c, strokeWidth: 1.5 };
  return { fill: `rgb(${TONE.grey} / 0.12)`, stroke: c, strokeWidth: 1.5, strokeDasharray: "4 3" };
}

const clip = (s: string, n: number) => (s.length > n ? `${s.slice(0, Math.max(n - 1, 1))}…` : s);

/** Text for a bar: the dates, the length and the outcome. Used for the aria-label and the detail line. */
export function barText(b: Bar, styles: Record<string, OutcomeStyle>): string {
  const o = styles[b.outcome]?.label ?? b.outcome;
  const when = b.ongoing ? `since ${fmtDate(b.start)}, still going` : b.end ? `${fmtDate(b.start)} to ${fmtDate(b.end)}` : `${fmtDate(b.start)}, no end date`;
  return `${b.label}: ${when}, ${fmtDuration(b.days)}${b.ongoing ? " so far" : ""}. ${o}${b.upcoming ? ". Starts in the future" : ""}.`;
}

const ROW = 46;
const TOP = 30;

/** Horizontal Gantt-style bars, one row per item, with a "today" line. Items with no start date are
 *  listed under the chart. Each bar can be focused; its details show under the chart. */
export function TimelineChart({ items, styles, today, noun }: { items: TimelineInput[]; styles: Record<string, OutcomeStyle>; today: string; noun: string }) {
  const [wrap, width] = useWidth<HTMLDivElement>();
  const pid = useId().replace(/:/g, "");
  const layout = useMemo(() => layoutTimeline(items, today), [items, today]);
  const [sel, setSel] = useState<string | null>(null);
  const W = Math.max(width, 280);
  const padL = 8;
  const padR = 22; // room for the arrow of an ongoing bar
  const inner = W - padL - padR;
  const xp = (f: number) => padL + f * inner;
  const H = TOP + layout.bars.length * ROW + 8;
  const used = [...new Set(layout.bars.map((b) => b.outcome))];
  const chosen = layout.bars.find((b) => b.id === sel) ?? null;
  const maxChars = Math.floor(inner / 7);

  return (
    <div className="timeline">
      <div ref={wrap} className="timeline-svg">
        {layout.bars.length === 0 ? (
          <p className="muted">No {noun} with a start date to draw.</p>
        ) : (
          <svg width={W} height={H} role="group" aria-label={`Timeline of ${layout.bars.length} ${noun}`} focusable="false">
            <defs>
              {(["mint", "amber", "rose", "grey"] as const).map((t) => (
                <pattern key={t} id={`${pid}-${t}`} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                  <rect width="6" height="6" fill={`rgb(${TONE[t]} / 0.18)`} />
                  <line x1="0" y1="0" x2="0" y2="6" stroke={`rgb(${TONE[t]})`} strokeWidth="2" />
                </pattern>
              ))}
            </defs>
            {layout.ticks.map((k) => (
              <g key={k.label} className="tl-tick">
                <line x1={xp(k.x)} x2={xp(k.x)} y1={TOP - 6} y2={H - 4} />
                <text x={xp(k.x)} y={TOP - 12} textAnchor="middle">
                  {k.label}
                </text>
              </g>
            ))}
            <g className="tl-today">
              <line x1={xp(layout.todayX)} x2={xp(layout.todayX)} y1={TOP - 6} y2={H - 4} />
              <text x={xp(layout.todayX)} y={10} textAnchor={layout.todayX > 0.9 ? "end" : layout.todayX < 0.08 ? "start" : "middle"}>
                Today
              </text>
            </g>
            {layout.bars.map((b, i) => {
              const s = styles[b.outcome] ?? styles.unknown;
              const y = TOP + i * ROW;
              const x0 = xp(b.x0);
              const x1 = xp(b.x1);
              const h = 16;
              const by = y + 20;
              const label = barText(b, styles);
              const pick = () => setSel(b.id);
              return (
                <g
                  key={b.id}
                  className={`tl-bar${sel === b.id ? " sel" : ""}`}
                  tabIndex={0}
                  role="button"
                  aria-label={`${clip(b.label, maxChars - 22)}${s.label} · ${b.days} ${b.days === 1 ? "day" : "days"}`}
                  aria-description={label}
                  aria-pressed={sel === b.id}
                  onClick={pick}
                  onFocus={pick}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      pick();
                    }
                  }}
                >
                  <text aria-hidden="true" className="tl-label" x={padL} y={y + 14}>
                    {clip(b.label, maxChars - 22)}
                    <tspan className="tl-sub" dx="8">
                      {s.label}
                      {" · "}
                      {b.days} {b.days === 1 ? "day" : "days"}
                    </tspan>
                  </text>
                  <rect className="tl-hit" x={padL} y={y + 2} width={inner + padR} height={ROW - 4} />
                  <rect className="tl-rect" x={x0} y={by} width={Math.max(x1 - x0, 4)} height={h} rx={3} {...paint(s, pid)} />
                  {b.ongoing && <path className="tl-arrow" d={`M${x1 + 2} ${by - 1} L${x1 + 12} ${by + h / 2} L${x1 + 2} ${by + h + 1} Z`} fill={`rgb(${TONE[s.tone]})`} />}
                </g>
              );
            })}
          </svg>
        )}
      </div>
      <p className="small tl-detail" role="status" aria-live="polite">
        {chosen ? barText(chosen, styles) : layout.bars.length > 0 ? "Select a bar to see its dates." : ""}
      </p>
      {used.length > 0 && (
        <ul className="tl-legend small" aria-label="Outcome key">
          {used.map((k) => (
            <li key={k}>
              <Swatch s={styles[k] ?? styles.unknown} />
              {(styles[k] ?? styles.unknown).label}
            </li>
          ))}
          {layout.bars.some((b) => b.ongoing) && <li><span className="tl-arrow-key" aria-hidden="true" />Arrow: still going</li>}
          <li><span className="tl-today-key" aria-hidden="true" />Today</li>
        </ul>
      )}
      {layout.undated.length > 0 && (
        <div className="tl-undated">
          <h4>Dates not entered</h4>
          <p className="small muted">These have no start date, so they cannot be placed on the timeline.</p>
          <ul className="small">
            {layout.undated.map((u) => (
              <li key={u.id}>
                {u.label}
                <span className="muted"> · {(styles[u.outcome] ?? styles.unknown).label}</span>
                {u.end && <span className="muted"> · ended {fmtDate(u.end)}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/** The same rows as a table. */
export function TimelineTable({ items, styles, today, caption }: { items: TimelineInput[]; styles: Record<string, OutcomeStyle>; today: string; caption: string }) {
  const layout = useMemo(() => layoutTimeline(items, today), [items, today]);
  const rows = [...layout.bars.map((b) => ({ id: b.id, label: b.label, start: b.start, end: b.end, outcome: b.outcome, days: b.days as number | null, ongoing: b.ongoing })), ...layout.undated.map((u) => ({ id: u.id, label: u.label, start: u.start, end: u.end, outcome: u.outcome, days: null, ongoing: false }))];
  return (
    <div className="table-wrap">
      <table>
        <caption>{caption}</caption>
        <thead>
          <tr>
            <th scope="col">Name</th>
            <th scope="col">Start</th>
            <th scope="col">End</th>
            <th scope="col" className="num">Days</th>
            <th scope="col">Outcome</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <th scope="row">{r.label}</th>
              <td>{r.start ? fmtDate(r.start) : "Dates not entered"}</td>
              <td>{r.end ? fmtDate(r.end) : r.ongoing ? "Ongoing" : r.start ? "No end date" : "–"}</td>
              <td className="num">{r.days ?? "–"}</td>
              <td>{(styles[r.outcome] ?? styles.unknown).label}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** A switch between two or three views of the same data. */
export function ViewSwitch<T extends string>({ label, value, options, onChange }: { label: string; value: T; options: { id: T; label: string }[]; onChange: (v: T) => void }) {
  return (
    <div className="seg-toggle" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.id} type="button" className={o.id === value ? "on" : ""} aria-pressed={o.id === value} onClick={() => onChange(o.id)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}
