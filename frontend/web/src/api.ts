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
  // clinicians and parents only:
  observability?: Record<CritKey, Observability>;
  risk_criteria?: Record<string, CritKey[]>;
  risks?: { id: string; title: string; track: string }[];
}

export type Role = "single" | "multi";
export interface Me { username: string; role: Role; profiles: string[] }

export interface ProfileListItem {
  id: string; name: string; condition: string; source: string; scripted: boolean;
  first_day: string | null; last_day: string | null; n_days: number;
  config: Profile;
  attention?: ProfileAttention;   // added by the backend (v3); absent until then
}

/** What needs a clinician's look per person: new flags, and whether crisis/self-harm sites appeared. */
export interface ProfileAttention { flags: number; alert: boolean }

export interface DeviceRef { ip: string; label: string }

/** A person: a name, a traffic source, and their devices (or all devices of the source). */
export interface Profile {
  id: string; name: string; source: string; all_devices: boolean; devices: DeviceRef[];
  baseline_first: string | null; baseline_last: string | null; persona: string | null; view_key: string;
  reference: "none" | "baseline" | "all" | null; reference_mode: "none" | "baseline" | "all";
}

export interface Source { source: string; n_days: number; first_day: string | null; last_day: string | null; has_plan: boolean }

export interface SourceDevice {
  ip: string; packets: number; days: number; last_seen: string | null;
  label: string; role: string; assigned_to: string[];
}

export interface ProfileBody {
  id?: string; name: string; source: string; all_devices: boolean; devices: DeviceRef[];
  baseline_first: string | null; baseline_last: string | null;
  reference?: "none" | "baseline" | "all" | null;
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
  observed?: DayObserved | null;
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

/** Layer 1: what the network saw on a day (times in minutes from midnight; negative = evening before). */
export interface DayObserved {
  quiet_start: number | null; quiet_end: number | null; quiet_hours: number | null;
  online_hours: number | null; night_minutes: number | null;
  chat_sessions: number | null; sites: number | null;
  active_hourly: number[] | null;     // minutes in use per hour
  has_data: boolean;
  deviation: Record<string, number | null>;   // z against the person's usual range
  deviation_ref?: Record<string, number | null>;   // z against the healthy reference (clinicians and parents)
  sensitive?: { metric: string; label: string; value: number | null }[];   // clinicians and parents only
  sensitive_days?: number;
  percentile_ref?: Record<string, number | null>;   // v3 (K1): position in the typical range, 0–100, per track
}

export interface ObservedTrack {
  key: string; label: string; unit: string; sensitive: boolean;
  risk: number[];          // direction(s) that count as a risk: 1 higher than usual, -1 lower
}
export interface RiskFlag {
  id: string; title: string; track: string; direction: number; days: string[]; count: number;
  window: number; unit: string; phrase: string; text: string; sensitive: boolean; names?: string[];
  basis: "own" | "reference";     // compared with the person's usual weeks, or with healthy people
  kind?: "risk" | "change";       // v3 (K1): change = notable change in the other direction, "to discuss"
  icon?: string;                  // v3 (K1): one of the Icon names
}
/** v3 (K1): typical range per track as percentiles (P16–P84 = central 68 %). */
export interface ReferenceTrack { p16: number; p50: number; p84: number; n?: number; citation?: string; proxy_note?: string }
export interface Observed {
  tracks: ObservedTrack[];
  usual: Record<string, { mean: number; sd: number; n: number }>;
  // v2: stats (mean ± SD of the pooled reference); v3 (K1): source, label, tracks (percentiles)
  reference: {
    stats?: Record<string, { mean: number; sd: number; n: number }>; n_days?: number; people?: string[];
    source?: "pooled" | "external"; label?: string; tracks?: Record<string, ReferenceTrack>;
  } | null;
  flags: RiskFlag[];
  params: { active_packets: number; deviation_z: number; flag_days: number; flag_window: number;
    sensitive_window: number; night_from_hour: number; night_to_hour: number };
}

export interface Note { id: string; date: string; text: string; author: string; created: string }

export type DayType = "away" | "home" | "free";
export const WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;
export type Weekday = typeof WEEKDAYS[number];
export interface NamedDevice { id?: string; name: string; kind: string; shared: boolean; ip?: string | null }
/** The patient's routine (onboarding, changeable later). */
export type Half = "am" | "pm";
/** One weekday: the morning (until about noon) and the afternoon. */
export type HalfDays = Record<Half, DayType>;
export interface Routine {
  week: Record<Weekday, HalfDays>;
  away_from: string | null; away_to: string | null;
  bedtime: string | null; wake: string | null; bedtime_free: string | null; wake_free: string | null;
  devices: NamedDevice[]; note: string;
}
export interface AwayPeriod { id?: string; from: string; to: string; reason: string }
export type Sensitivity = "strict" | "standard" | "relaxed";
/** The clinician's setup (clinicians and parents only). */
export interface Clinical {
  history: string; concerns: string; treatment: string; criteria: CritKey[];
  focus: Record<string, { enabled: boolean; sensitivity: Sensitivity }>;
  normals: Record<string, { min: number | null; max: number | null }>;
}
export interface Care {
  purpose?: "assessment" | "treatment";   // v3 (K5): which comparison the overview shows first
  routine: Routine | null; away_periods: AwayPeriod[]; clinical: Clinical | null;
  updated: Record<string, { by: string; at: string }>;
}
export interface FocusSuggestion {
  criteria: { criterion: CritKey; priority: "high" | "medium" | "low"; reason: string }[];
  risks: { id: string; enabled: boolean; sensitivity: Sensitivity; reason: string }[];
  caveats: string[];
}
export interface Observability { level: "good" | "partial" | "none"; observes: string; cannot: string; caveats: string[]; scored: boolean }
export type SeenMarks = Record<string, { last_day: string; by: string; at: string }>;

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
  observed?: Observed;
  notes?: Note[];            // clinicians and parents only
  care?: Care;
  seen?: SeenMarks;          // flags marked as seen (clinicians and parents only)
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
  model?: string; default_model?: string; has_key?: boolean;
}
export interface AssistantSettingsBody { enabled: boolean; model: string; api_key?: string | null }
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

