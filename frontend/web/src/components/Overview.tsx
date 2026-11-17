import { useMemo, useState } from "react";
import type { Day, RiskFlag, SeenMarks, Timeline } from "../api";
import { fmtDay, fmtNum } from "../lib/format";
import { flagSentence, fmtClock, fmtHours, inRange, type RangeKey } from "../lib/observed";
import { C } from "../theme";
import { Chart } from "./Chart";

type Props = {
  tl: Timeline;
  person: boolean;                 // the person's own view: "you", no sensitive sites
  selectedDay: string | null;
  onSelectDay: (d: string) => void;
  seen?: SeenMarks;                                         // clinicians and parents
  onSeen?: (flagId: string, lastDay: string | null) => void;
};

/** Healthy reference: a dashed outline, no fill, so it reads differently from the person's own band. */
const REF_BAND = { color: "rgba(0,0,0,0)", borderColor: "#6f6862", borderWidth: 1, borderType: "dashed" as const };

const RANGES: [RangeKey, string][] = [["7", "Last 7 days"], ["14", "Last 14 days"], ["30", "Last 30 days"], ["all", "All"]];

/** Track rows below the quiet-window chart (the quiet window itself has its own chart). */
const ROW_KEYS = ["online_hours", "night_minutes", "chat_sessions", "sites", "sensitive_days"];

const fmtValue = (key: string, v: number | null | undefined): string =>
  v === null || v === undefined ? "–"
    : key === "online_hours" || key === "quiet_hours" ? fmtHours(v)
      : key === "night_minutes" ? `${fmtNum(v, 0)} min`
        : key.startsWith("quiet") ? fmtClock(v) : fmtNum(v, 0);

