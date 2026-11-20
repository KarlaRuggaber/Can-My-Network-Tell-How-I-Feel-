import { useMemo, useState, type CSSProperties, type ReactNode } from "react";
import type { Day, RiskFlag, SeenMarks, Timeline } from "../api";
import { axisName, BAND_LABELS, baselineMarkArea, mergeMarkAreas, typicalBand, usualBand } from "../lib/chart";
import { fmtDay, fmtNum } from "../lib/format";
import {
  carePurpose, flagIcon, flagKind, flagSentence, fmtClock, fmtHours, fmtTrack, inRange, percentileText,
  trackAxis, trackIcon, typicalRange, typicalWording, usualRange, type RangeKey, type Typical,
} from "../lib/observed";
import { C } from "../theme";
import { Chart } from "./Chart";
import { DataLabel } from "./DataLabel";
import { Icon, ICON_MEANING } from "./Icon";
import { WeekTable } from "./WeekTable";
import "./overview.css";

type Props = {
  tl: Timeline;
  person: boolean;                 // the person's own view: "you", no flags, no sensitive sites
  selectedDay: string | null;
  onSelectDay: (d: string) => void;
  seen?: SeenMarks;                                         // clinicians and parents
  onSeen?: (flagId: string, lastDay: string | null) => void;
  onAsk?: (question: string, focus: string) => void;
};

const RANGES: [RangeKey, string][] = [["7", "Last 7 days"], ["14", "Last 14 days"], ["30", "Last 30 days"], ["all", "All"]];

/** Track rows of "Day by day" (the quiet window has its own chart). */
const ROW_KEYS = ["online_hours", "night_minutes", "quiet_start_sd7", "chat_sessions", "sites", "sensitive_days"];

/** Theme colours the stylesheet reads (one source of truth: theme.ts). */
const CSS_VARS = {
  "--t1-alert": C.alert, "--t1-alert-soft": C.alertSoft, "--t1-change": C.change,
  "--t1-usual": C.usualBand, "--t1-typical": C.typicalLine, "--t1-baseline": C.baselineShade,
  "--t1-area": C.intensity[0], "--t1-bar": C.intensity[0], "--t1-dot": C.ink, "--t1-night-dot": C.intensity[7],
} as CSSProperties;

/** Layer 1: what the network observed, in real units, against the usual and the typical range. */
export function Overview(props: Props) {
  const { tl, person, selectedDay, onSelectDay } = props;
  const [showCharts, setShowCharts] = useState(false);
  if (!tl.observed) return null;

  if (person) {
    return (
      <div className="ov" style={CSS_VARS}>
        <DataLabel tl={tl} />
        <WeekTable tl={tl} person selectedDay={selectedDay} onSelectDay={onSelectDay} selectable={showCharts} />
        <section className="card">
          <div className="row-between">
            <div>
              <h2>Charts</h2>
              <p className="sub">The same days as charts: use over the day and when your devices were quiet at night.</p>
            </div>
            <button className="btn" aria-expanded={showCharts} onClick={() => setShowCharts((s) => !s)}>
              {showCharts ? "Hide charts" : "Show charts"}
            </button>
          </div>
          {showCharts && <Charts tl={tl} person selectedDay={selectedDay} onSelectDay={onSelectDay} />}
        </section>
      </div>
    );
  }

  return (
    <div className="ov" style={CSS_VARS}>
      <Flags {...props} />
      <section className="card">
        <Charts tl={tl} person={false} selectedDay={selectedDay} onSelectDay={onSelectDay} />
      </section>
    </div>
  );
}

