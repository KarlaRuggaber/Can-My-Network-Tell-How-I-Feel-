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

export type Role = "single" | "multi";
export interface Me { username: string; role: Role; profiles: string[] }

export interface ProfileListItem {
  id: string; name: string; condition: string; source: string; scripted: boolean;
  first_day: string | null; last_day: string | null; n_days: number;
  config: Profile;
}

export interface DeviceRef { ip: string; label: string }

/** A person: a name, a traffic source, and their devices (or all devices of the source). */
export interface Profile {
  id: string; name: string; source: string; all_devices: boolean; devices: DeviceRef[];
  baseline_first: string | null; baseline_last: string | null; persona: string | null; view_key: string;
}

export interface Source { source: string; n_days: number; first_day: string | null; last_day: string | null; has_plan: boolean }

export interface SourceDevice {
  ip: string; packets: number; days: number; last_seen: string | null;
  label: string; role: string; assigned_to: string[];
}

export interface ProfileBody {
  id?: string; name: string; source: string; all_devices: boolean; devices: DeviceRef[];
  baseline_first: string | null; baseline_last: string | null;
}

export type Expectation = "present" | "no" | "elevated" | "borderline" | "flag";
export interface PersonaMeta {
  id: string; source: string; scripted: boolean;
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
  ground_truth: GroundTruthSummary | null;   // only for scripted sources
  metrics: Record<string, number | string | boolean | null>;
  hourly: number[] | null;   // packets per hour of the day
  L: Record<CritKey, number | null>;
  parts: Partial<Record<CritKey, Record<string, MetricPart>>>;
}

/** "current" = the clinical phase of a scripted run, or the recent days of live traffic. */
export type PhaseKey = "baseline" | "current";

export interface PhaseInfo {
  days: number; n_phase_days: number; total_present: number; core_present: boolean; episode: boolean;
  criteria: Partial<Record<CritKey, { days_over: number; present: boolean }>>;
  planned_first: string | null; planned_last: string | null; planned_days: number;
  counted: string[]; in_progress: string[];
}

export interface Timeline {
  profile: Profile & { has_plan: boolean; phase_labels: Record<PhaseKey, string> };
  persona: PersonaMeta;
  status: "ready" | "pending";
  days: Day[];
  gate: {
    params: { theta: number; N: number; M: number; core: string[]; min_present: number };
    /** Per-phase gate with the configured parameters (the UI recomputes it for its sliders). */
    phases: Record<PhaseKey, PhaseInfo>;
    /** Rolling window over the last M days: optional extra view, mixes phases. */
    rolling: { present: Partial<Record<CritKey, boolean[]>>; episode: boolean[]; note: string };
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
  profile: string; date: string;
  activity: { bin_minutes: number; total: number[]; devices: Record<string, number[]> } | null;
  blocks: Block[];
  packets_raw: number; packets_kept: number; n_partitions: number;
  last_partition_start: string | null;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

/** Called when the session is gone (401), so the app can show the login again. */
let onUnauthorized: () => void = () => undefined;
export const setUnauthorizedHandler = (f: () => void) => { onUnauthorized = f; };

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(path, {
    method, credentials: "same-origin",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`;
    try { const d = (await r.json()).detail; msg = typeof d === "string" ? d : JSON.stringify(d); } catch { /* not JSON */ }
    if (r.status === 401 && path !== "/api/login") onUnauthorized();
    throw new ApiError(r.status, msg);
  }
  return r.json() as Promise<T>;
}
const get = <T,>(path: string) => call<T>("GET", path);
const enc = encodeURIComponent;

export interface AssistantStatus {
  enabled: boolean; notice: string;
  // multi-profile users only:
  provider?: string; model?: string; has_key?: boolean;
  providers?: Record<string, { label: string; default_model: string }>;
}
export interface AssistantSettingsBody { enabled: boolean; provider: string; model: string; api_key?: string | null }
export interface ChatTurn { role: "user" | "assistant"; content: string }

/** Ask the explanation assistant; calls onText for every streamed chunk. */
async function ask(id: string, messages: ChatTurn[], focus: string | null, onText: (t: string) => void): Promise<void> {
  const r = await fetch(`/api/profiles/${encodeURIComponent(id)}/assistant`, {
    method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages, focus }),
  });
  if (!r.ok || !r.body) {
    let msg = `${r.status} ${r.statusText}`;
    try { const d = (await r.json()).detail; msg = typeof d === "string" ? d : msg; } catch { /* not JSON */ }
    if (r.status === 401) onUnauthorized();
    throw new ApiError(r.status, msg);
  }
  const reader = r.body.getReader();
  const dec = new TextDecoder();
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    onText(dec.decode(value, { stream: true }));
  }
}

export const api = {
  assistant: () => get<AssistantStatus>("/api/assistant"),
  saveAssistant: (b: AssistantSettingsBody) => call<AssistantStatus>("PUT", "/api/assistant", b),
  ask,
  login: (username: string, password: string) => call<Me>("POST", "/api/login", { username, password }),
  logout: () => call<{ ok: boolean }>("POST", "/api/logout"),
  me: () => get<Me>("/api/me"),
  config: () => get<Config>("/api/config"),
  profiles: () => get<ProfileListItem[]>("/api/profiles"),
  timeline: (id: string) => get<Timeline>(`/api/profiles/${enc(id)}`),
  day: (id: string, day: string) => get<DayDetail>(`/api/profiles/${enc(id)}/days/${day}`),
  sources: () => get<Source[]>("/api/sources"),
  sourceDevices: (source: string) => get<SourceDevice[]>(`/api/sources/${enc(source)}/devices`),
  createProfile: (b: ProfileBody) => call<Profile & { pending: boolean }>("POST", "/api/profiles", b),
  updateProfile: (id: string, b: ProfileBody) => call<Profile & { pending: boolean }>("PUT", `/api/profiles/${enc(id)}`, b),
  deleteProfile: (id: string) => call<{ ok: boolean }>("DELETE", `/api/profiles/${enc(id)}`),
};
