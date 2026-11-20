import { useEffect, useMemo, useState } from "react";
import {
  api, CRIT_KEYS, type AwayPeriod, type Care, type CarePurpose, type Clinical, type Config, type CritKey, type FocusSuggestion,
  type Routine, type Sensitivity, type SourceDevice, type Timeline,
} from "../api";
import { fmtClock, fmtHours } from "../lib/observed";
import { fmtNum } from "../lib/format";
import { AwayEditor, defaultRoutine, RoutineForm } from "./RoutineForm";
import { appendText, Dictate } from "./Dictate";

type Props = {
  tl: Timeline;
  cfg: Config;
  assistant: boolean;
  onSaved: (care: Care) => void;
  onAsk: (question: string, focus: string) => void;
};

const emptyClinical = (): Clinical => ({
  purpose: "assessment", change_flags: null, history: "", concerns: "", treatment: "", criteria: [], focus: {}, normals: {},
});

/** Why the person is monitored; decides what the overview shows first (Feedback-v3-Plan §5.2, E2). */
const PURPOSES: { id: CarePurpose; title: string; question: string; effect: string }[] = [
  { id: "assessment", title: "Assessment", question: "Where does this person stand?",
    effect: "The overview shows the comparison with the typical range first. Notable changes (improvements) are flagged, to discuss." },
  { id: "treatment", title: "Treatment monitoring", question: "How is this person changing over time?",
    effect: "The overview shows the change against the person's own usual weeks first. Notable changes (improvements) are flagged, to discuss." },
];

/** Safety signal that is never switched off (the only red risk). */
const ALWAYS_ON = new Set(["sensitive_sites"]);

/** Icon per risk, the same names the flags use (Icon contract, Feedback-v3-Plan §2). */
type IconName = "moon" | "sunrise" | "clock" | "night-use" | "chat" | "globe" | "alert" | "irregular" | "change";
const RISK_ICON: Record<string, IconName> = {
  later_nights: "moon", shorter_quiet: "moon", later_mornings: "sunrise", night_use: "night-use",
  more_use: "clock", less_use: "clock", fewer_chats: "chat", fewer_sites: "globe",
  irregular_nights: "irregular", sensitive_sites: "alert",
};
const ICON_PATH: Record<IconName, string> = {
  moon: "M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z",
  sunrise: "M4 18h16M7 18a5 5 0 0 1 10 0M12 4v4M5 9l2 2M19 9l-2 2",
  clock: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7v5l3 2",
  "night-use": "M16 13.5A6.5 6.5 0 0 1 7.5 5a6.5 6.5 0 1 0 8.5 8.5zM19 18.5a1.5 1.5 0 1 0 0 .01",
  chat: "M4 5h16v10H9l-5 4z",
  globe: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18",
  alert: "M12 3 2 20h20zM12 9v5M12 17v.01",
  irregular: "M3 12l3-5 3 10 3-10 3 10 3-10 3 5",
  change: "M5 19 19 5M10 5h9v9",
};
/** Stand-in until T0's Icon.tsx is merged: then this becomes <Icon name={name} label={label} />. */
function RiskIcon({ name, label }: { name: IconName; label: string }) {
  return (
    <svg className={`icon icon-${name}`} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" role="img" aria-label={label}
      style={{ verticalAlign: "-3px", flexShrink: 0 }}>
      <title>{label}</title><path d={ICON_PATH[name]} />
    </svg>
  );
}
const ALERT_COLOR = "var(--alert, var(--red-text))";
const LEVEL: Record<string, string> = { good: "well observable", partial: "partly observable", none: "barely observable" };
const NORMAL_TRACKS: { key: string; label: string; kind: "evening" | "morning" | "hours" | "number" }[] = [
  { key: "quiet_start", label: "Went quiet (bedtime)", kind: "evening" },
  { key: "quiet_end", label: "Back online (waking)", kind: "morning" },
  { key: "quiet_hours", label: "Quiet window (h)", kind: "hours" },
  { key: "online_hours", label: "Time in use (h)", kind: "hours" },
  { key: "night_minutes", label: "Use at night 00–06 (min)", kind: "number" },
  { key: "chat_sessions", label: "Chat sessions", kind: "number" },
  { key: "sites", label: "Different sites", kind: "number" },
];

/** Clock time <-> minutes from midnight; evening times (from 18:00) are negative (the night before). */
const toMin = (hhmm: string, kind: string) => {
  const m = Number(hhmm.slice(0, 2)) * 60 + Number(hhmm.slice(3, 5));
  return kind === "evening" && m >= 18 * 60 ? m - 1440 : m;
};
const toHHMM = (m: number | null) => (m === null ? "" : fmtClock(m));