/** Clinicians and parents: flag tiles with icons, grouped by comparison, ordered by the care-plan purpose. */
function Flags({ tl, selectedDay, onSelectDay, seen, onSeen, onAsk }: Props) {
  const obs = tl.observed!;
  const name = tl.persona.name;
  const labels = tl.profile.phase_labels;
  const purpose = carePurpose(tl.care);
  const currentDays = tl.days.filter((d) => d.phase === "current" && d.complete).length;
  const lastDay = (f: RiskFlag) => [...f.days].sort().at(-1) ?? "";
  // seen until a new day joins the flag
  const isSeen = (f: RiskFlag) => !!seen?.[f.id] && seen[f.id].last_day >= lastDay(f);
  const sortFlags = (fs: RiskFlag[]) => [...fs].sort((a, b) =>
    Number(isSeen(a)) - Number(isSeen(b)) || Number(flagKind(b) === "alert") - Number(flagKind(a) === "alert"));

  const renderFlag = (f: RiskFlag) => {
    const kind = flagKind(f);
    const title = typicalWording(f.title);
    return (
      <li key={f.id} className={`flag flag-${kind} ${f.basis === "reference" ? "flag-reference" : ""} ${isSeen(f) ? "flag-seen" : ""}`}>
        <span className="flag-icon"><Icon name={flagIcon(f)} label={ICON_MEANING[flagIcon(f)]} /></span>
        <div className="flag-body">
          <div className="flag-title">
            {title}
            {kind === "change" && <span className="pill pill-change">to discuss</span>}
            {f.basis === "reference" && <span className="pill pill-neutral">vs. typical range</span>}
          </div>
          <div className="flag-text">{typicalWording(flagSentence(f, name))}</div>
          <div className="flag-days">
            {f.days.map((d) => (
              <button key={d} className={`chip ${d === selectedDay ? "chip-on" : ""}`} onClick={() => onSelectDay(d)}>{fmtDay(d)}</button>
            ))}
            {onAsk && <button className="link small explain-link" onClick={() => onAsk(
              `Explain the flag "${title}" (${f.basis === "reference" ? "compared with the typical range" : "compared with the usual weeks"}): which days and values led to it, against which range, and what else could explain it (routine, away periods, notes)?`,
              `flag ${f.id}`)}><Icon name="explain" size={14} /> explain</button>}
          </div>
          {onSeen && (
            <div className="flag-actions">
              {isSeen(f)
                ? <span className="muted small">Seen by {seen![f.id].by} on {fmtDay(seen![f.id].at.slice(0, 10))} ·{" "}
                    <button className="link small" onClick={() => onSeen(f.id, null)}>undo</button></span>
                : <button className="btn small" onClick={() => onSeen(f.id, lastDay(f))}>Mark as seen</button>}
              {seen?.[f.id] && !isSeen(f) && <span className="muted small">new days since it was marked as seen</span>}
            </div>
          )}
        </div>
      </li>
    );
  };

  const own = obs.flags.filter((f) => f.basis !== "reference" && flagKind(f) !== "change");
  const ref = obs.flags.filter((f) => f.basis === "reference" && flagKind(f) !== "change");
  const change = obs.flags.filter((f) => flagKind(f) === "change");
  const refNote = obs.reference && (obs.reference.label
    ? <>Typical range: {obs.reference.label}{obs.reference.source === "external" ? " (published norms; a proxy, see the note on each chart)" : ""}.
        Owls and larks are not flagged: only several days outside the typical range count.</>
    : <>Typical range: {obs.reference.n_days} usual days of {(obs.reference.people ?? []).join(" and ")} (their everyday weeks, without {name}).
        A small reference that mixes lifestyles: a difference can reflect a lifestyle (student vs. office job) rather than health.
        Works from the first week, before {name}'s own baseline exists.</>);

  const groups: Record<"own" | "ref" | "change", ReactNode> = {
    own: <FlagGroup key="own" title={`Compared with ${name}'s usual weeks`} flags={own}
      empty={currentDays === 0 ? `The comparison starts after the ${labels.baseline.toLowerCase()} (the first 14 days).` : null}
      calm={`Nothing stands out: the recent days are within ${name}'s usual range.`} render={renderFlag} sort={sortFlags} />,
    ref: obs.reference ? <FlagGroup key="ref" title="Compared with the typical range" note={refNote} flags={ref} empty={null}
      calm="Nothing stands out: the recent days are within the typical range." render={renderFlag} sort={sortFlags} /> : null,
    change: change.length ? <FlagGroup key="change" title="Notable changes, to discuss" flags={change} empty={null}
      note={<>Clear changes in the other direction (e.g. earlier nights, more contact). Not a risk: worth discussing with {name}.</>}
      calm="" render={renderFlag} sort={sortFlags} /> : null,
  };
  const order: ("own" | "ref" | "change")[] = purpose === "assessment" ? ["ref", "own", "change"]
    : purpose === "treatment" ? ["own", "change", "ref"] : ["own", "ref", "change"];

  return (
    <section className="card">
      <div className="card-head">
        <h2>What stands out</h2>
        <p className="sub">A risk is shown when at least {obs.params.flag_days} of the last {obs.params.flag_window} days differ clearly
          (more than {obs.params.deviation_z} SD) in that direction, from {name}'s usual weeks or from the typical range;
          crisis or self-harm sites as soon as they rise above the usual level (the only alert, <Icon name="alert" label="alert" size={14} />).</p>
        {purpose && <p className="sub"><b>Care-plan purpose: {purpose}.</b> {purpose === "assessment"
          ? "The comparison with the typical range comes first."
          : "Change over time comes first, improvements included."}</p>}
      </div>
      {order.map((k) => groups[k])}
    </section>
  );
}

function FlagGroup({ title, note, flags, empty, calm, render, sort }: {
  title: string; note?: ReactNode; flags: RiskFlag[]; empty: string | null; calm: string;
  render: (f: RiskFlag) => ReactNode; sort: (fs: RiskFlag[]) => RiskFlag[];
}) {
  return (
    <div className="flag-group">
      <h3 className="flag-group-title">{title}</h3>
      {note && <p className="muted small flag-note">{note}</p>}
      {empty ? <p className="muted">{empty}</p>
        : flags.length === 0 ? <p className="calm">{calm}</p>
          : <ul className="flags">{sort(flags).map(render)}</ul>}
    </div>
  );
}

/** Day and night, devices quiet at night, day by day. The person sees them behind "Show charts". */
function Charts({ tl, person, selectedDay, onSelectDay }: {
  tl: Timeline; person: boolean; selectedDay: string | null; onSelectDay: (d: string) => void;
}) {
  const obs = tl.observed!;
  const [range, setRange] = useState<RangeKey>("all");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [nightShade, setNightShade] = useState(false);
  const [midnight, setMidnight] = useState(true);
  const [toolbar, setToolbar] = useState(!person);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [focus, setFocus] = useState<string | null>(null);
  const days = useMemo(() => inRange(tl.days, range, from, to), [tl, range, from, to]);

  const purpose = carePurpose(tl.care);
  const whose = person ? "your" : `${tl.persona.name}'s`;
  // the person sees no flags (A3)
  const flags = person ? [] : obs.flags;
  const flagsByTrack = new Map<string, RiskFlag[]>();
  for (const f of flags) flagsByTrack.set(f.track, [...(flagsByTrack.get(f.track) ?? []), f]);
  const rows = obs.tracks.filter((t) => ROW_KEYS.includes(t.key)).sort((a, b) => ROW_KEYS.indexOf(a.key) - ROW_KEYS.indexOf(b.key));
  const group = `obs-${tl.profile.id}`;
  const quietFlagged = new Set(["quiet_start", "quiet_end", "quiet_hours"].flatMap((k) => flagsByTrack.get(k) ?? [])
    .filter((f) => flagKind(f) !== "change").flatMap((f) => f.days));
  const hasRef = !!obs.reference;
  const hasBaseline = days.some((d) => d.phase === "baseline");

  const rangeKeys = (typicalFirst: boolean) => {
    const usual = <span key="u"><i className="key-usual" /> {whose} usual range (mean ± 1 SD)</span>;
    const typical = hasRef ? <span key="t"><i className="key-typical" /> typical range (other people)</span> : null;
    return typicalFirst ? [typical, usual] : [usual, typical];
  };
  const baselineKey = hasBaseline ? <span><i className="key-shade" /> Baseline (usual weeks)</span> : null;

  return (
    <>
      {person && (
        <button className="link small chart-options" aria-expanded={toolbar} onClick={() => setToolbar((t) => !t)}>
          {toolbar ? "Hide chart options" : "Chart options (days, night, midnight)"}
        </button>
      )}
      {toolbar && (
        <div className="toolbar">
          <div className="seg" role="group" aria-label="Time range">
            {RANGES.map(([k, l]) => (
              <button key={k} className={range === k ? "active" : ""} onClick={() => setRange(k)}>{l}</button>
            ))}
          </div>
          <div className="dates">
            <input type="date" aria-label="From" value={from} onChange={(e) => { setFrom(e.target.value); setRange("custom"); }} />
            <span>–</span>
            <input type="date" aria-label="To" value={to} onChange={(e) => { setTo(e.target.value); setRange("custom"); }} />
          </div>
          <label className="toggle"><input type="checkbox" checked={nightShade} onChange={(e) => setNightShade(e.target.checked)} /> Mark night (22–06)</label>
          <label className="toggle"><input type="checkbox" checked={midnight} onChange={(e) => setMidnight(e.target.checked)} /> Mark midnight</label>
        </div>
      )}

      <h3 className="chart-title"><Icon name="clock" /> Day and night</h3>
      <p className="sub">Minutes in use per hour. Gaps mean no use: asleep, away or devices off look the same from the network.</p>
      <DayNight days={days} nightShade={nightShade} midnight={midnight} selectedDay={selectedDay} onSelectDay={onSelectDay} />
      <p className="sub band-key">
        <span><i className="key-area" /> minutes in use per hour</span>
        {baselineKey}
        <span><i className="key-nodata" /> no data</span>
        {midnight && <span><i className="key-line" /> midnight</span>}
        {nightShade && <span><i className="key-night" /> night 22–06</span>}
      </p>

      <h3 className="chart-title"><Icon name="moon" /> Devices quiet at night</h3>
      <p className="sub">When the devices went quiet and came back online{person ? "" : " (longest stretch without use overlapping 00:00–06:00; a short check at night does not end it)"}.
        Asleep, away or switched off look the same from the network: this is not sleep.</p>
      <QuietWindows tl={tl} days={days} person={person} flagged={quietFlagged} selectedDay={selectedDay} onSelectDay={onSelectDay} />
      <p className="sub band-key">
        <span><i className="key-bar" /> quiet: went quiet → back online</span>
        {rangeKeys(purpose === "assessment")}
        {baselineKey}
        <span><i className="kdot kdot-night" /> use during the quiet window</span>
        {!person && quietFlagged.size > 0 && <span><i className="key-bar key-bar-flag" /> night in a flag</span>}
      </p>

      <h3 className="chart-title">Day by day</h3>
      <p className="sub band-key">
        {rangeKeys(purpose === "assessment")}
        {baselineKey}
        <span><i className="kdot" /> clearly different from {whose} usual range{rows.some((t) => t.risk.length) && !person ? ", in the risk direction" : ""}</span>
        {!person && <span><i className="kdot kdot-change" /> clearly different the other way</span>}
        {hasRef && <span><i className="kdot kdot-ring" /> outside the typical range only</span>}
        {rows.some((t) => t.sensitive) && <span><i className="kdot kdot-alert" /> crisis or self-harm sites</span>}
      </p>
      <div className="chips legend-chips" role="group" aria-label="Show or hide rows">
        {rows.map((t) => (
          <button key={t.key} className={`chip ${hidden.has(t.key) ? "chip-off" : "chip-on-soft"}`}
            onClick={() => setHidden((h) => { const n = new Set(h); if (n.has(t.key)) n.delete(t.key); else n.add(t.key); return n; })}
            onMouseEnter={() => setFocus(t.key)} onMouseLeave={() => setFocus(null)}
            aria-pressed={!hidden.has(t.key)}>
            <Icon name={trackIcon(t.key)} size={14} /> {t.label}
          </button>
        ))}
      </div>
      <div className="track-rows">
        {rows.filter((t) => !hidden.has(t.key)).map((t) => {
          const u = usualRange(obs, t.key);
          const ty = typicalRange(obs, t.key);
          const usualTxt = u && <span key="u" className="muted small">usual {fmtTrack(t.key, u.lo)} – {fmtTrack(t.key, u.hi)}</span>;
          const typTxt = ty && <span key="t" className="muted small typical-txt" title={typicalTitle(ty)}>typical {fmtTrack(t.key, ty.lo)} – {fmtTrack(t.key, ty.hi)}{ty.proxyNote || ty.citation ? " ⓘ" : ""}</span>;
          return (
            <div key={t.key} className={`track-row ${focus && focus !== t.key ? "dim" : ""}`}>
              <div className="track-head">
                <span className="track-name"><Icon name={trackIcon(t.key)} /> {t.label}</span>
                {purpose === "assessment" ? [typTxt, usualTxt] : [usualTxt, typTxt]}
                {(flagsByTrack.get(t.key) ?? []).map((f) => (
                  <span key={f.id} className={`pill ${flagKind(f) === "alert" ? "pill-alert" : flagKind(f) === "change" ? "pill-change" : "pill-neutral"}`}>
                    <Icon name={flagIcon(f)} size={14} /> {typicalWording(f.title)}
                  </span>
                ))}
              </div>
              <TrackChart tl={tl} days={days} track={t.key} person={person} group={group} selectedDay={selectedDay} onSelectDay={onSelectDay} />
            </div>
          );
        })}
      </div>
    </>
  );
}

/** Hover text of a typical range: its source, citation and proxy caveat (D2). */
function typicalTitle(t: Typical): string {
  return [
    `Typical range: ${t.label}`,
    t.percentiles ? "P16–P84 (central 68 %)" : "mean ± 1 SD (pooled reference)",
    t.citation ? `Source: ${t.citation}` : "",
    t.proxyNote ? `Note: ${t.proxyNote}` : "",
  ].filter(Boolean).join("\n");
}

function selectedIndex(days: Day[], d: string | null) {
  return days.findIndex((x) => x.date === d);
}

const AXIS_LABEL = { color: C.text2, fontSize: 10 };
const tsOf = (date: string, h: number) => new Date(`${date}T${String(h).padStart(2, "0")}:00:00`).getTime();

/** Baseline days as a neutral band on a time axis, covering whole days (the shared helper marks day starts). */
function baselineTimeBand(days: Day[]) {
  const b = days.filter((d) => d.phase === "baseline");
  if (!b.length) return [];
  return [[
    { xAxis: tsOf(b[0].date, 0), itemStyle: { color: C.baselineShade },
      label: { show: true, position: "insideTopLeft", formatter: BAND_LABELS.baseline, color: C.text2, fontSize: 10 } },
    { xAxis: tsOf(b[b.length - 1].date, 0) + 864e5 },
  ]];
}

/** Robin Z-style course over time: minutes in use per hour, baseline band and midnight lines. */
function DayNight({ days, nightShade, midnight, selectedDay, onSelectDay }: {
  days: Day[]; nightShade: boolean; midnight: boolean; selectedDay: string | null; onSelectDay: (d: string) => void;
}) {
  const option = useMemo(() => {
    const data: [number, number | null][] = [];
    const noData: object[] = [];
    for (const d of days) {
      const a = d.observed?.active_hourly;
      if (!a || !d.observed?.has_data) {
        noData.push([{ xAxis: tsOf(d.date, 0), itemStyle: { color: "rgba(0,0,0,0)", borderColor: C.muted, borderWidth: 1, borderType: "dotted" } },
          { xAxis: tsOf(d.date, 0) + 864e5 }]);
        data.push([tsOf(d.date, 0), null]);
        continue;
      }
      a.forEach((v, h) => data.push([tsOf(d.date, h) + 18e5, v]));
    }
    const nights = nightShade ? days.map((d) => [
      { xAxis: tsOf(d.date, 0) - 2 * 36e5, itemStyle: { color: "rgba(0,0,0,0)", borderColor: C.grid, borderWidth: 1 } }, { xAxis: tsOf(d.date, 6) },
    ]) : [];
    const midnights = midnight ? days.map((d) => ({ xAxis: tsOf(d.date, 0) })) : [];
    const sel = days.find((d) => d.date === selectedDay);
    return {
      animation: false,
      grid: { left: 56, right: 12, top: 18, bottom: 28 },
      tooltip: {
        trigger: "axis",
        formatter: (ps: { data: [number, number | null] }[]) => {
          const p = ps[0];
          if (!p || p.data[1] === null) return "no data";
          const t = new Date(p.data[0] - 18e5);
          return `${t.toLocaleDateString("en-GB", { weekday: "short", day: "2-digit", month: "2-digit" })} ${String(t.getHours()).padStart(2, "0")}:00–${String(t.getHours() + 1).padStart(2, "0")}:00<br/>in use ${p.data[1]} min`;
        },
      },
      xAxis: {
        type: "time", min: days.length ? tsOf(days[0].date, 0) : undefined,
        max: days.length ? tsOf(days[days.length - 1].date, 0) + 864e5 : undefined,
        axisLabel: { ...AXIS_LABEL, formatter: "{dd}/{MM}" }, splitLine: { show: false },
        axisLine: { lineStyle: { color: C.grid } },
      },
      yAxis: {
        type: "value", min: 0, max: 60, interval: 30, ...axisName("minutes in use", "per hour"),
        axisLabel: { ...AXIS_LABEL, formatter: "{value}′" }, splitLine: { lineStyle: { color: C.grid } },
      },
      series: [{
        type: "line", data, step: "middle", symbol: "none", connectNulls: false,
        lineStyle: { width: 1.2, color: C.ink }, areaStyle: { color: C.intensity[0] },
        markArea: {
          silent: true,
          data: [...baselineTimeBand(days), ...nights, ...noData,
            ...(sel ? [[{ xAxis: tsOf(sel.date, 0), itemStyle: { color: "rgba(0,0,0,0)", borderColor: C.ink, borderWidth: 1 } }, { xAxis: tsOf(sel.date, 0) + 864e5 }]] : [])],
        },
        markLine: { silent: true, symbol: "none", label: { show: false }, lineStyle: { color: C.muted, type: "dashed", width: 1 }, data: midnights },
      }],
    };
  }, [days, nightShade, midnight, selectedDay]);
  return <Chart option={option} height={180} ariaLabel="Minutes in use per hour over the selected days"
    onClick={(p) => { const v = (p.data as [number, number])?.[0]; if (v) { const d = new Date(v - 18e5); onSelectDay(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`); } }} />;
}

/** Percentile line for tooltips (clinicians): "later than 85 % of reference nights". */
function pctLine(d: Day, key: string): string {
  const t = percentileText(key, d.observed?.percentile_ref?.[key]);
  return t ? `<br/><span style="color:${C.text2}">${t}</span>` : "";
}

/** Sleep-diary style: one bar per night from going quiet to coming back, with the usual and typical times. */
function QuietWindows({ tl, days, person, flagged, selectedDay, onSelectDay }: {
  tl: Timeline; days: Day[]; person: boolean; flagged: Set<string>; selectedDay: string | null; onSelectDay: (d: string) => void;
}) {
  const option = useMemo(() => {
    const obs = tl.observed;
    const bars = days.map((d, i) => [i, d.observed?.quiet_start ?? null, d.observed?.quiet_end ?? null]);
    const dots: [number, number][] = [];
    days.forEach((d, i) => {
      const o = d.observed;
      if (!o?.active_hourly || o.quiet_start === null || o.quiet_end === null) return;
      for (let h = 0; h < 14; h++) {
        const t = h * 60 + 30;
        if (o.active_hourly[h] > 0 && t > o.quiet_start && t < o.quiet_end) dots.push([i, t]);
      }
    });
    const u = (k: string) => { const r = usualRange(obs, k); return r ? usualBand({ mean: (r.lo + r.hi) / 2, sd: (r.hi - r.lo) / 2 }) : null; };
    const ty = (k: string) => { const r = typicalRange(obs, k); return r ? typicalBand({ p16: r.lo, p50: r.mid, p84: r.hi }) : null; };
    const sel = selectedIndex(days, selectedDay);
    return {
      animation: false,
      grid: { left: 60, right: 12, top: 8, bottom: 28 },
      tooltip: {
        trigger: "item",
        formatter: (p: { data: number[] }) => {
          const d = days[p.data[0]];
          const o = d?.observed;
          if (!o) return "";
          const head = `<b>${d.weekday} ${fmtDay(d.date)}</b>${flagged.has(d.date) ? " · in a flag" : ""}`;
          if (o.quiet_start === null) return `${head}<br/>no quiet window found (no data, or no use at all)`;
          return `${head}<br/>went quiet ${fmtClock(o.quiet_start)}${person ? "" : pctLine(d, "quiet_start")}`
            + `<br/>back online ${fmtClock(o.quiet_end)}${person ? "" : pctLine(d, "quiet_end")}`
            + `<br/>quiet for ${fmtHours(o.quiet_hours)}${person ? "" : pctLine(d, "quiet_hours")}`
            + `<br/>use at night (00–06): ${fmtNum(o.night_minutes, 0)} min`;
        },
      },
      xAxis: { type: "category", data: days.map((d) => fmtDay(d.date)), axisLabel: AXIS_LABEL, axisTick: { show: false }, axisLine: { lineStyle: { color: C.grid } } },
      yAxis: {
        type: "value", inverse: true, min: -360, max: 840, interval: 120, ...axisName("clock time", ""),
        axisLabel: { ...AXIS_LABEL, formatter: (v: number) => fmtClock(v) }, splitLine: { lineStyle: { color: C.grid } },
      },
      series: [
        {
          type: "custom", data: bars, encode: { x: 0, y: [1, 2] },
          renderItem: (_: unknown, api: { value: (i: number) => number; coord: (v: number[]) => number[]; size: (v: number[]) => number[] }) => {
            const i = api.value(0), s = api.value(1), e = api.value(2);
            if (s === null || e === null || Number.isNaN(s) || Number.isNaN(e)) return null;
            const [x, y0] = api.coord([i, s]);
            const [, y1] = api.coord([i, e]);
            const w = api.size([1, 0])[0] * 0.56;
            const isFlag = flagged.has(days[i].date);
            return {
              type: "rect", shape: { x: x - w / 2, y: y0, width: w, height: y1 - y0, r: 4 },
              style: {
                fill: i === sel ? C.intensity[3] : C.intensity[0],
                stroke: isFlag ? C.ink : null, lineWidth: isFlag ? 2 : 0,
              },
            };
          },
          markArea: mergeMarkAreas(baselineMarkArea(days), u("quiet_start"), u("quiet_end"), ty("quiet_start"), ty("quiet_end")),
        },
        { type: "scatter", data: dots, symbolSize: 5, itemStyle: { color: C.intensity[7] }, tooltip: { show: false }, silent: true },
      ],
    };
  }, [tl, days, person, flagged, selectedDay]);
  return <Chart option={option} height={240} ariaLabel="Devices quiet at night, per night"
    onClick={(p) => { const i = (p.data as number[])?.[0]; if (days[i]) onSelectDay(days[i].date); }} />;
}

/** One track per day with the usual range (fill), the typical range (dashed) and clearly different days. */
function TrackChart({ tl, days, track, person, group, selectedDay, onSelectDay }: {
  tl: Timeline; days: Day[]; track: string; person: boolean; group: string; selectedDay: string | null; onSelectDay: (d: string) => void;
}) {
  const option = useMemo(() => {
    const obs = tl.observed;
    const u = usualRange(obs, track);
    const ty = typicalRange(obs, track);
    const z = obs?.params.deviation_z ?? 1.5;
    const meta = obs?.tracks.find((t) => t.key === track);
    const sensitive = !!meta?.sensitive;
    const risk = meta?.risk ?? [];
    const vals = days.map((d) => (d.observed ? (d.observed as unknown as Record<string, number | null>)[track] ?? null : null));
    const sel = selectedIndex(days, selectedDay);
    const beyond = (dev: number | null | undefined, dir?: number) =>
      dev !== null && dev !== undefined && Math.abs(dev) >= z && (dir === undefined || Math.sign(dev) === dir);
    // filled dark: clearly different in the risk direction; change colour: clearly different the other way
    // (clinicians); ring: outside the typical range only; crisis/self-harm sites: alert
    const data = vals.map((v, i) => {
      const o = days[i].observed;
      const dev = o?.deviation?.[track];
      const isRisk = risk.length ? risk.some((r) => beyond(dev, r)) : beyond(dev);
      const isChange = !person && !isRisk && beyond(dev);
      const refOnly = !isRisk && !isChange && risk.some((r) => beyond(o?.deviation_ref?.[track], r));
      const strong = isRisk || isChange || refOnly || (person && beyond(dev));
      return {
        value: v, symbolSize: strong ? 8 : 5,
        itemStyle: sensitive ? { color: C.alert }
          : refOnly ? { color: C.surface, borderColor: C.ink, borderWidth: 2 }
            : { color: isRisk || (person && beyond(dev)) ? C.ink : isChange ? C.change : C.intensity[2] },
      };
    });
    const [what, unit] = trackAxis(meta ?? { key: track, label: track, unit: "" });
    return {
      animation: false,
      grid: { left: 64, right: 12, top: 8, bottom: 22 },
      tooltip: {
        trigger: "axis",
        formatter: (ps: { dataIndex: number }[]) => {
          const d = days[ps[0]?.dataIndex];
          if (!d) return "";
          const v = vals[ps[0].dataIndex];
          if (sensitive) {
            const s = d.observed?.sensitive ?? [];
            return `<b>${d.weekday} ${fmtDay(d.date)}</b><br/>${s.length ? s.map((x) => `${x.label}: ${fmtNum(x.value)}`).join("<br/>") : "nothing above the usual level"}`;
          }
          const dev = d.observed?.deviation?.[track];
          const dref = d.observed?.deviation_ref?.[track];
          return `<b>${d.weekday} ${fmtDay(d.date)}</b><br/>${fmtTrack(track, v)}`
            + (u ? `<br/>usual ${fmtTrack(track, u.lo)} – ${fmtTrack(track, u.hi)}${beyond(dev) ? " · <b>outside</b>" : ""}` : "")
            + (ty ? `<br/>typical ${fmtTrack(track, ty.lo)} – ${fmtTrack(track, ty.hi)}${beyond(dref) ? " · <b>outside</b>" : ""}` : "")
            + (person ? "" : pctLine(d, track))
            + (ty?.proxyNote ? `<br/><span style="color:${C.muted}">${ty.proxyNote}</span>` : "");
        },
      },
      xAxis: { type: "category", data: days.map((d) => fmtDay(d.date)), axisLabel: { ...AXIS_LABEL, fontSize: 9 }, axisTick: { show: false }, axisLine: { lineStyle: { color: C.grid } } },
      yAxis: sensitive
        ? { type: "value", min: 0, max: 1, interval: 1, ...axisName(what, unit, 36), axisLabel: { ...AXIS_LABEL, fontSize: 9, formatter: (v: number) => (v ? "yes" : "no") }, splitLine: { show: false } }
        : { type: "value", scale: true, splitNumber: 3, ...axisName(what, unit, 40), axisLabel: { ...AXIS_LABEL, fontSize: 9, formatter: (v: number) => (track === "online_hours" ? `${v} h` : fmtNum(v, 0)) }, splitLine: { lineStyle: { color: C.grid } } },
      series: [{
        type: sensitive ? "bar" : "line", data, barWidth: "40%", connectNulls: false, symbol: "circle",
        lineStyle: { width: 1.5, color: C.intensity[1] },
        markArea: mergeMarkAreas(
          baselineMarkArea(days),
          u && !sensitive ? usualBand({ mean: (u.lo + u.hi) / 2, sd: (u.hi - u.lo) / 2 }) : null,
          ty && !sensitive ? typicalBand({ p16: ty.lo, p50: ty.mid, p84: ty.hi }) : null,
        ),
        markLine: sel >= 0 ? { silent: true, symbol: "none", label: { show: false }, lineStyle: { color: C.text, width: 1, type: "solid" }, data: [{ xAxis: sel }] } : undefined,
      }],
    };
  }, [tl, days, track, person, selectedDay]);
  return <Chart option={option} height={track === "sensitive_days" ? 80 : 120} group={group} ariaLabel={`Daily values: ${track}`}
    onClick={(p) => days[p.dataIndex] && onSelectDay(days[p.dataIndex].date)} />;
}
