import type { MedicineRecordOut } from "./api";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-03-12" -> "12 Mar 2026". Built from the parts so the time zone cannot shift the day. */
export function fmtDate(iso: string | null | undefined): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso ?? "");
  return m ? `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]} ${m[1]}` : "";
}

export function fmtDuration(days: number): string {
  if (days >= 90) return `${days} days (about ${Math.round(days / 30)} months)`;
  return `${days} ${days === 1 ? "day" : "days"}`;
}

/** The time course of a medicine as dates and as a length, or why it cannot be shown. */
export function courseText(m: Pick<MedicineRecordOut, "status" | "start_date" | "end_date" | "duration_days">): string {
  const start = fmtDate(m.start_date);
  const end = fmtDate(m.end_date);
  const len = m.duration_days != null ? fmtDuration(m.duration_days) : "";
  switch (m.status) {
    case "not_stated":
      return "Dates not given";
    case "upcoming":
      return end ? `Starts ${start} – ${end}${len ? ` · ${len}` : ""}` : `Starts ${start} · no end date`;
    case "past":
      return `${start} – ${end}${len ? ` · ${len}` : ""}`;
    default:
      return end ? `${start} – ${end}${len ? ` · ${len}` : ""}` : `Since ${start} · ongoing${len ? `, ${len} so far` : ""}`;
  }
}

export const SEX_LABEL = { female: "Female", male: "Male", other: "Other" } as const;
export const SEVERITY_LABEL = { mild: "Mild", moderate: "Moderate", severe: "Severe", unknown: "Severity not known" } as const;
export const KIND_LABEL = { illness: "Illness", surgery: "Surgery", injury: "Injury", other: "Other" } as const;
export const CONDITION_OUTCOME_LABEL = { cured: "Cured", ongoing: "Ongoing", not_cured: "Not cured", unknown: "Outcome not known" } as const;
export const MEDICINE_OUTCOME_LABEL = { cured: "Cured", improved: "Improved", not_cured: "Not cured", stopped: "Stopped", unknown: "Outcome not known" } as const;
