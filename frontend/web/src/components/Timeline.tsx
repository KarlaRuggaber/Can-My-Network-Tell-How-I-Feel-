import { useMemo, useState } from "react";
import type { Day, Note, RiskFlag, Timeline as TL } from "../api";
import { api } from "../api";
import { fmtDay, fmtNum } from "../lib/format";
import { flagIcon, fmtClock, fmtHours, typicalWording } from "../lib/observed";
import { C } from "../theme";
import { appendText, Dictate } from "./Dictate";
import { Icon } from "./Icon";
import "./overview.css";

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
  quiet_start_sd7: ["More irregular nights", "More regular nights"],
};

export type Difference = { text: string; risk: boolean; reference?: boolean };

/** Clear differences of a day: from the person's usual range, then (clinicians, parents) from the typical range. */
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
    out.push({ text: `${WORDS[t.key][sign > 0 ? 0 : 1]} than typical`, risk: t.risk.includes(sign), reference: true });
  }
  return out;
}

/** Robin Z-style timeline, newest first. The person: one line per day with three facts and the 24 h strip
 * (A6). Clinicians and parents: one card per day with all values, differences, flags and notes. */
export function Timeline(props: Props) {
  return props.person ? <PersonTimeline {...props} /> : <ClinicianTimeline {...props} />;
}