export interface SpeechStatus { available: boolean; max_seconds?: number }
export interface Transcript { text: string; language?: string | null; seconds?: number | null }

/** Send a recording to the local speech-to-text service (Whisper on the portal's own machine). */
async function transcribe(audio: Blob): Promise<Transcript> {
  const r = await fetch("/api/transcribe", {
    method: "POST", credentials: "same-origin",
    headers: { "Content-Type": audio.type || "audio/webm" }, body: audio,
  });
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`;
    try { const d = (await r.json()).detail; if (typeof d === "string") msg = d; } catch { /* not JSON */ }
    if (r.status === 401) onUnauthorized();
    throw new ApiError(r.status, msg);
  }
  return r.json() as Promise<Transcript>;
}

export const api = {
  speechStatus: () => get<SpeechStatus>("/api/transcribe"),
  transcribe,
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
  putRoutine: (id: string, routine: Routine) => call<Care>("PUT", `/api/profiles/${enc(id)}/care/routine`, { routine }),
  putAway: (id: string, away_periods: AwayPeriod[]) => call<Care>("PUT", `/api/profiles/${enc(id)}/care/away`, { away_periods }),
  putClinical: (id: string, clinical: Clinical) => call<Care>("PUT", `/api/profiles/${enc(id)}/care/clinical`, { clinical }),
  suggestRoutine: (id: string, text: string) => call<{ routine: Routine }>("POST", `/api/profiles/${enc(id)}/setup-suggestion`, { kind: "routine", text }),
  suggestFocus: (id: string, text: string) => call<{ focus: FocusSuggestion }>("POST", `/api/profiles/${enc(id)}/setup-suggestion`, { kind: "focus", text }),
  addNote: (id: string, date: string, text: string) => call<{ notes: Note[] }>("POST", `/api/profiles/${enc(id)}/notes`, { date, text }),
  deleteNote: (id: string, noteId: string) => call<{ notes: Note[] }>("DELETE", `/api/profiles/${enc(id)}/notes/${enc(noteId)}`),
  markSeen: (id: string, flag: string, lastDay: string) => call<{ seen: SeenMarks }>("PUT", `/api/profiles/${enc(id)}/flags/${enc(flag)}/seen`, { last_day: lastDay }),
  unmarkSeen: (id: string, flag: string) => call<{ seen: SeenMarks }>("DELETE", `/api/profiles/${enc(id)}/flags/${enc(flag)}/seen`),
  createProfile: (b: ProfileBody) => call<Profile & { pending: boolean }>("POST", "/api/profiles", b),
  updateProfile: (id: string, b: ProfileBody) => call<Profile & { pending: boolean }>("PUT", `/api/profiles/${enc(id)}`, b),
  deleteProfile: (id: string) => call<{ ok: boolean }>("DELETE", `/api/profiles/${enc(id)}`),
};