/** Layer 1: what the network observed, in real units, against the person's usual range. */
export function Overview({ tl, person, selectedDay, onSelectDay, seen, onSeen }: Props) {
  const obs = tl.observed;
  const [range, setRange] = useState<RangeKey>("all");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [nightShade, setNightShade] = useState(true);
  const [midnight, setMidnight] = useState(true);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [focus, setFocus] = useState<string | null>(null);

  const days = useMemo(() => inRange(tl.days, range, from, to), [tl, range, from, to]);
  if (!obs) return null;

  const who = person ? null : tl.persona.name;
  const labels = tl.profile.phase_labels;
  const flagsByTrack = new Map<string, RiskFlag[]>();
  for (const f of obs.flags) flagsByTrack.set(f.track, [...(flagsByTrack.get(f.track) ?? []), f]);
  const rows = obs.tracks.filter((t) => ROW_KEYS.includes(t.key));
  const currentDays = tl.days.filter((d) => d.phase === "current" && d.complete).length;
  const group = `obs-${tl.profile.id}`;
  const lastDay = (f: RiskFlag) => [...f.days].sort().at(-1) ?? "";
  // seen until a new day joins the flag
  const isSeen = (f: RiskFlag) => !!seen?.[f.id] && seen[f.id].last_day >= lastDay(f);

  const renderFlag = (f: RiskFlag) => (
    <li key={f.id} className={`flag ${f.sensitive ? "flag-sensitive" : ""} ${f.basis === "reference" ? "flag-reference" : ""} ${isSeen(f) ? "flag-seen" : ""}`}>
      <span className="flag-mark" aria-hidden="true" />
      <div>
        <div className="flag-title">{f.title}</div>
        <div className="flag-text">{flagSentence(f, who)}</div>
        <div className="flag-days">
          {f.days.map((d) => (
            <button key={d} className={`chip ${d === selectedDay ? "chip-on" : ""}`} onClick={() => onSelectDay(d)}>{fmtDay(d)}</button>
          ))}
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
  const sortSeen = (fs: RiskFlag[]) => [...fs].sort((a, b) => Number(isSeen(a)) - Number(isSeen(b)));

  return (
    <>
      {person && (
        <section className="card person-intro">
          <h2>Hello {tl.persona.name}</h2>
          <p>This page shows how your devices were used, day by day, and what looks different from your <b>usual weeks</b>.
            It looks only at when and how much your devices were online, never at what you read or wrote.
            It is a research prototype, not a diagnosis.</p>
        </section>
      )}

      <section className="card">
        <div className="card-head">
          <h2>What stands out</h2>
          <p className="sub">{person
            ? "Shown when several of the recent days differ clearly from your usual weeks. Single different days are normal."
            : `A risk is shown when at least ${obs.params.flag_days} of the last ${obs.params.flag_window} days differ clearly
              (more than ${obs.params.deviation_z} SD) in that direction, from ${tl.persona.name}'s usual weeks or from healthy people;
              crisis or self-harm sites as soon as they rise above the usual level.`}</p>
        </div>
        <FlagGroup title={person ? null : `Compared with ${tl.persona.name}'s usual weeks`}
          flags={obs.flags.filter((f) => f.basis !== "reference")}
          empty={currentDays === 0
            ? `The comparison starts after the ${labels.baseline.toLowerCase()} (${person ? "your first" : "the first"} 14 days).`
            : null}
          calm={`Nothing stands out: the recent days are within ${person ? "your" : `${tl.persona.name}'s`} usual range.`}
          renderFlag={renderFlag} sort={sortSeen} />
        {obs.reference && (
          <FlagGroup title="Compared with healthy people"
            note={<>Healthy reference: {obs.reference.n_days} healthy days of {obs.reference.people.join(" and ")} (their everyday weeks, without
              {" "}{tl.persona.name}). A small reference that mixes lifestyles: a difference can reflect a lifestyle (student vs. office job)
              rather than health. Works from the first week, before {tl.persona.name}'s own baseline exists.</>}
            flags={obs.flags.filter((f) => f.basis === "reference")}
            empty={null}
            calm={`Nothing stands out: the recent days are within the healthy range.`}
            renderFlag={renderFlag} sort={sortSeen} />
        )}
      </section>

      <section className="card">
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
          <label className="toggle"><input type="checkbox" checked={nightShade} onChange={(e) => setNightShade(e.target.checked)} /> Shade night (22–06)</label>
          <label className="toggle"><input type="checkbox" checked={midnight} onChange={(e) => setMidnight(e.target.checked)} /> Mark midnight</label>
        </div>

        <h3 className="chart-title">Day and night</h3>
        <p className="sub">Minutes in use per hour. Gaps mean no use: asleep, away or devices off look the same from the network.</p>
        <DayNight days={days} nightShade={nightShade} midnight={midnight} selectedDay={selectedDay} onSelectDay={onSelectDay} />

        <h3 className="chart-title">Quiet window at night</h3>
        <p className="sub">When the devices went quiet and came back online{person ? "" : " (longest stretch without use overlapping 00:00–06:00; a short check at night does not end it)"}.
          Dots mark use during the night. The bands show the usual times{obs.reference ? "; dashed: healthy people" : ""}.</p>
        <QuietWindows tl={tl} days={days} flagged={new Set((flagsByTrack.get("quiet_start") ?? []).concat(flagsByTrack.get("quiet_end") ?? [], flagsByTrack.get("quiet_hours") ?? []).flatMap((f) => f.days))}
          selectedDay={selectedDay} onSelectDay={onSelectDay} />

        <h3 className="chart-title">Day by day</h3>
        <p className="sub band-key">
          <span><i className="key-band" /> {person ? "your" : `${tl.persona.name}'s`} usual range</span>
          {obs.reference && <span><i className="key-band key-band-ref" /> healthy people</span>}
          <span><i className="key-dot" /> clearly different{obs.reference ? " from the usual range" : ""}</span>
          {obs.reference && <span><i className="key-dot key-dot-ref" /> clearly different from healthy people only</span>}
        </p>
        <div className="chips legend-chips" role="group" aria-label="Show or hide rows">
          {rows.map((t) => (
            <button key={t.key} className={`chip ${hidden.has(t.key) ? "chip-off" : "chip-on-soft"} ${flagsByTrack.has(t.key) ? "chip-flag" : ""}`}
              onClick={() => setHidden((h) => { const n = new Set(h); if (n.has(t.key)) n.delete(t.key); else n.add(t.key); return n; })}
              onMouseEnter={() => setFocus(t.key)} onMouseLeave={() => setFocus(null)}
              aria-pressed={!hidden.has(t.key)}>
              {t.label}
            </button>
          ))}
        </div>
        <div className="track-rows">
          {rows.filter((t) => !hidden.has(t.key)).map((t) => (
            <div key={t.key} className={`track-row ${focus && focus !== t.key ? "dim" : ""}`}>
              <div className="track-head">
                <span className="track-name">{t.label}</span>
                {obs.usual[t.key] && <span className="muted small">usual {fmtValue(t.key, obs.usual[t.key].mean)} ± {fmtValue(t.key, obs.usual[t.key].sd)}</span>}
                {obs.reference?.stats[t.key] && <span className="muted small">· healthy {fmtValue(t.key, obs.reference.stats[t.key].mean)} ± {fmtValue(t.key, obs.reference.stats[t.key].sd)}</span>}
                {(flagsByTrack.get(t.key) ?? []).map((f) => <span key={f.id} className="pill pill-red">{f.title}</span>)}
              </div>
              <TrackChart tl={tl} days={days} track={t.key} group={group} selectedDay={selectedDay} onSelectDay={onSelectDay} />
            </div>
          ))}
        </div>
      </section>
    </>
  );
}

function selectedIndex(days: Day[], d: string | null) {
  return days.findIndex((x) => x.date === d);
}

/** Robin Z-style course over time: minutes in use per hour, night shading and midnight lines. */
function DayNight({ days, nightShade, midnight, selectedDay, onSelectDay }: {
  days: Day[]; nightShade: boolean; midnight: boolean; selectedDay: string | null; onSelectDay: (d: string) => void;
}) {
  const option = useMemo(() => {
    const ts = (date: string, h: number) => new Date(`${date}T${String(h).padStart(2, "0")}:00:00`).getTime();
    const data: [number, number | null][] = [];
    const noData: object[] = [];
    for (const d of days) {
      const a = d.observed?.active_hourly;
      if (!a || !d.observed?.has_data) {
        noData.push([{ xAxis: ts(d.date, 0), itemStyle: { color: "rgba(138,131,124,0.12)" } }, { xAxis: ts(d.date, 0) + 864e5 }]);
        data.push([ts(d.date, 0), null]);
        continue;
      }
      a.forEach((v, h) => data.push([ts(d.date, h) + 18e5, v]));
    }
    const nights = nightShade ? days.map((d) => [
      { xAxis: ts(d.date, 0) - 2 * 36e5, itemStyle: { color: "rgba(38,38,38,0.05)" } }, { xAxis: ts(d.date, 6) },
    ]) : [];
    const midnights = midnight ? days.map((d) => ({ xAxis: ts(d.date, 0) })) : [];
    const sel = days.find((d) => d.date === selectedDay);
    return {
      animation: false,
      grid: { left: 40, right: 12, top: 10, bottom: 28 },
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
        type: "time", min: days.length ? ts(days[0].date, 0) : undefined,
        max: days.length ? ts(days[days.length - 1].date, 0) + 864e5 : undefined,
        axisLabel: { color: C.text2, fontSize: 10, formatter: "{dd}/{MM}" }, splitLine: { show: false },
        axisLine: { lineStyle: { color: C.grid } },
      },
      yAxis: { type: "value", min: 0, max: 60, interval: 30, axisLabel: { color: C.text2, fontSize: 10, formatter: "{value}′" }, splitLine: { lineStyle: { color: C.grid } } },
      series: [{
        type: "line", data, step: "middle", symbol: "none", connectNulls: false,
        lineStyle: { width: 1.2, color: C.ink }, areaStyle: { color: "rgba(38,38,38,0.22)" },
        markArea: { silent: true, data: [...nights, ...noData, ...(sel ? [[{ xAxis: ts(sel.date, 0), itemStyle: { color: "rgba(220,58,79,0.08)" } }, { xAxis: ts(sel.date, 0) + 864e5 }]] : [])] },
        markLine: { silent: true, symbol: "none", label: { show: false }, lineStyle: { color: C.muted, type: "dashed", width: 1 }, data: midnights },
      }],
    };
  }, [days, nightShade, midnight, selectedDay]);
  return <Chart option={option} height={170} ariaLabel="Minutes in use per hour over the selected days"
    onClick={(p) => { const v = (p.data as [number, number])?.[0]; if (v) { const d = new Date(v - 18e5); onSelectDay(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`); } }} />;
}

/** Sleep-diary style: one bar per night from going quiet to coming back, with the usual times. */
function QuietWindows({ tl, days, flagged, selectedDay, onSelectDay }: {
  tl: Timeline; days: Day[]; flagged: Set<string>; selectedDay: string | null; onSelectDay: (d: string) => void;
}) {
  const option = useMemo(() => {
    const usual = tl.observed?.usual ?? {};
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
    const band = (k: string, color: string) => usual[k]
      ? [[{ yAxis: usual[k].mean - usual[k].sd, itemStyle: { color } }, { yAxis: usual[k].mean + usual[k].sd }]] : [];
    const ref = tl.observed?.reference?.stats ?? {};
    const refBand = (k: string) => ref[k]
      ? [[{ yAxis: ref[k].mean - ref[k].sd, itemStyle: REF_BAND }, { yAxis: ref[k].mean + ref[k].sd }]] : [];
    const sel = selectedIndex(days, selectedDay);
    return {
      animation: false,
      grid: { left: 48, right: 12, top: 8, bottom: 28 },
      tooltip: {
        trigger: "item",
        formatter: (p: { seriesIndex: number; data: number[] }) => {
          const d = days[p.data[0]];
          const o = d?.observed;
          if (!o) return "";
          const head = `<b>${d.weekday} ${fmtDay(d.date)}</b>${flagged.has(d.date) ? " · <b>different from usual</b>" : ""}`;
          if (o.quiet_start === null) return `${head}<br/>no quiet window found (no data, or no use at all)`;
          return `${head}<br/>went quiet ${fmtClock(o.quiet_start)}, back online ${fmtClock(o.quiet_end)} (${fmtHours(o.quiet_hours)})<br/>use at night (00–06): ${fmtNum(o.night_minutes, 0)} min`;
        },
      },
      xAxis: { type: "category", data: days.map((d) => fmtDay(d.date)), axisLabel: { color: C.text2, fontSize: 10 }, axisTick: { show: false }, axisLine: { lineStyle: { color: C.grid } } },
      yAxis: {
        type: "value", inverse: true, min: -360, max: 840, interval: 120,
        axisLabel: { color: C.text2, fontSize: 10, formatter: (v: number) => fmtClock(v) }, splitLine: { lineStyle: { color: C.grid } },
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
            const d = days[i];
            const isFlag = flagged.has(d.date);
            return {
              type: "rect", shape: { x: x - w / 2, y: y0, width: w, height: y1 - y0, r: 4 },
              style: {
                fill: d.phase === "current" ? "#cfc6bc" : C.baseline,
                stroke: isFlag ? C.critical : i === sel ? C.ink : null, lineWidth: isFlag || i === sel ? 2 : 0,
              },
            };
          },
          markArea: {
            silent: true,
            data: [...band("quiet_start", "rgba(168,112,44,0.12)"), ...band("quiet_end", "rgba(168,112,44,0.12)"),
              ...refBand("quiet_start"), ...refBand("quiet_end")],
          },
        },
        { type: "scatter", data: dots, symbolSize: 5, itemStyle: { color: C.critical }, tooltip: { show: false }, silent: true },
      ],
    };
  }, [tl, days, flagged, selectedDay]);
  return <Chart option={option} height={230} ariaLabel="Quiet window per night"
    onClick={(p) => { const i = (p.data as number[])?.[0]; if (days[i]) onSelectDay(days[i].date); }} />;
}

/** One behaviour track per day with the usual range (mean ± 1 SD) and clearly different days in red. */
function TrackChart({ tl, days, track, group, selectedDay, onSelectDay }: {
  tl: Timeline; days: Day[]; track: string; group: string; selectedDay: string | null; onSelectDay: (d: string) => void;
}) {
  const option = useMemo(() => {
    const usual = tl.observed?.usual[track];
    const z = tl.observed?.params.deviation_z ?? 1.5;
    const sensitive = track === "sensitive_days";
    const vals = days.map((d) => (d.observed ? (d.observed as unknown as Record<string, number | null>)[track] ?? null : null));
    const cur = days.map((d, i) => (d.phase === "current" ? i : -1)).filter((i) => i >= 0);
    const sel = selectedIndex(days, selectedDay);
    const risk = tl.observed?.tracks.find((t) => t.key === track)?.risk ?? [];
    const ref = tl.observed?.reference?.stats[track];
    const riskBeyond = (dev: number | null | undefined) => dev !== null && dev !== undefined && risk.some((r) => dev * r >= z);
    // filled red: clearly different from the usual range in the risk direction; hollow red: only from
    // healthy people; larger grey point: clearly different from the usual range the other way
    const data = vals.map((v, i) => {
      const o = days[i].observed;
      const dev = o?.deviation?.[track];
      const strong = dev !== null && dev !== undefined && Math.abs(dev) >= z;
      const red = sensitive ? !!v : riskBeyond(dev);
      const refOnly = !sensitive && !red && riskBeyond(o?.deviation_ref?.[track]);
      return {
        value: v, symbolSize: red || strong || refOnly ? 8 : 5,
        itemStyle: refOnly ? { color: "#fff", borderColor: C.critical, borderWidth: 2 }
          : { color: red ? C.critical : strong ? C.text2 : C.ink },
      };
    });
    return {
      animation: false,
      grid: { left: 48, right: 12, top: 8, bottom: 22 },
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
          return `<b>${d.weekday} ${fmtDay(d.date)}</b><br/>${fmtValue(track, v)}`
            + (dev !== null && dev !== undefined && Math.abs(dev) >= z ? "<br/><b>different from the usual range</b>" : "")
            + (dref !== null && dref !== undefined && Math.abs(dref) >= z ? "<br/><b>different from healthy people</b>" : "");
        },
      },
      xAxis: { type: "category", data: days.map((d) => fmtDay(d.date)), axisLabel: { color: C.text2, fontSize: 9 }, axisTick: { show: false }, axisLine: { lineStyle: { color: C.grid } } },
      yAxis: sensitive
        ? { type: "value", min: 0, max: 1, show: false }
        : { type: "value", scale: true, splitNumber: 3, axisLabel: { color: C.text2, fontSize: 9, formatter: (v: number) => (track === "online_hours" ? `${v} h` : fmtNum(v, 0)) }, splitLine: { lineStyle: { color: C.grid } } },
      series: [{
        type: sensitive ? "bar" : "line", data, barWidth: "40%", connectNulls: false, symbol: "circle",
        lineStyle: { width: 1.5, color: C.ink },
        markArea: {
          silent: true,
          data: [
            ...(usual ? [[{ yAxis: usual.mean - usual.sd, itemStyle: { color: C.baselineBand } }, { yAxis: usual.mean + usual.sd }]] : []),
            ...(ref ? [[{ yAxis: ref.mean - ref.sd, itemStyle: REF_BAND }, { yAxis: ref.mean + ref.sd }]] : []),
            ...(cur.length ? [[{ xAxis: cur[0], itemStyle: { color: C.clinicalTint } }, { xAxis: cur[cur.length - 1] }]] : []),
          ],
        },
        markLine: sel >= 0 ? { silent: true, symbol: "none", label: { show: false }, lineStyle: { color: C.text, width: 1, type: "solid" }, data: [{ xAxis: sel }] } : undefined,
      }],
    };
  }, [tl, days, track, selectedDay]);
  return <Chart option={option} height={track === "sensitive_days" ? 70 : 110} group={group} ariaLabel={`Daily values: ${track}`}
    onClick={(p) => days[p.dataIndex] && onSelectDay(days[p.dataIndex].date)} />;
}

function FlagGroup({ title, note, flags, empty, calm, renderFlag, sort }: {
  title: string | null; note?: React.ReactNode; flags: RiskFlag[]; empty: string | null; calm: string;
  renderFlag: (f: RiskFlag) => React.ReactNode; sort: (fs: RiskFlag[]) => RiskFlag[];
}) {
  return (
    <div className="flag-group">
      {title && <h3 className="flag-group-title">{title}</h3>}
      {note && <p className="muted small flag-note">{note}</p>}
      {empty ? <p className="muted">{empty}</p>
        : flags.length === 0 ? <p className="calm">{calm}</p>
          : <ul className="flags">{sort(flags).map(renderFlag)}</ul>}
    </div>
  );
}
