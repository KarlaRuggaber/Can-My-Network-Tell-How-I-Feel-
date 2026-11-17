import { useState } from "react";
import { api, WEEKDAYS, type DayType, type NamedDevice, type Routine, type SourceDevice } from "../api";
import { fmtNum } from "../lib/format";

export const defaultRoutine = (): Routine => ({
  week: { mon: "away", tue: "away", wed: "away", thu: "away", fri: "away", sat: "free", sun: "free" },
  away_from: "08:00", away_to: "16:00", bedtime: "22:30", wake: "07:00", bedtime_free: null, wake_free: null,
  devices: [], note: "",
});

const DAY_NAMES: Record<string, string> = { mon: "Mon", tue: "Tue", wed: "Wed", thu: "Thu", fri: "Fri", sat: "Sat", sun: "Sun" };
const TYPE_LABEL: Record<DayType, string> = { away: "Away", home: "At home", free: "Free" };
const TYPE_HINT: Record<DayType, string> = {
  away: "school, work or training away from home",
  home: "home office or online school",
  free: "weekend or day off",
};
const KINDS = ["phone", "laptop", "tablet", "computer", "console", "tv", "other"];

export type RoutineSection = "describe" | "week" | "times" | "devices" | "note";

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
  const set = (patch: Partial<Routine>) => onChange({ ...value, ...patch });
  const setDevice = (i: number, patch: Partial<NamedDevice>) =>
    set({ devices: value.devices.map((d, j) => (j === i ? { ...d, ...patch } : d)) });

  const fill = async () => {
    setBusy(true); setMsg(null);
    try {
      const r = (await api.suggestRoutine(profileId, text)).routine;
      // keep links a clinician made for devices with the same name
      const old = new Map(value.devices.map((d) => [d.name.toLowerCase(), d]));
      onChange({ ...r, devices: r.devices.map((d) => ({ ...d, id: old.get(d.name.toLowerCase())?.id ?? d.id, ip: old.get(d.name.toLowerCase())?.ip ?? null })) });
      setMsg("Filled in from the description. Please check it and change what is not right.");
    } catch (e) {
      setMsg(`The assistant could not fill it in: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="routine">
      {show("describe") && assistant && (
        <div className="describe">
          <label className="field">{person ? "Describe your usual week in your own words" : "Describe the usual week (or paste what the patient said)"}
            <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)}
              placeholder="e.g. School Monday to Friday from 8 to 4, Wednesdays online from home. Usually in bed around 11, up at 7; on weekends I sleep longer. I use my iPhone and a school laptop; the iPad belongs to the family." />
          </label>
          <div className="row-actions">
            <button className="btn" onClick={fill} disabled={busy || !text.trim()}>{busy ? "Filling in…" : "Fill in with the assistant"}</button>
            <span className="muted small">Your description is sent to the assistant's provider to fill in the form; nothing is saved until you save.</span>
          </div>
          {msg && <p className="notice">{msg}</p>}
        </div>
      )}

      {show("week") && (
        <fieldset className="fieldset">
          <legend>{person ? "Your week" : "Week"}</legend>
          <div className="week-grid">
            {WEEKDAYS.map((d) => (
              <div key={d} className="week-day">
                <span className="week-name">{DAY_NAMES[d]}</span>
                {(["away", "home", "free"] as DayType[]).map((t) => (
                  <button key={t} type="button" title={TYPE_HINT[t]}
                    className={`chip ${value.week[d] === t ? "chip-on" : ""}`}
                    onClick={() => set({ week: { ...value.week, [d]: t } })}>{TYPE_LABEL[t]}</button>
                ))}
              </div>
            ))}
          </div>
          <p className="muted small">Away: {TYPE_HINT.away}. At home: {TYPE_HINT.home}. Free: {TYPE_HINT.free}.</p>
        </fieldset>
      )}

      {show("times") && (
        <fieldset className="fieldset">
          <legend>{person ? "Your usual times" : "Usual times"}</legend>
          <div className="form-grid">
            <TimeField label="On away days: leave home" value={value.away_from} onChange={(v) => set({ away_from: v })} />
            <TimeField label="On away days: back home" value={value.away_to} onChange={(v) => set({ away_to: v })} />
            <TimeField label="Bedtime (school/work days)" value={value.bedtime} onChange={(v) => set({ bedtime: v })} />
            <TimeField label="Waking up (school/work days)" value={value.wake} onChange={(v) => set({ wake: v })} />
            <TimeField label="Bedtime (free days)" value={value.bedtime_free} onChange={(v) => set({ bedtime_free: v })} />
            <TimeField label="Waking up (free days)" value={value.wake_free} onChange={(v) => set({ wake_free: v })} />
          </div>
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
              <select value={d.kind} onChange={(e) => setDevice(i, { kind: e.target.value })} aria-label="Kind">
                {KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
              </select>
              <label className="toggle"><input type="checkbox" checked={d.shared} onChange={(e) => setDevice(i, { shared: e.target.checked })} /> shared with others</label>
              {linkOptions && (
                <select value={d.ip ?? ""} onChange={(e) => setDevice(i, { ip: e.target.value || null })} aria-label="Network address">
                  <option value="">not linked</option>
                  {linkOptions.map((o) => (
                    <option key={o.ip} value={o.ip}>{o.ip}{o.label ? ` · ${o.label}` : ""} · {fmtNum(o.packets)} packets{o.assigned_to.length ? ` · ${o.assigned_to.join(", ")}` : ""}</option>
                  ))}
                </select>
              )}
              {!person && !linkOptions && <span className="muted small">{d.ip ? `linked: ${d.ip}` : "not linked"}</span>}
              <button className="link small" onClick={() => set({ devices: value.devices.filter((_, j) => j !== i) })}>remove</button>
            </div>
          ))}
          <button className="btn small" onClick={() => set({ devices: [...value.devices, { name: "", kind: "phone", shared: false }] })}>+ Add a device</button>
        </fieldset>
      )}

      {show("note") && (
        <label className="field">{person ? "Anything else that matters for your week? (optional)" : "Note (optional)"}
          <textarea rows={2} value={value.note} maxLength={1000} onChange={(e) => set({ note: e.target.value })}
            placeholder="e.g. every second weekend at my father's" />
        </label>
      )}
    </div>
  );
}

function TimeField({ label, value, onChange }: { label: string; value: string | null; onChange: (v: string | null) => void }) {
  return (
    <label className="field">{label}
      <input type="time" value={value ?? ""} onChange={(e) => onChange(e.target.value || null)} />
    </label>
  );
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
            <li key={p.id ?? i}><b>{p.from === p.to ? p.from : `${p.from} – ${p.to}`}</b>{p.reason && ` · ${p.reason}`}
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
