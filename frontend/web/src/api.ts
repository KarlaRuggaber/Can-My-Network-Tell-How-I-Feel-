// Types and fetchers for the backend API (frontend/backend/cmn_frontend/api.py).

export type CritKey = "C1" | "C2" | "C3" | "C4" | "C5" | "C6" | "C7" | "C8" | "C9";
export const CRIT_KEYS: CritKey[] = ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9"];

export interface MfSpec { type: string; lo: number; mid: number; hi: number; invert?: boolean }
export interface MetricSpec { w: number; mf: MfSpec; bom?: string }

export interface Config {
  M: number; N: number; theta: number; tau: number; core: string[];
  criteria: Record<CritKey, Record<string, MetricSpec>>;
  criterion_names: Record<CritKey, string>;
  metric_labels: Record<string, string>;
  metric_criterion: Record<string, CritKey>;
  fasl_config_path: string;
}

export interface PersonaListItem {
  dataset: string; name: string; condition: string;
  first_day: string; last_day: string; n_days: number;
}

export type Expectation = "present" | "no" | "elevated" | "borderline" | "flag";
export interface PersonaMeta {
  name: string; condition: string; profile: string | null; baseline_profile: string | null;
  summary: string;
  expected: Partial<Record<CritKey, { present: Expectation; note: string }>>;
  episode: { expected: string; note: string } | null;
}

export interface MetricPart { value: number | null; mu: number; w: number }

export interface GroundTruthSummary {
  n_blocks: number; n_profile_blocks: number; n_sensitive: number; n_failed: number;
  n_not_run: number; profile_blocks: Record<string, number>;
}

export interface Day {
  date: string; weekday: string; phase: string; complete: boolean;
  n_partitions: number; packets_kept: number;
  first_packet: string | null; last_packet: string | null; computed_at: string;
  ground_truth: GroundTruthSummary;
  metrics: Record<string, number | string | boolean | null>;
  L: Record<CritKey, number | null>;
  parts: Partial<Record<CritKey, Record<string, MetricPart>>>;
}

export interface Timeline {
  dataset: string;
  persona: PersonaMeta;
  days: Day[];
  gate: {
    params: { theta: number; N: number; M: number; core: string[]; min_present: number };
    present: Partial<Record<CritKey, boolean[]>>;
    episode: boolean[];
  };
  baseline_stats: Record<string, { mean: number; sd: number; n: number }>;
}

export interface Block {
  block_id: string; start: string; end: string; device: string; activity: string;
  profile_block: string; phase: string; plan_day: string; mix: string; flag: string;
  profile: string; companion_of: string; started_at: string | null; late_s: number | null;
  exited_at: string | null; exit_code: number | null; status: string;
}

export interface DayDetail {
  dataset: string; date: string;
  activity: { bin_minutes: number; total: number[]; devices: Record<string, number[]> } | null;
  blocks: Block[];
  packets_raw: number; packets_kept: number; n_partitions: number;
  last_partition_start: string | null;
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(path);
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`;
    try { msg = (await r.json()).detail ?? msg; } catch { /* not JSON */ }
    throw new Error(msg);
  }
  return r.json() as Promise<T>;
}

export const api = {
  config: () => get<Config>("/api/config"),
  personas: () => get<PersonaListItem[]>("/api/personas"),
  timeline: (ds: string) => get<Timeline>(`/api/personas/${encodeURIComponent(ds)}`),
  day: (ds: string, day: string) =>
    get<DayDetail>(`/api/personas/${encodeURIComponent(ds)}/days/${day}`),
};
