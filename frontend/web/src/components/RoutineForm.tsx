import { useState } from "react";
import { api, WEEKDAYS, type DayType, type Half, type HalfDays, type NamedDevice, type Routine, type SourceDevice } from "../api";
import { fmtNum } from "../lib/format";
import { appendText, Dictate } from "./Dictate";

const both = (t: DayType): HalfDays => ({ am: t, pm: t });
const week = (wd: HalfDays, we: HalfDays): Routine["week"] =>
  ({ mon: wd, tue: wd, wed: wd, thu: wd, fri: wd, sat: we, sun: we });

export const defaultRoutine = (): Routine => ({
  week: week(both("away"), both("free")),
  away_from: "08:00", away_to: "16:00", bedtime: "22:30", wake: "07:00", bedtime_free: null, wake_free: null,
  devices: [], note: "",
});

const DAY_NAMES: Record<string, string> = { mon: "Mon", tue: "Tue", wed: "Wed", thu: "Thu", fri: "Fri", sat: "Sat", sun: "Sun" };
const HALVES: Half[] = ["am", "pm"];
const HALF_NAME: Record<Half, string> = { am: "morning", pm: "afternoon" };
const TYPE_LABEL: Record<DayType, string> = { away: "Away", home: "At home", free: "Free" };
const TYPE_HINT: Record<DayType, string> = {
  away: "school, work or training away from home",
  home: "home office or online school",
  free: "weekend or day off",
};
const KINDS = ["phone", "laptop", "tablet", "computer", "console", "tv", "other"];
const PRESETS: { label: string; week: Routine["week"] }[] = [
  { label: "Mon–Fri away, weekend free", week: week(both("away"), both("free")) },
  { label: "Mon–Fri mornings away, afternoons free", week: week({ am: "away", pm: "free" }, both("free")) },
  { label: "Mon–Fri at home, weekend free", week: week(both("home"), both("free")) },
  { label: "Every day free", week: week(both("free"), both("free")) },
];

export type RoutineSection = "describe" | "week" | "times" | "devices" | "note";

/** A follow-up question from the backend (`setup_assist.missing_fields`): what the description left open. */
export type MissingQuestion = { id: string; fields: string[]; question: string };
type Suggested = Routine & { missing?: MissingQuestion[] };
const TIME_KEYS = ["away_from", "away_to", "bedtime", "wake", "bedtime_free", "wake_free"] as const;
type TimeKey = (typeof TIME_KEYS)[number];
const namedDevices = (r: Routine) => r.devices.filter((d) => d.name.trim());
const sameWeek = (a: Routine["week"], b: Routine["week"]) => JSON.stringify(a) === JSON.stringify(b);
const withoutMissing = ({ missing: _, ...r }: Suggested): Routine => r;

/**
 * Merge the form filled in from one answer into the current form. The answer's week replaces the
 * current one only if the question was about the week (otherwise it is just the default); times the
 * question asked for are taken, other times only where the form is still empty; new devices are added.
 */
export function mergeAnswer(current: Routine, answer: Routine, fields: string[]): Routine {
  const out: Routine = { ...current };
  if (fields.includes("week")) out.week = answer.week;
  for (const k of TIME_KEYS) if (answer[k] && (fields.includes(k) || !current[k])) out[k] = answer[k];
  const names = new Set(current.devices.map((d) => d.name.trim().toLowerCase()));
  out.devices = [...namedDevices(current), ...namedDevices(answer).filter((d) => !names.has(d.name.trim().toLowerCase()))];
  if (answer.note.trim() && !current.note.includes(answer.note.trim())) out.note = appendText(current.note, answer.note.trim()).slice(0, 1000);
  return out;
}

/** Whether a question is still open for the form as it is now (it may have been filled in by hand). */
export function stillOpen(q: MissingQuestion, r: Routine): boolean {
  return q.fields.some((f) => f === "week" ? sameWeek(r.week, defaultRoutine().week)
    : f === "devices" ? namedDevices(r).length === 0
    : (TIME_KEYS as readonly string[]).includes(f) ? !r[f as TimeKey] : false);
}

