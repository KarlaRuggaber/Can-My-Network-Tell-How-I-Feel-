import { useMemo, useState } from "react";
import type { Day, Note, Timeline as TL } from "../api";
import { api } from "../api";
import { fmtDay, fmtNum } from "../lib/format";
import { fmtClock, fmtHours } from "../lib/observed";
import { C } from "../theme";
import { appendText, Dictate } from "./Dictate";

type Props = {
  tl: TL;
  person: boolean;
  notes: Note[];
  onNotes: (n: Note[]) => void;
  selectedDay: string | null;
  onSelectDay: (d: string) => void;
  onOpenDetails?: (d: string) => void;      // clinicians and parents: jump to the day in Details
  onAsk?: (question: string, focus: string) => void;
};

/** Everyday wording for "clearly different from usual", by track and direction. */
const WORDS: Record<string, [string, string]> = {
  quiet_start: ["Went quiet later", "Went quiet earlier"],
  quiet_end: ["Back online later", "Back online earlier"],
  quiet_hours: ["Longer quiet window", "Shorter quiet window"],
  online_hours: ["More time in use", "Less time in use"],
  night_minutes: ["More use at night", "Less use at night"],
  chat_sessions: ["More chat sessions", "Fewer chat sessions"],
  sites: ["More different sites", "Fewer different sites"],
};

export type Difference = { text: string; risk: boolean; reference?: boolean };

/** Clear differences of a day: from the person's usual range, then (clinicians, parents) from healthy people. */
export function differences(tl: TL, d: Day): Difference[] {
  const o = d.observed;
  if (!o) return [];
  const z = tl.observed?.params.deviation_z ?? 1.5;
  const out: Difference[] = [];
  for (const t of tl.observed?.tracks ?? []) {
    const dev = o.deviation?.[t.key];
    if (dev === null || dev === undefined || Math.abs(dev) < z || !WORDS[t.key]) continue;
    const sign = dev > 0 ? 1 : -1;
    out.push({ text: WORDS[t.key][sign > 0 ? 0 : 1], risk: t.risk.includes(sign) });
  }
  for (const s of o.sensitive ?? []) out.push({ text: s.label, risk: true });
  for (const t of tl.observed?.tracks ?? []) {
    const dev = o.deviation_ref?.[t.key];
    if (dev === null || dev === undefined || Math.abs(dev) < z || !WORDS[t.key]) continue;
    const sign = dev > 0 ? 1 : -1;
    out.push({ text: `${WORDS[t.key][sign > 0 ? 0 : 1]} than healthy people`, risk: t.risk.includes(sign), reference: true });
  }
  return out;
}

