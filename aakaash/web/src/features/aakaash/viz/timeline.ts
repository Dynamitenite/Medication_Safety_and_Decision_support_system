// Layout of the medical-history timelines. Pure logic: dates are read from their ISO parts so the time
// zone cannot move a day; `today` is passed in so the result can be tested.
export type TimelineInput = {
  id: string;
  label: string;
  start: string | null;
  end: string | null;
  /** key into the outcome list of the view (cured, improved, ...) */
  outcome: string;
  /** a course or condition that is still running: with a start date and no end date */
  openEnded: boolean;
};

export type Bar = TimelineInput & { x0: number; x1: number; ongoing: boolean; upcoming: boolean; days: number; startDay: number; endDay: number | null };
export type Tick = { x: number; label: string };
export type TimelineLayout = {
  bars: Bar[];
  /** items with no start date: listed under the chart, never drawn */
  undated: TimelineInput[];
  /** position of today, 0 to 1 (always inside the axis) */
  todayX: number;
  ticks: Tick[];
  minDay: number;
  maxDay: number;
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function dayNumber(iso: string): number | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  return m ? Math.floor(Date.UTC(+m[1], +m[2] - 1, +m[3]) / 86400000) : null;
}

const dateOf = (day: number) => new Date(day * 86400000);

function monthTicks(min: number, max: number): { day: number; label: string }[] {
  const span = max - min;
  const step = span <= 200 ? 1 : span <= 500 ? 3 : span <= 1100 ? 6 : 12; // months between ticks
  const start = dateOf(min);
  // month index counted from year 0, first tick at or after min and on a multiple of `step`
  let n = start.getUTCFullYear() * 12 + start.getUTCMonth() + 1;
  n = Math.ceil(n / step) * step;
  const out: { day: number; label: string }[] = [];
  for (let guard = 0; guard < 80; guard++, n += step) {
    const yy = Math.floor(n / 12);
    const mm = n % 12;
    const day = Math.floor(Date.UTC(yy, mm, 1) / 86400000);
    if (day > max) break;
    if (day >= min) out.push({ day, label: step >= 12 ? `${yy}` : `${MONTHS[mm]} ${yy}` });
  }
  return out;
}

export function layoutTimeline(items: TimelineInput[], today: string): TimelineLayout {
  const t = dayNumber(today) ?? 0;
  const undated: TimelineInput[] = [];
  const raw: (TimelineInput & { s: number; e: number | null })[] = [];
  for (const it of items) {
    const s = it.start ? dayNumber(it.start) : null;
    if (s == null) {
      undated.push(it);
      continue;
    }
    const e = it.end ? dayNumber(it.end) : null;
    raw.push({ ...it, s, e: e != null && e < s ? s : e });
  }
  raw.sort((a, b) => a.s - b.s || (a.e ?? Infinity) - (b.e ?? Infinity) || a.label.localeCompare(b.label));
  let min = Math.min(t, ...raw.map((r) => r.s));
  let max = Math.max(t, ...raw.map((r) => r.e ?? r.s));
  const pad = Math.max(3, Math.round((max - min) * 0.03));
  min -= pad;
  max += pad;
  if (max - min < 30) max = min + 30;
  const span = max - min;
  const x = (d: number) => (d - min) / span;
  const bars: Bar[] = raw.map((r) => {
    const ongoing = r.e == null && r.openEnded;
    const last = r.e ?? (ongoing ? Math.max(t, r.s) : r.s);
    const upcoming = r.s > t;
    return {
      id: r.id, label: r.label, start: r.start, end: r.end, outcome: r.outcome, openEnded: r.openEnded,
      x0: x(r.s), x1: Math.max(x(last), x(r.s) + 0.004), ongoing, upcoming,
      days: last - r.s + 1, startDay: r.s, endDay: r.e,
    };
  });
  return {
    bars, undated, todayX: x(t),
    ticks: monthTicks(min, max).map((k) => ({ x: x(k.day), label: k.label })),
    minDay: min, maxDay: max,
  };
}
