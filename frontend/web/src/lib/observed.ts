// Helpers for layer 1 (observed behaviour).
import type { Day, RiskFlag } from "../api";

/** Minutes from midnight (negative = evening before) as a clock time, e.g. -90 -> "22:30". */
export function fmtClock(min: number | null | undefined): string {
  if (min === null || min === undefined || !Number.isFinite(min)) return "–";
  const m = ((Math.round(min) % 1440) + 1440) % 1440;
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
}

export function fmtHours(h: number | null | undefined): string {
  if (h === null || h === undefined || !Number.isFinite(h)) return "–";
  const hh = Math.floor(h);
  const mm = Math.round((h - hh) * 60);
  return mm === 60 ? `${hh + 1} h` : mm ? `${hh} h ${String(mm).padStart(2, "0")}` : `${hh} h`;
}

/** Flag sentence: "you" in the person's own view, the name for clinicians and parents. */
export function flagSentence(f: RiskFlag, who: string | null): string {
  if (f.id === "sensitive_sites") return f.text;
  return `On ${f.count} of the last ${f.window} ${f.unit} ${who ?? "you"} ${f.phrase}.`;
}

export type RangeKey = "7" | "14" | "30" | "all" | "custom";

/** Days within the chosen range, counted back from the last day with data. */
export function inRange(days: Day[], range: RangeKey, from: string, to: string): Day[] {
  if (!days.length) return days;
  if (range === "all") return days;
  if (range === "custom") return days.filter((d) => (!from || d.date >= from) && (!to || d.date <= to));
  const n = Number(range);
  return days.slice(-n);
}