/** Robin Z-style timeline: one card per day, newest first, with what was different and the notes. */
export function Timeline({ tl, person, notes, onNotes, selectedDay, onSelectDay, onOpenDetails, onAsk }: Props) {
  const [onlyDifferent, setOnlyDifferent] = useState(false);
  const [draft, setDraft] = useState<{ day: string; text: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const labels = tl.profile.phase_labels;
  const flagDays = useMemo(() => {
    const m = new Map<string, string[]>();
    for (const f of tl.observed?.flags ?? []) for (const d of f.days) m.set(d, [...(m.get(d) ?? []), f.title]);
    return m;
  }, [tl]);
  const notesByDay = useMemo(() => {
    const m = new Map<string, Note[]>();
    for (const n of notes) m.set(n.date, [...(m.get(n.date) ?? []), n]);
    return m;
  }, [notes]);

  const days = [...tl.days].reverse().filter((d) => !onlyDifferent || differences(tl, d).length > 0 || notesByDay.has(d.date));

  const save = async () => {
    if (!draft?.text.trim()) return;
    try {
      onNotes((await api.addNote(tl.profile.id, draft.day, draft.text)).notes);
      setDraft(null); setError(null);
    } catch (e) { setError(String((e as Error).message)); }
  };
  const remove = async (n: Note) => {
    if (!window.confirm("Delete this note?")) return;
    onNotes((await api.deleteNote(tl.profile.id, n.id)).notes);
  };

  return (
    <section className="card">
      <div className="card-head row-between">
        <div>
          <h2>Timeline</h2>
          <p className="sub">One card per day, newest first: the quiet window, use over the day, and what was clearly different from {person ? "your" : "the"} usual weeks.
            {!person && " Notes add the context the network cannot see (holidays, exams, a move to outpatient care)."}</p>
        </div>
        <label className="toggle"><input type="checkbox" checked={onlyDifferent} onChange={(e) => setOnlyDifferent(e.target.checked)} /> only days with differences{person ? "" : " or notes"}</label>
      </div>
      {error && <p className="error">{error}</p>}
      <ol className="timeline">
        {days.map((d) => {
          const o = d.observed;
          const diff = differences(tl, d);
          const dayNotes = notesByDay.get(d.date) ?? [];
          const flags = flagDays.get(d.date) ?? [];
          const phase = d.phase === "current" ? labels.current : d.phase === "baseline" ? labels.baseline : d.phase;
          return (
            <li key={d.date} className={`tl-day ${d.date === selectedDay ? "tl-selected" : ""}`}>
              <div className="tl-rail" aria-hidden="true"><span className={`tl-dot ${diff.some((x) => x.risk && !x.reference) ? "tl-dot-risk" : diff.length ? "tl-dot-diff" : ""}`} /></div>
              <div className="tl-body">
                <div className="tl-head">
                  <button className="tl-date" onClick={() => onSelectDay(d.date)}>{d.weekday} {fmtDay(d.date)}</button>
                  <span className={`pill ${d.phase === "current" ? "pill-red" : "pill-beige"}`}>{phase.toLowerCase()}</span>
                  {!d.complete && <span className="pill pill-outline">still being recorded</span>}
                  {flags.map((f) => <span key={f} className="pill pill-outline tl-flag">{f}</span>)}
                  {onOpenDetails && <button className="link small tl-open" onClick={() => onOpenDetails(d.date)}>Open in Details</button>}
                </div>
                {!o || !o.has_data ? <p className="muted small">No data on this day.</p> : (
                  <>
                    <div className="tl-values">
                      <span><b>{fmtClock(o.quiet_start)} → {fmtClock(o.quiet_end)}</b> quiet ({fmtHours(o.quiet_hours)})</span>
                      <span><b>{fmtHours(o.online_hours)}</b> in use</span>
                      <span><b>{fmtNum(o.night_minutes, 0)} min</b> at night</span>
                      <span><b>{fmtNum(o.chat_sessions, 0)}</b> chat sessions</span>
                      <span><b>{fmtNum(o.sites, 0)}</b> sites</span>
                    </div>
                    <HourStrip hourly={o.active_hourly} />
                    {diff.length > 0 && (
                      <div className="tl-diff">
                        {diff.map((x) => onAsk
                          ? <button key={x.text} className={`pill pill-btn ${x.risk ? "pill-risk" : "pill-grey"} ${x.reference ? "pill-ref" : ""}`} title="Explain with the assistant"
                              onClick={() => onAsk(`Why does ${d.weekday} ${d.date} show "${x.text}"? Which value, compared with which range, and what could explain it?`, `timeline, day ${d.date}`)}>{x.text} ✦</button>
                          : <span key={x.text} className={`pill ${x.risk ? "pill-risk" : "pill-grey"} ${x.reference ? "pill-ref" : ""}`}>{x.text}</span>)}
                      </div>
                    )}
                  </>
                )}
                {!person && (
                  <div className="tl-notes">
                    {dayNotes.map((n) => (
                      <div key={n.id} className="tl-note">
                        <span className="tl-note-text">{n.text}</span>
                        <span className="muted small"> — {n.author}, {fmtDay(n.created.slice(0, 10))}</span>
                        <button className="link small" onClick={() => remove(n)} aria-label="Delete note">delete</button>
                      </div>
                    ))}
                    {draft?.day === d.date ? (
                      <form className="tl-add" onSubmit={(e) => { e.preventDefault(); save(); }}>
                        <input autoFocus value={draft.text} maxLength={2000} placeholder="e.g. exam week, holidays, moved to outpatient care"
                          onChange={(e) => setDraft({ day: d.date, text: e.target.value })} />
                        <Dictate onText={(t) => setDraft((dr) => (dr ? { ...dr, text: appendText(dr.text, t).slice(0, 2000) } : dr))} />
                        <button className="btn btn-primary" type="submit" disabled={!draft.text.trim()}>Save</button>
                        <button className="btn btn-quiet" type="button" onClick={() => setDraft(null)}>Cancel</button>
                      </form>
                    ) : (
                      <button className="link small" onClick={() => setDraft({ day: d.date, text: "" })}>+ Add note</button>
                    )}
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

/** 24 cells for the hours of the day, darker = more minutes in use; night hours (22–06) underlined. */
function HourStrip({ hourly }: { hourly: number[] | null }) {
  if (!hourly) return null;
  return (
    <div className="hour-strip" role="img" aria-label="Minutes in use per hour">
      {hourly.map((m, h) => (
        <span key={h} className={`hour ${h >= 22 || h < 6 ? "hour-night" : ""}`}
          style={{ background: m <= 0 ? "#f6f3ef" : C.seq[Math.min(C.seq.length - 1, 1 + Math.floor((m / 60) * (C.seq.length - 2)))] }}
          title={`${String(h).padStart(2, "0")}:00 · ${m} min in use`} />
      ))}
      <span className="hour-scale muted small"><span>00</span><span>06</span><span>12</span><span>18</span><span>24</span></span>
    </div>
  );
}