type Props = {
  profileId: string;
  value: Routine;
  onChange: (r: Routine) => void;
  person: boolean;                       // wording: "you" vs. the patient
  assistant: boolean;                    // the assistant can fill the form from a description
  sections?: RoutineSection[];
  linkOptions?: SourceDevice[] | null;   // clinicians and parents: link named devices to addresses
};

/** The routine: day types per weekday, usual times, devices in plain words. */
export function RoutineForm({ profileId, value, onChange, person, assistant, sections, linkOptions }: Props) {
  const show = (s: RoutineSection) => !sections || sections.includes(s);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [queue, setQueue] = useState<MissingQuestion[]>([]);   // follow-up questions not yet answered or skipped
  const [asked, setAsked] = useState(0);
  const pending = queue.filter((q) => stillOpen(q, value));
  const set = (patch: Partial<Routine>) => onChange({ ...value, ...patch });
  const hasAway = Object.values(value.week).some((d) => d.am === "away" || d.pm === "away");
  const setHalf = (d: string, h: Half, t: DayType) =>
    set({ week: { ...value.week, [d]: { ...value.week[d as keyof Routine["week"]], [h]: t } } });
  const setDevice = (i: number, patch: Partial<NamedDevice>) =>
    set({ devices: value.devices.map((d, j) => (j === i ? { ...d, ...patch } : d)) });

  const fill = async (description = text) => {
    setBusy(true); setMsg(null);
    try {
      const s = (await api.suggestRoutine(profileId, description)).routine as Suggested;
      const r = withoutMissing(s);
      // keep links a clinician made for devices with the same name
      const old = new Map(value.devices.map((d) => [d.name.toLowerCase(), d]));
      const next = { ...r, devices: r.devices.map((d) => ({ ...d, id: old.get(d.name.toLowerCase())?.id ?? d.id, ip: old.get(d.name.toLowerCase())?.ip ?? null })) };
      onChange(next);
      const qs = (s.missing ?? []).filter((q) => stillOpen(q, next));
      setQueue(qs); setAsked(0);
      setMsg(qs.length
        ? "Filled in from the description. A few short questions complete what is still open; you can skip any of them."
        : "Filled in from the description. Please check it and change what is not right.");
    } catch (e) {
      setMsg(`The assistant could not fill it in: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  const answer = async (q: MissingQuestion, text: string) => {
    setBusy(true); setMsg(null);
    try {
      const s = (await api.suggestRoutine(profileId, `Question: ${q.question}\nAnswer: ${text}`)).routine as Suggested;
      onChange(mergeAnswer(value, withoutMissing(s), q.fields));
      next(q);
    } catch (e) {
      setMsg(`The assistant could not fill in the answer: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  };
  const next = (q: MissingQuestion) => {
    const rest = queue.filter((x) => x.id !== q.id);
    setQueue(rest); setAsked(asked + 1);
    if (!rest.length) setMsg("Thank you. Please check the form below and change what is not right.");
  };

  return (
    <div className="routine">
      {show("describe") && assistant && (
        <div className="describe">
          <label className="field">{person ? "Describe your usual week in your own words" : "Describe the usual week (or paste what the patient said)"}
            <span className="dictate-wrap">
              <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)}
                placeholder="e.g. School Monday to Friday from 8 to 4, Wednesdays online from home. Usually in bed around 11, up at 7; on weekends I sleep longer. I use my iPhone and a school laptop; the iPad belongs to the family." />
              <Dictate inField disabled={busy} label="your week" onText={(t) => {   // spoken: fill in the form straight away
                const description = appendText(text, t);
                setText(description);
                void fill(description);
              }} />
            </span>
          </label>
          <div className="row-actions">
            <button className="btn" onClick={() => fill()} disabled={busy || !text.trim()}>{busy ? "Filling in…" : "Fill in with the assistant"}</button>
            <span className="muted small">Type, or speak with the microphone: what you say is filled in straight away. The description is sent to Claude (Anthropic) to fill in the form; nothing is saved until you save.</span>
          </div>
          {msg && <p className="notice" role="status">{msg}</p>}
          {pending.length > 0 && (
            <FollowUp key={pending[0].id} q={pending[0]} n={asked + 1} total={asked + pending.length} busy={busy}
              onAnswer={(t) => answer(pending[0], t)} onSkip={() => next(pending[0])}
              onSkipAll={() => { setQueue([]); setMsg("Please check the form below and fill in what you like."); }} />
          )}
        </div>
      )}

      {show("week") && (
        <fieldset className="fieldset">
          <legend>{person ? "Your week" : "Week"}</legend>
          <div className="row-actions week-presets">
            <span className="muted small">Quick start:</span>
            {PRESETS.map((p) => (
              <button key={p.label} type="button" className="chip" onClick={() => set({ week: { ...p.week } })}>{p.label}</button>
            ))}
          </div>
          <div className="table-wrap">
            <table className="week-table">
              <thead>
                <tr><th />{WEEKDAYS.map((d) => <th key={d} colSpan={2} className={`day ${d === "sat" || d === "sun" ? "weekend" : ""}`}>{DAY_NAMES[d]}</th>)}</tr>
                <tr className="halves"><th />{WEEKDAYS.flatMap((d) => HALVES.map((h) => (
                  <th key={d + h} className={`${h} ${d === "sat" || d === "sun" ? "weekend" : ""}`} title={HALF_NAME[h]}>{h.toUpperCase()}</th>
                )))}</tr>
              </thead>
              <tbody>
                {(["away", "home", "free"] as DayType[]).map((t) => (
                  <tr key={t}>
                    <th scope="row"><span className="week-type"><DayTypeIcon type={t} /> {TYPE_LABEL[t]}</span><span className="muted small">{TYPE_HINT[t]}</span></th>
                    {WEEKDAYS.flatMap((d) => HALVES.map((h) => {
                      const on = value.week[d][h] === t;
                      return (
                        <td key={d + h} className={`${h} ${d === "sat" || d === "sun" ? "weekend" : ""}`}>
                          <button type="button" role="radio" aria-checked={on}
                            aria-label={`${DAY_NAMES[d]} ${HALF_NAME[h]}: ${TYPE_LABEL[t]}`}
                            className={`week-cell week-${t} ${on ? "on" : ""}`}
                            onClick={() => setHalf(d, h, t)} />
                        </td>
                      );
                    }))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {/* phones: one line per day instead of a 14-column grid */}
          <ul className="week-list" aria-label={person ? "Your week, day by day" : "Week, day by day"}>
            {WEEKDAYS.map((d) => (
              <li key={d} className={d === "sat" || d === "sun" ? "weekend" : ""}>
                <span className="week-list-day">{DAY_NAMES[d]}</span>
                {HALVES.map((h) => (
                  <div key={h} className="week-list-half" role="radiogroup" aria-label={`${DAY_NAMES[d]} ${HALF_NAME[h]}`}>
                    <span className="muted small">{h === "am" ? "Morning" : "Afternoon"}</span>
                    <div className="seg seg-small">
                      {(["away", "home", "free"] as DayType[]).map((t) => (
                        <button key={t} type="button" role="radio" aria-checked={value.week[d][h] === t}
                          className={value.week[d][h] === t ? "active" : ""} onClick={() => setHalf(d, h, t)}>
                          <DayTypeIcon type={t} /> {TYPE_LABEL[t]}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </li>
            ))}
          </ul>
          <p className="muted small">AM is the morning until about noon, PM the afternoon. A day counts as away if part of it is away.</p>
        </fieldset>
      )}

      {show("times") && (
        <fieldset className="fieldset">
          <legend>{person ? "Your usual times" : "Usual times"}</legend>
          <table className="times-table">
            <thead><tr><th /><th>School / work days</th><th>Free days</th></tr></thead>
            <tbody>
              <tr><th scope="row">Wake up</th>
                <td><TimeInput label="Wake up on school or work days" value={value.wake} onChange={(v) => set({ wake: v })} /></td>
                <td><TimeInput label="Wake up on free days" value={value.wake_free} onChange={(v) => set({ wake_free: v })} /></td></tr>
              {hasAway && (
                <>
                  <tr><th scope="row">Leave home</th>
                    <td><TimeInput label="Leave home on away days" value={value.away_from} onChange={(v) => set({ away_from: v })} /></td>
                    <td className="muted">–</td></tr>
                  <tr><th scope="row">Back home</th>
                    <td><TimeInput label="Back home on away days" value={value.away_to} onChange={(v) => set({ away_to: v })} /></td>
                    <td className="muted">–</td></tr>
                </>
              )}
              <tr><th scope="row">Bedtime</th>
                <td><TimeInput label="Bedtime on school or work days" value={value.bedtime} onChange={(v) => set({ bedtime: v })} /></td>
                <td><TimeInput label="Bedtime on free days" value={value.bedtime_free} onChange={(v) => set({ bedtime_free: v })} /></td></tr>
            </tbody>
          </table>
          <p className="muted small">Leave fields empty if you are not sure.{!hasAway && " Leave and back home times appear when a day is set to away."}</p>
        </fieldset>
      )}

      {show("devices") && (
        <fieldset className="fieldset">
          <legend>{person ? "Your devices" : "Devices"}</legend>
          <p className="muted small">{person
            ? "The devices you use at home, in your own words. You do not need any technical details; the study team links them to the network."
            : "The patient's devices in their words. Link each one to an address seen on the network."}</p>
          {value.devices.map((d, i) => (
            <div key={d.id ?? i} className="device-row">
              <input className="inline-input" value={d.name} placeholder="e.g. iPhone" onChange={(e) => setDevice(i, { name: e.target.value })} aria-label="Device name" />
              <select value={d.kind} onChange={(e) => setDevice(i, { kind: e.target.value })} aria-label="Kind of device">
                {KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
              </select>
              <label className="toggle"><input type="checkbox" checked={d.shared} onChange={(e) => setDevice(i, { shared: e.target.checked })} /> shared with others</label>
              {linkOptions && (
                <select value={d.ip ?? ""} onChange={(e) => setDevice(i, { ip: e.target.value || null })} aria-label="Network address">
                  <option value="">not linked</option>
                  {linkOptions.map((o) => (
                    <option key={o.ip} value={o.ip}>{o.ip}{o.label ? `, ${o.label}` : ""}, {fmtNum(o.packets)} packets{o.assigned_to.length ? `, ${o.assigned_to.join(", ")}` : ""}</option>
                  ))}
                </select>
              )}
              {!person && !linkOptions && <span className="muted small">{d.ip ? `linked: ${d.ip}` : "not linked"}</span>}
              <button className="link small" aria-label={`Remove ${d.name.trim() || "this device"}`}
                onClick={() => set({ devices: value.devices.filter((_, j) => j !== i) })}>remove</button>
            </div>
          ))}
          <button className="btn small" onClick={() => set({ devices: [...value.devices, { name: "", kind: "phone", shared: false }] })}>+ Add a device</button>
        </fieldset>
      )}

      {show("note") && (
        <label className="field">{person ? "Anything else that matters for your week? (optional)" : "Note (optional)"}
          <span className="dictate-wrap">
            <textarea rows={2} value={value.note} maxLength={1000} onChange={(e) => set({ note: e.target.value })}
              placeholder="e.g. every second weekend at my father's" />
            <Dictate inField label="the note" onText={(t) => set({ note: appendText(value.note, t).slice(0, 1000) })} />
          </span>
        </label>
      )}
    </div>
  );
}

/** One follow-up question, answered by typing or speaking; a spoken answer is filled in straight away. */
function FollowUp({ q, n, total, busy, onAnswer, onSkip, onSkipAll }: {
  q: MissingQuestion; n: number; total: number; busy: boolean;
  onAnswer: (text: string) => void; onSkip: () => void; onSkipAll: () => void;
}) {
  const [text, setText] = useState("");
  return (
    <fieldset className="fieldset followup" aria-live="polite">
      <legend>Question {n} of {total}</legend>
      <label className="field">{q.question}
        <span className="dictate-wrap">
          <textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder="Your answer, in your own words" />
          <Dictate inField disabled={busy} label="your answer" onText={(t) => { const a = appendText(text, t); setText(a); onAnswer(a); }} />
        </span>
      </label>
      <div className="row-actions">
        <button type="button" className="btn" onClick={() => onAnswer(text)} disabled={busy || !text.trim()}>{busy ? "Filling in…" : "Answer"}</button>
        <button type="button" className="btn btn-quiet" onClick={onSkip} disabled={busy}>Skip this question</button>
        {total - n > 0 && <button type="button" className="link small" onClick={onSkipAll} disabled={busy}>Skip the remaining questions</button>}
      </div>
    </fieldset>
  );
}

/**
 * Day types as icons next to their label: away (suitcase), at home (house), free (cup). Decorative:
 * the label is always next to it. TODO(T0): use <Icon name="away" /> from Icon.tsx once it is merged;
 * "home" and "free" are not in the §2 icon contract yet.
 */
export function DayTypeIcon({ type }: { type: DayType }) {
  const paths: Record<DayType, JSX.Element> = {
    away: <><rect x="3" y="7" width="18" height="13" rx="2" /><path d="M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2M3 13h18" /></>,
    home: <><path d="M3 11l9-7 9 7" /><path d="M5 10v10h14V10M10 20v-6h4v6" /></>,
    free: <><path d="M4 9h13v5a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5z" /><path d="M17 11h1.5a2.5 2.5 0 0 1 0 5H16M8 3v3M12 3v3" /></>,
  };
  return (
    <svg className={`daytype-icon daytype-${type}`} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden style={{ verticalAlign: "-2px" }}>
      {paths[type]}
    </svg>
  );
}

function TimeInput({ label, value, onChange }: { label: string; value: string | null; onChange: (v: string | null) => void }) {
  return <input type="time" aria-label={label} value={value ?? ""} onChange={(e) => onChange(e.target.value || null)} />;
}

/** Away periods: holidays, hospital stays, travel — left out of the usual ranges and flags. */
export function AwayEditor({ value, onChange, person }: { value: { id?: string; from: string; to: string; reason: string }[]; onChange: (v: { id?: string; from: string; to: string; reason: string }[]) => void; person: boolean }) {
  const [draft, setDraft] = useState({ from: "", to: "", reason: "" });
  return (
    <fieldset className="fieldset">
      <legend>{person ? "Times you are away" : "Away periods"}</legend>
      <p className="muted small">{person
        ? "Holidays, trips or a hospital stay: these days are not compared with your usual weeks."
        : "Holidays, hospital stays, travel: left out of the usual ranges and the flags."}</p>
      {value.length > 0 && (
        <ul className="away-list">
          {value.map((p, i) => (
            <li key={p.id ?? i}><b>{p.from === p.to ? p.from : `${p.from} – ${p.to}`}</b>{p.reason && `, ${p.reason}`}
              <button className="link small" onClick={() => onChange(value.filter((_, j) => j !== i))}>remove</button></li>
          ))}
        </ul>
      )}
      <div className="away-add">
        <input type="date" aria-label="From" value={draft.from} onChange={(e) => setDraft({ ...draft, from: e.target.value, to: draft.to || e.target.value })} />
        <span>–</span>
        <input type="date" aria-label="To" value={draft.to} onChange={(e) => setDraft({ ...draft, to: e.target.value })} />
        <input className="inline-input" placeholder="reason (optional)" value={draft.reason} onChange={(e) => setDraft({ ...draft, reason: e.target.value })} />
        <button className="btn small" disabled={!draft.from || !draft.to || draft.to < draft.from}
          onClick={() => { onChange([...value, draft]); setDraft({ from: "", to: "", reason: "" }); }}>Add</button>
      </div>
    </fieldset>
  );
}
