import type { Config } from "../api";

/** A readable name for a metric code without a label: never show the code itself. */
export function readable(code: string): string {
  let core = code.replace(/^(C\d_)?F\d+_/, "");
  let unit = "";
  const m = core.match(/(Sec|Min|Bps|Bytes|Hours)$/);
  if (m) {
    unit = ({ Sec: " (s)", Min: " (min)", Bps: "", Bytes: "", Hours: " (h)" } as Record<string, string>)[m[1]];
    core = core.slice(0, m.index);
  }
  const words = core.replace(/(?<=[a-z0-9])(?=[A-Z])|_/g, " ").trim().toLowerCase();
  return words ? words[0].toUpperCase() + words.slice(1) + unit : code;
}

/** The plain-language name of a metric (from the server's labels, else built from the code). */
export function metricName(code: string, cfg: Pick<Config, "metric_labels">): string {
  return cfg.metric_labels[code] ?? readable(code);
}

/** Site groups whose daily number is counted as visits (not packets). */
export const SITE_GROUP_OF: Record<string, string> = {
  C9_F1_CrisisLineHits: "crisis", C9_F3_TherapyBookingVisits: "therapy",
  C7_F1_MentalHealthSiteVisitsDay: "mental_health", C7_F4_HelpTherapyLookupHits: "therapy",
};

export type SiteVisits = { visits: number; starts: string[]; minutes: number };

/** "2 visits (23:40, 23:58), about 3 min" */
export function visitText(v: SiteVisits | null | undefined): string {
  if (!v || !v.visits) return "no visits";
  return `${v.visits} visit${v.visits === 1 ? "" : "s"} (${v.starts.join(", ")}), about ${v.minutes} min`;
}