function PersonTimeline({ tl, selectedDay, onSelectDay }: Props) {
  const days = [...tl.days].reverse();
  return (
    <section className="card">
      <div className="t1-head">
        <h2>Timeline</h2>
        <p className="sub">One line per day, newest first: how long your devices were in use, when they went quiet the night before,
          when they were back online, and use over the 24 hours of the day.</p>
        <StripKey />
      </div>
      <ol className="tlp">
        {days.map((d) => {
          const o = d.observed;
          return (
            <li key={d.date} className={`tlp-day ${d.date === selectedDay ? "tlp-selected" : ""}`}>
              <button className="tlp-date" onClick={() => onSelectDay(d.date)}>{d.weekday} {fmtDay(d.date)}</button>
              {!o || !o.has_data ? <span className="muted small tlp-none">No data on this day{d.complete ? "" : " yet"}</span> : (
                <>
                  <span className="tlp-facts">
                    <span title="Time in use"><Icon name="clock" label="Time in use" size={15} /> {fmtHours(o.online_hours)}</span>
                    <span title="Went quiet the night before"><Icon name="moon" label="Went quiet" size={15} /> {fmtClock(o.quiet_start)}</span>
                    <span title="Back online in the morning"><Icon name="sunrise" label="Back online" size={15} /> {fmtClock(o.quiet_end)}</span>
                  </span>
                  <HourStrip hourly={o.active_hourly} compact />
                </>
              )}
              {!d.complete && <span className="muted small">still being recorded</span>}
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function ClinicianTimeline({ tl, notes, onNotes, selectedDay, onSelectDay, onOpenDetails, onAsk }: Props) {
  const [onlyDifferent, setOnlyDifferent] = useState(false);
  const [draft, setDraft] = useState<{ day: string; text: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const labels = tl.profile.phase_labels;
  const flagDays = useMemo(() => {
    const m = new Map<string, RiskFlag[]>();
    for (const f of tl.observed?.flags ?? []) for (const d of f.days) m.set(d, [...(m.get(d) ?? []), f]);
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
          <p className="sub">One card per day, newest first: the quiet window, use over the day, and what was clearly different from the usual weeks
            or the typical range. Notes add the context the network cannot see (holidays, exams, a move to outpatient care).</p>
          <StripKey />
          <p className="sub band-key">
            <span><i className="tl-dot-key tl-dot-key-risk" /> clearly different, risk direction</span>
            <span><i className="tl-dot-key tl-dot-key-diff" /> clearly different, other direction</span>
            <span><span className="pill pill-baseline">{labels.baseline.toLowerCase()}</span> baseline days (usual weeks)</span>
          </p>
        </div>
        <label className="toggle"><input type="checkbox" checked={onlyDifferent} onChange={(e) => setOnlyDifferent(e.target.checked)} /> only days with differences or notes</label>
      </div>
      {error && <p className="error">{error}</p>}
      <ol className="timeline">
        {days.map((d) => {
          const o = d.observed;
          const diff = differences(tl, d);
          const dayNotes = notesByDay.get(d.date) ?? [];
          const flags = flagDays.get(d.date) ?? [];
          return (
            <li key={d.date} className={`tl-day ${d.date === selectedDay ? "tl-selected" : ""}`}>
              <div className="tl-rail" aria-hidden="true"><span className={`tl-dot ${diff.some((x) => x.risk && !x.reference) ? "tl-dot-risk" : diff.length ? "tl-dot-diff" : ""}`} /></div>
              <div className="tl-body">
                <div className="tl-head">
                  <button className="tl-date" onClick={() => onSelectDay(d.date)}>{d.weekday} {fmtDay(d.date)}</button>
                  {d.phase === "baseline" && <span className="pill pill-baseline">{labels.baseline.toLowerCase()}</span>}
                  {!d.complete && <span className="pill pill-outline">still being recorded</span>}
                  {flags.map((f) => (
                    <span key={f.id} className={`pill tl-flag ${f.sensitive ? "pill-alert" : f.kind === "change" ? "pill-change" : "pill-outline"}`}>
                      <Icon name={flagIcon(f)} size={14} /> {typicalWording(f.title)}
                    </span>
                  ))}
                  {onOpenDetails && <button className="link small tl-open" onClick={() => onOpenDetails(d.date)}>Open in Details</button>}
                </div>
                {!o || !o.has_data ? <p className="muted small">No data on this day.</p> : (
                  <>
                    <div className="tl-values">
                      <span><Icon name="moon" label="Quiet at night" size={15} /> <b>{fmtClock(o.quiet_start)} → {fmtClock(o.quiet_end)}</b> quiet ({fmtHours(o.quiet_hours)})</span>
                      <span><Icon name="clock" label="Time in use" size={15} /> <b>{fmtHours(o.online_hours)}</b> in use</span>
                      <span><Icon name="night-use" label="Use at night" size={15} /> <b>{fmtNum(o.night_minutes, 0)} min</b> at night</span>
                      <span><Icon name="chat" label="Chat sessions" size={15} /> <b>{fmtNum(o.chat_sessions, 0)}</b> chat sessions</span>
                      <span><Icon name="globe" label="Different sites" size={15} /> <b>{fmtNum(o.sites, 0)}</b> sites</span>
                    </div>
                    <HourStrip hourly={o.active_hourly} />
                    {diff.length > 0 && (
                      <div className="tl-diff">
                        {diff.map((x) => onAsk
                          ? <button key={x.text} className={`pill pill-btn ${x.risk ? "pill-neutral" : "pill-outline"} ${x.reference ? "pill-ref" : ""}`} title="Explain with the assistant"
                              onClick={() => onAsk(`Why does ${d.weekday} ${d.date} show "${x.text}"? Which value, compared with which range, and what could explain it?`, `timeline, day ${d.date}`)}>{x.text} <Icon name="explain" size={13} /></button>
                          : <span key={x.text} className={`pill ${x.risk ? "pill-neutral" : "pill-outline"} ${x.reference ? "pill-ref" : ""}`}>{x.text}</span>)}
                      </div>
                    )}
                  </>
                )}
                <div className="tl-notes">
                  {dayNotes.map((n) => (
                    <div key={n.id} className="tl-note">
                      <Icon name="note" label="Note" size={14} /> <span className="tl-note-text">{n.text}</span>
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
                    <button className="link small" onClick={() => setDraft({ day: d.date, text: "" })}><Icon name="note" size={14} /> Add note</button>
                  )}
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

const EMPTY_HOUR = "#f3f0ec";

/** Legend of the 24-hour strip (rule 7: no unexplained tiles). */
function StripKey() {
  return (
    <p className="sub band-key strip-key">
      <span>24 h strip, one cell per hour 00–24:</span>
      <span className="strip-ramp" aria-hidden="true">
        {[EMPTY_HOUR, ...C.intensity].map((c) => <i key={c} style={{ background: c }} />)}
      </span>
      <span>empty = no use, light to dark = a few minutes to the whole hour in use</span>
      <span><i className="key-night-tick" /> night hours 22–06</span>
    </p>
  );
}

/** 24 cells for the hours of the day, darker = more minutes in use (neutral scale); night hours (22–06) underlined. */
export function HourStrip({ hourly, compact = false }: { hourly: number[] | null; compact?: boolean }) {
  if (!hourly) return null;
  const n = C.intensity.length;
  // no use = an empty cell; 1–60 minutes on the neutral scale, lightest to darkest
  return (
    <div className={`hour-strip ${compact ? "hour-strip-compact" : ""}`} role="img"
      aria-label={`Minutes in use per hour: ${hourly.map((m, h) => `${h}h ${m}`).join(", ")}`}>
      {hourly.map((m, h) => (
        <span key={h} className={`hour ${h >= 22 || h < 6 ? "hour-night" : ""}`}
          style={{ background: m <= 0 ? EMPTY_HOUR : C.intensity[Math.min(n - 1, Math.floor((m / 60) * n))] }}
          title={`${String(h).padStart(2, "0")}:00–${String(h + 1).padStart(2, "0")}:00, ${m} min in use`} />
      ))}
      <span className="hour-scale muted small"><span>00</span><span>06</span><span>12</span><span>18</span><span>24</span></span>
    </div>
  );
}
