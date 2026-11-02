import { fmtDate } from "../../format";
import { addDays, durationOf, todayIso, type ToAddItem } from "../../toAdd";
import { dayNumber } from "../../viz/timeline";

type Course = { start: string; startGiven: boolean; end: string | null; days: number | null };

/** The course as the server will save it: start today when none is entered; the end from a duration or an end date. */
export function courseOf(it: ToAddItem): Course | null {
  const startGiven = Boolean(it.start_date);
  const start = it.start_date || todayIso();
  const dur = durationOf(it);
  const end = dur ? addDays(start, dur - 1) : it.end_mode === "end" && it.end_date ? it.end_date : null;
  if (end) {
    const a = dayNumber(start);
    const b = dayNumber(end);
    if (a == null || b == null || b < a) return null; // the form shows its own error for this
    return { start, startGiven, end, days: b - a + 1 };
  }
  return { start, startGiven, end: null, days: null };
}

/** A small bar for one medicine in the "To add" list. The bar length is the number of days, on one scale
 *  for the whole list, so two bars can be compared. No end date is drawn as an open arrow. */
export function CourseBar({ it, maxDays }: { it: ToAddItem; maxDays: number }) {
  const c = courseOf(it);
  if (!c) return null;
  const open = c.end === null;
  const pct = open ? 100 : Math.max(4, Math.round((100 * (c.days ?? 1)) / Math.max(maxDays, 1)));
  const text = open
    ? `${c.startGiven ? `From ${fmtDate(c.start)}` : "Starts today"}, no end date`
    : `${fmtDate(c.start)} to ${fmtDate(c.end)} · ${c.days} ${c.days === 1 ? "day" : "days"}`;
  return (
    <div className="course-bar" role="img" aria-label={`Course for ${it.name}: ${text}`}>
      <div className="course-track" aria-hidden="true">
        <div className={open ? "course-fill open" : "course-fill"} style={{ width: `${pct}%` }} />
      </div>
      <span className="small course-text" aria-hidden="true">
        {text}
        {!c.startGiven && !open && " (start: today)"}
      </span>
    </div>
  );
}

/** Longest known course in the list, for the shared scale. */
export const longestCourse = (items: ToAddItem[]) => Math.max(1, ...items.map((i) => courseOf(i)?.days ?? 1));
