// Helpers for layer 1 (observed behaviour).
import type { Care, Day, Observed, ObservedTrack, RiskFlag } from "../api";
import type { IconName } from "../components/Icon";
import { fmtNum } from "./format";

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

// ---- v3: reference ranges, flag icons, percentiles ------------------------------------------


/** Value of a track in its unit: hours, clock times, minutes or counts. */
export function fmtTrack(key: string, v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "–";
  if (key === "online_hours" || key === "quiet_hours") return fmtHours(v);
  if (key === "night_minutes" || key === "quiet_start_sd7") return `${fmtNum(v, 0)} min`;
  if (key.startsWith("quiet")) return fmtClock(v);
  return fmtNum(v, 0);
}

/** Short axis name of a track chart: unit and basis (rule 5); the track's name is the row title. */
export function trackAxis(t: Pick<ObservedTrack, "key" | "label" | "unit">): [string, string] {
  switch (t.key) {
    case "online_hours": return ["hours", "per day"];
    case "quiet_hours": return ["hours", "per night"];
    case "night_minutes": return ["minutes", "00–06"];
    case "chat_sessions": return ["count", "per day"];
    case "sites": return ["count", "per day"];
    case "quiet_start_sd7": return ["minutes", "SD, 7 nights"];
    case "sensitive_days": return ["visits", "yes / no"];
    default: return [t.label.toLowerCase(), t.unit === "time" ? "clock time" : t.unit];
  }
}

export type Range = { lo: number; mid: number; hi: number };
export type Typical = Range & {
  source: "pooled" | "external"; label: string; citation?: string; proxyNote?: string; percentiles: boolean;
};

/** The person's own usual range: mean ± 1 SD of the usual weeks. */
export function usualRange(obs: Observed | undefined, key: string): Range | null {
  const u = obs?.usual?.[key];
  if (!u || !Number.isFinite(u.mean)) return null;
  // durations and counts cannot be negative; clock times (minutes from midnight) can
  const lo = key === "quiet_start" || key === "quiet_end" ? u.mean - u.sd : Math.max(0, u.mean - u.sd);
  return { lo, mid: u.mean, hi: u.mean + u.sd };
}

/** The typical range: P16–P84 from the v3 reference (K1), else the v2 pooled mean ± 1 SD. */
export function typicalRange(obs: Observed | undefined, key: string): Typical | null {
  const ref = obs?.reference;
  if (!ref) return null;
  const t = ref.tracks?.[key];
  if (t) {
    return {
      lo: t.p16, mid: t.p50, hi: t.p84, source: ref.source ?? "pooled", percentiles: true,
      label: ref.label ?? "typical range", citation: t.citation, proxyNote: t.proxy_note,
    };
  }
  const s = ref.stats?.[key];
  if (!s) return null;
  return {
    lo: s.mean - s.sd, mid: s.mean, hi: s.mean + s.sd, source: "pooled", percentiles: false,
    label: ref.label ?? `typical (other people's usual weeks${ref.n_days ? `, ${ref.n_days} days` : ""})`,
  };
}

/** Everyday direction words per track, for percentiles: [higher, lower, unit of reference]. */
const PCT_WORDS: Record<string, [string, string, string]> = {
  quiet_start: ["later", "earlier", "nights"],
  quiet_end: ["later", "earlier", "nights"],
  quiet_hours: ["longer", "shorter", "nights"],
  online_hours: ["more", "less", "days"],
  night_minutes: ["more", "less", "nights"],
  chat_sessions: ["more", "fewer", "days"],
  sites: ["more", "fewer", "days"],
  quiet_start_sd7: ["more irregular", "more regular", "weeks"],
};

/** "later than 85 % of reference nights" (percentile 0–100 within the reference). */
export function percentileText(key: string, p: number | null | undefined): string | null {
  if (p === null || p === undefined || !Number.isFinite(p)) return null;
  const [up, down, unit] = PCT_WORDS[key] ?? ["higher", "lower", "days"];
  const q = Math.round(p);
  return q >= 50 ? `${up} than ${q} % of reference ${unit}` : `${down} than ${100 - q} % of reference ${unit}`;
}

/** Replaces the v2 wording "healthy people" with "typical" (D1) in texts from the backend. */
export function typicalWording(s: string): string {
  return s.replace(/than healthy people usually do/g, "than is typical").replace(/than healthy people/g, "than typical").replace(/healthy people/g, "the typical range")
    .replace(/healthy reference/gi, "typical range");
}

/** Fixed icon per flag (rule 6): crisis/self-harm sites are the only alert. */
const TRACK_ICON: Record<string, IconName> = {
  quiet_start: "moon", quiet_end: "sunrise", quiet_hours: "moon", online_hours: "clock", night_minutes: "night-use",
  chat_sessions: "chat", sites: "globe", sensitive_days: "alert", quiet_start_sd7: "irregular",
};
const ICONS = new Set<string>(["moon", "sunrise", "clock", "night-use", "chat", "globe", "alert", "irregular", "change",
  "note", "explain", "away", "phone", "laptop", "person", "data", "lock"]);

export function flagKind(f: RiskFlag): "alert" | "risk" | "change" {
  if (f.sensitive || f.id === "sensitive_sites") return "alert";
  return f.kind === "change" ? "change" : "risk";
}

export function flagIcon(f: RiskFlag): IconName {
  if (flagKind(f) === "alert") return "alert";
  if (f.icon && ICONS.has(f.icon) && f.icon !== "alert") return f.icon as IconName;
  if (f.id === "irregular_nights") return "irregular";
  if (flagKind(f) === "change") return "change";
  return TRACK_ICON[f.track] ?? "data";
}

export function trackIcon(key: string): IconName {
  return TRACK_ICON[key] ?? "data";
}

/** Care-plan purpose (K5): which comparison comes first. Null = the v2 order. */
export function carePurpose(care: Care | undefined | null): "assessment" | "treatment" | null {
  const p = care?.purpose ?? (care?.clinical as { purpose?: string } | null | undefined)?.purpose;
  return p === "assessment" || p === "treatment" ? p : null;
}

/** The last n days, newest first (week table, person timeline). */
export function lastDays(days: Day[], n: number): Day[] {
  return days.slice(-n).reverse();
}
