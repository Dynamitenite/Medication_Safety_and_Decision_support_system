import type { CourseIn } from "./api";

/** One medicine in the "To add" list. Course fields are strings as typed; empty means not entered. */
export type ToAddItem = {
  id: string; // catalogue id
  name: string;
  manufacturer: string | null;
  composition: string;
  source: "typed" | "scanned";
  raw?: string; // the scanned line it came from
  reason: string;
  dose: string;
  frequency: string;
  food: string;
  start_date: string;
  end_mode: "duration" | "end";
  duration_days: string;
  end_date: string;
};

export const emptyCourse = {
  reason: "",
  dose: "",
  frequency: "",
  food: "",
  start_date: "",
  end_mode: "duration" as const,
  duration_days: "",
  end_date: "",
};

export const todayIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

/** Add whole days to an ISO date, in UTC so the time zone cannot shift the day. */
export function addDays(iso: string, days: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10);
}

export const durationOf = (it: ToAddItem): number | null => {
  const n = Number(it.duration_days);
  return it.end_mode === "duration" && it.duration_days.trim() && Number.isInteger(n) && n >= 1 ? n : null;
};

/** The course as the server takes it. The server fills today as the start when none is given. */
export function toCourse(it: ToAddItem): CourseIn {
  return {
    catalogue_id: it.id,
    reason: it.reason.trim() || null,
    dose: it.dose.trim() || null,
    frequency: it.frequency.trim() || null,
    food: it.food.trim() || null,
    start_date: it.start_date || null,
    end_date: it.end_mode === "end" && it.end_date ? it.end_date : null,
    duration_days: durationOf(it),
    source: it.source,
  };
}