/** Clinicians and parents: the patient's routine and devices, away periods, history, focus and normals. */
export function CarePlan({ tl, cfg, assistant, onSaved, onAsk }: Props) {
  const care = tl.care;
  const pid = tl.profile.id;
  const [routine, setRoutine] = useState<Routine>(care?.routine ?? defaultRoutine());
  const [away, setAway] = useState<AwayPeriod[]>(care?.away_periods ?? []);
  const [clinical, setClinical] = useState<Clinical>({ ...emptyClinical(), ...(care?.clinical ?? {}) });
  const [devices, setDevices] = useState<SourceDevice[] | null>(null);
  const [msg, setMsg] = useState<{ where: string; kind: "ok" | "error"; text: string } | null>(null);
  const [suggestion, setSuggestion] = useState<FocusSuggestion | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { api.sourceDevices(tl.profile.source).then(setDevices).catch(() => setDevices([])); }, [tl.profile.source]);

  const obs = cfg.observability ?? ({} as Record<CritKey, never>);
  const riskCrit = cfg.risk_criteria ?? {};
  const risks = cfg.risks ?? [];
  const effective = (id: string) => {
    const e = clinical.focus[id] ?? { enabled: true, sensitivity: "standard" as Sensitivity };
    return ALWAYS_ON.has(id) ? { ...e, enabled: true } : e;
  };
  const purpose: CarePurpose = clinical.purpose ?? "assessment";
  const changeFlags = clinical.change_flags ?? true;
  const iconFor = (r: { id: string; icon?: string }) => (r.icon ?? RISK_ICON[r.id]) as IconName | undefined;
  const linked = routine.devices.filter((d) => d.ip);
  const status = [
    { ok: !!care?.routine, text: care?.routine ? `Routine filled in (last changed by ${care.updated?.routine?.by ?? "—"})` : "Routine not filled in yet (the patient does this at first login)" },
    { ok: routine.devices.length > 0 && linked.length === routine.devices.length,
      text: routine.devices.length ? `${linked.length} of ${routine.devices.length} devices linked to the network` : "No devices named yet" },
    { ok: !!care?.clinical, text: care?.clinical ? `Clinical setup done (last changed by ${care.updated?.clinical?.by ?? "—"})` : "Clinical setup not done yet" },
  ];

  const say = (where: string, kind: "ok" | "error", text: string) => setMsg({ where, kind, text });
  const saveRoutine = async () => {
    try {
      await api.putRoutine(pid, { ...routine, devices: routine.devices.filter((d) => d.name.trim()) });
      onSaved(await api.putAway(pid, away));
      say("routine", "ok", "Routine, devices and away periods saved.");
    } catch (e) { say("routine", "error", String((e as Error).message)); }
  };
  const savePurpose = async () => {
    try {      // only the purpose: unsaved edits further down stay in the form
      const saved = { ...emptyClinical(), ...(care?.clinical ?? {}), purpose, change_flags: clinical.change_flags ?? null };
      onSaved(await api.putClinical(pid, saved));
      say("purpose", "ok", purpose === "treatment"
        ? "Purpose saved: treatment monitoring. The overview now leads with change over time."
        : "Purpose saved: assessment. The overview now leads with the comparison with the typical range.");
    } catch (e) { say("purpose", "error", String((e as Error).message)); }
  };
  const saveClinical = async () => {
    try {
      onSaved(await api.putClinical(pid, clinical));
      say("clinical", "ok", "Clinical setup saved. The overview's flags and usual ranges now follow it.");
    } catch (e) { say("clinical", "error", String((e as Error).message)); }
  };
  const useLinked = async () => {
    const p = tl.profile;
    try {
      await api.updateProfile(pid, {
        name: p.name, source: p.source, all_devices: false,
        devices: linked.map((d) => ({ ip: d.ip as string, label: d.name })),
        baseline_first: p.baseline_first, baseline_last: p.baseline_last, reference: p.reference,
      });
      say("routine", "ok", "This person is now computed on the linked devices only. The data appears after the next export run.");
    } catch (e) { say("routine", "error", String((e as Error).message)); }
  };

  const toggleCriterion = (c: CritKey) => {
    const on = clinical.criteria.includes(c);
    const criteria = on ? clinical.criteria.filter((x) => x !== c) : [...clinical.criteria, c];
    const focus = { ...clinical.focus };
    if (!on) for (const [rid, cs] of Object.entries(riskCrit)) if (cs.includes(c)) focus[rid] = { ...effective(rid), enabled: true };
    setClinical({ ...clinical, criteria, focus });
  };
  const setRisk = (id: string, patch: Partial<{ enabled: boolean; sensitivity: Sensitivity }>) =>
    setClinical({ ...clinical, focus: { ...clinical.focus, [id]: { ...effective(id), ...patch } } });
  const setNormal = (key: string, side: "min" | "max", v: number | null) => {
    const cur = clinical.normals[key] ?? { min: null, max: null };
    const next = { ...cur, [side]: v };
    const normals = { ...clinical.normals };
    if (next.min === null && next.max === null) delete normals[key]; else normals[key] = next;
    setClinical({ ...clinical, normals });
  };

  const suggest = async () => {
    setBusy(true); setSuggestion(null);
    try {
      const text = [clinical.history, clinical.concerns, clinical.treatment].filter((t) => t.trim()).join("\n\n");
      setSuggestion((await api.suggestFocus(pid, text)).focus);
    } catch (e) { say("clinical", "error", `The assistant could not suggest a focus: ${(e as Error).message}`); }
    finally { setBusy(false); }
  };
  const applySuggestion = () => {
    if (!suggestion) return;
    const focus = { ...clinical.focus };
    for (const r of suggestion.risks) focus[r.id] = { enabled: r.enabled || ALWAYS_ON.has(r.id), sensitivity: r.sensitivity };
    setClinical({ ...clinical, criteria: suggestion.criteria.filter((c) => c.priority !== "low").map((c) => c.criterion), focus });
    say("clinical", "ok", "Suggestion applied to the form. Check it, then save.");
  };

  const groupedRisks = useMemo(() => {
    const inFocus = risks.filter((r) => (riskCrit[r.id] ?? []).some((c) => clinical.criteria.includes(c)));
    return { inFocus, other: risks.filter((r) => !inFocus.includes(r)) };
  }, [risks, riskCrit, clinical.criteria]);

  const riskRow = (r: { id: string; title: string; icon?: string }) => {
    const e = effective(r.id);
    const icon = iconFor(r);
    const locked = ALWAYS_ON.has(r.id);
    return (
      <tr key={r.id} className={e.enabled ? "" : "unconfigured"}>
        <td><label className="toggle" title={locked ? "Safety signal: always on" : undefined}
          style={locked ? { color: ALERT_COLOR } : undefined}>
          <input type="checkbox" checked={e.enabled} disabled={locked} aria-label={`Flag ${r.title}`}
            onChange={(ev) => setRisk(r.id, { enabled: ev.target.checked })} />{" "}
          {icon && <RiskIcon name={icon} label={r.title} />} {r.title}
          {locked && <span className="muted small" style={{ color: "var(--text2)" }}>, always on</span>}
        </label></td>
        <td className="muted small">{(riskCrit[r.id] ?? []).join(", ")}</td>
        <td>
          <div className="seg" role="group" aria-label={`Sensitivity for ${r.title}`} title="How many days beyond the usual range it takes to flag">
            {(["strict", "standard", "relaxed"] as Sensitivity[]).map((s) => (
              <button key={s} disabled={!e.enabled} className={e.sensitivity === s ? "active" : ""} onClick={() => setRisk(r.id, { sensitivity: s })}>{s}</button>
            ))}
          </div>
        </td>
      </tr>
    );
  };

  return (
    <>
      <section className="card">
        <div className="card-head">
          <h2>Care plan for {tl.persona.name}</h2>
          <p className="sub">What this patient's monitoring looks at, what counts as normal for them, and the context the network cannot see.</p>
        </div>
        <ul className="status-list">
          {status.map((s) => <li key={s.text} className={s.ok ? "ok" : "todo"}>{s.ok ? "✓" : "○"} {s.text}</li>)}
        </ul>
      </section>

      <section className="card">
        <div className="card-head"><h2>Purpose of the monitoring</h2>
          <p className="sub">Clinicians and parents only. Decides what the overview shows first and whether notable changes are flagged.</p></div>
        {msg?.where === "purpose" && <p className={msg.kind === "error" ? "error" : "notice"}>{msg.text}</p>}
        <fieldset className="purpose-pick" style={{ border: "none", padding: 0, margin: 0, display: "grid", gap: 8 }}>
          <legend className="small muted">Purpose</legend>
          {PURPOSES.map((p) => (
            <label key={p.id} className={`crit-option ${purpose === p.id ? "on" : ""}`}>
              <input type="radio" name="care-purpose" value={p.id} checked={purpose === p.id}
                onChange={() => setClinical({ ...clinical, purpose: p.id })} />
              <span><b>{p.title}</b> — {p.question}<br /><span className="muted small">{p.effect}</span></span>
            </label>
          ))}
        </fieldset>
        <label className="toggle" style={{ marginTop: 10, display: "flex", gap: 6, alignItems: "center" }}>
          <input type="checkbox" checked={changeFlags} onChange={(e) => setClinical({ ...clinical, change_flags: e.target.checked })} />
          <RiskIcon name="change" label="Notable change" />
          Flag notable changes (improvements), to discuss
          <span className="muted small">
            {clinical.change_flags == null ? "on by default" : "set by you"}
          </span>
          {clinical.change_flags != null && (
            <button type="button" className="link small" onClick={() => setClinical({ ...clinical, change_flags: null })}>back to default</button>
          )}
        </label>
        <div className="row-actions"><button className="btn btn-primary" onClick={savePurpose}>Save purpose</button></div>
      </section>

      <section className="card">
        <div className="card-head"><h2>Routine and devices</h2>
          <p className="sub">Filled in by the patient at first login; you can complete or correct it. Usual ranges are learned per day type (away, at home, free) once there are 5 baseline days of a type.</p></div>
        {msg?.where === "routine" && <p className={msg.kind === "error" ? "error" : "notice"}>{msg.text}</p>}
        <RoutineForm profileId={pid} value={routine} onChange={setRoutine} person={false} assistant={assistant} linkOptions={devices} />
        {linked.length > 0 && tl.profile.all_devices && (
          <p className="notice">This person is currently computed on all devices of <code>{tl.profile.source}</code>.{" "}
            <button className="link" onClick={useLinked}>Compute on the {linked.length} linked device{linked.length === 1 ? "" : "s"} only</button></p>
        )}
        <AwayEditor value={away} onChange={setAway} person={false} />
        <div className="row-actions"><button className="btn btn-primary" onClick={saveRoutine}>Save routine and away periods</button></div>
      </section>

      <section className="card">
        <div className="card-head"><h2>History and focus</h2>
          <p className="sub">Clinicians and parents only; never shown to the patient. {assistant && "The assistant can suggest a focus from these notes (they are sent to Claude, Anthropic)."}</p></div>
        {msg?.where === "clinical" && <p className={msg.kind === "error" ? "error" : "notice"}>{msg.text}</p>}
        <div className="form-grid">
          <label className="field">Background and history
<span className="dictate-wrap">
              <textarea rows={4} value={clinical.history} onChange={(e) => setClinical({ ...clinical, history: e.target.value })}
                placeholder="e.g. first depressive episode in 2025, admitted to LIFE in October; sleep problems since the summer" />
              <Dictate inField onText={(t) => setClinical((c) => ({ ...c, history: appendText(c.history, t) }))} />
            </span></label>
          <label className="field">Current concerns
<span className="dictate-wrap">
              <textarea rows={4} value={clinical.concerns} onChange={(e) => setClinical({ ...clinical, concerns: e.target.value })}
                placeholder="e.g. withdrawal from friends, late nights, passive suicidal thoughts reported two weeks ago" />
              <Dictate inField onText={(t) => setClinical((c) => ({ ...c, concerns: appendText(c.concerns, t) }))} />
            </span></label>
          <label className="field">Treatment and context
<span className="dictate-wrap">
              <textarea rows={4} value={clinical.treatment} onChange={(e) => setClinical({ ...clinical, treatment: e.target.value })}
                placeholder="e.g. outpatient since 3 Nov, sertraline since 20 Oct; exams in December" />
              <Dictate inField onText={(t) => setClinical((c) => ({ ...c, treatment: appendText(c.treatment, t) }))} />
            </span></label>
        </div>
        {assistant && (
          <div className="row-actions">
            <button className="btn" onClick={suggest} disabled={busy}>{busy ? "Thinking…" : "Suggest a focus with the assistant"}</button>
          </div>
        )}
        {suggestion && (
          <div className="suggestion-box">
            <h3 className="flag-group-title">Suggested focus</h3>
            <ul>
              {suggestion.criteria.map((c) => (
                <li key={c.criterion}><b>{c.criterion} {cfg.criterion_names[c.criterion]}</b> <span className={`pill pill-${c.priority === "high" ? "neutral" : "outline"}`} title="Priority suggested by the assistant">{c.priority}</span>
                  {obs[c.criterion] && <span className={`obs obs-${obs[c.criterion].level}`}>{LEVEL[obs[c.criterion].level]}</span>} — {c.reason}</li>
              ))}
            </ul>
            {suggestion.risks.length > 0 && <p className="small"><b>Risks:</b> {suggestion.risks.map((r) => `${risks.find((x) => x.id === r.id)?.title ?? r.id} (${r.enabled ? r.sensitivity : "off"}: ${r.reason})`).join("; ")}</p>}
            {suggestion.caveats.length > 0 && <p className="small muted"><b>Caveats:</b> {suggestion.caveats.join("; ")}</p>}
            <div className="row-actions">
              <button className="btn btn-primary" onClick={applySuggestion}>Apply to the form</button>
              <button className="btn btn-quiet" onClick={() => setSuggestion(null)}>Discard</button>
            </div>
          </div>
        )}

        <h3 className="flag-group-title">Criteria in focus</h3>
        <p className="muted small">What the network can tell differs a lot between criteria; for barely observable ones, rely on questionnaires and interviews.</p>
        <div className="crit-pick">
          {CRIT_KEYS.map((c) => {
            const o = obs[c];
            return (
              <label key={c} className={`crit-option ${clinical.criteria.includes(c) ? "on" : ""}`} title={o ? `Sees: ${o.observes}. Cannot see: ${o.cannot}.` : ""}>
                <input type="checkbox" checked={clinical.criteria.includes(c)} onChange={() => toggleCriterion(c)} />
                <span><b>{c}</b> {cfg.criterion_names[c]}</span>
                {o && <span className={`obs obs-${o.level}`}>{LEVEL[o.level]}</span>}
                {o && !o.scored && <span className="tag tag-muted">not scored</span>}
                <button type="button" className="link small" onClick={(e) => { e.preventDefault(); onAsk(`What can the network tell about ${c} ${cfg.criterion_names[c]} for ${tl.persona.name}, and what can it not? Is it worth focusing on given the care plan?`, `care plan, ${c}`); }}>ask</button>
              </label>
            );
          })}
        </div>

        <h3 className="flag-group-title">Risks to flag</h3>
        <table className="risk-table">
          <thead><tr><th>Risk (flag icon)</th><th>Criteria</th><th>Sensitivity</th></tr></thead>
          <tbody>
            {groupedRisks.inFocus.map(riskRow)}
            {groupedRisks.other.length > 0 && <tr><td colSpan={3} className="muted small">Not linked to a criterion in focus:</td></tr>}
            {groupedRisks.other.map(riskRow)}
          </tbody>
        </table>
        <p className="muted small">Strict: 2 of the last 7 days beyond 1 SD. Standard: 3 of 7 beyond 1.5 SD. Relaxed: 4 of 7 beyond 2 SD.
          Each risk carries the same icon as its flag in the overview. Crisis or self-harm sites are a safety signal and stay on.</p>

        <h3 className="flag-group-title">Normal for this patient</h3>
        <p className="muted small">Optional. A range here replaces the range learned from the baseline weeks: a day outside it counts as clearly different.</p>
        <table className="normals-table">
          <thead><tr><th>Track</th><th>Usual range (learned, mean ± 1 SD)</th><th>Normal from</th><th>to</th></tr></thead>
          <tbody>
            {NORMAL_TRACKS.map((t) => {
              const n = clinical.normals[t.key] ?? { min: null, max: null };
              const u = tl.observed?.usual[t.key];
              const learned = !u ? "–" : t.kind === "evening" || t.kind === "morning" ? `${fmtClock(u.mean - u.sd)}–${fmtClock(u.mean + u.sd)}`
                : t.kind === "hours" ? `${fmtHours(u.mean - u.sd)}–${fmtHours(u.mean + u.sd)}` : `${fmtNum(u.mean - u.sd, 0)}–${fmtNum(u.mean + u.sd, 0)}`;
              const input = (side: "min" | "max") => t.kind === "evening" || t.kind === "morning"
                ? <input type="time" aria-label={`${t.label}: normal ${side === "min" ? "from" : "to"}`} value={toHHMM(n[side])} onChange={(e) => setNormal(t.key, side, e.target.value ? toMin(e.target.value, t.kind) : null)} />
                : <input type="number" aria-label={`${t.label}: normal ${side === "min" ? "from" : "to"}`} step={t.kind === "hours" ? 0.5 : 1} min={0} value={n[side] ?? ""} onChange={(e) => setNormal(t.key, side, e.target.value === "" ? null : Number(e.target.value))} />;
              return (
                <tr key={t.key}><td>{t.label}</td><td className="muted small">{learned}</td><td>{input("min")}</td><td>{input("max")}</td></tr>
              );
            })}
          </tbody>
        </table>
        <div className="row-actions"><button className="btn btn-primary" onClick={saveClinical}>Save history and focus</button></div>
      </section>
    </>
  );
}
