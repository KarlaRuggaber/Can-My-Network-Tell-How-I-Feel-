import { Fragment, useEffect, useMemo, useState } from "react";
import type { Block, Config, CritKey, Day, DayDetail as DD, PhaseKey } from "../api";
import { api, CRIT_KEYS } from "../api";
import { fmtDay, fmtNum, fmtTime, minutesInDay } from "../lib/format";
import { fmtClock, fmtHours } from "../lib/observed";
import { axisName } from "../lib/chart";
import { C, deviceColor, deviceRole } from "../theme";
import { Chart } from "./Chart";
import { Icon } from "./Icon";
import { metricName } from "../lib/metrics";

/** Neutral hatch for scripted clinical blocks (rule §2.4: no red for periods). */
const CLIN_HATCH = `repeating-linear-gradient(135deg, ${C.intensity[4]} 0 3px, ${C.intensity[0]} 3px 5px)`;

type Props = {
  onAsk?: (question: string, focus: string) => void;
  profileId: string; day: Day; cfg: Config; present: Partial<Record<CritKey, boolean[]>>; dayIndex: number;
  phaseLabels: Record<PhaseKey, string>;
  /** Packets in 5 minutes from which a device counts as "in use" (the overview's rule). */
  activePackets?: number;
};

export function DayDetail({ onAsk, profileId, day, cfg, present, dayIndex, phaseLabels, activePackets = 50 }: Props) {
  const [detail, setDetail] = useState<DD | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [onlyClinical, setOnlyClinical] = useState(false);
  const gt = day.ground_truth;

  useEffect(() => {
    setDetail(null); setErr(null);
    api.day(profileId, day.date).then(setDetail).catch((e) => setErr(String(e.message ?? e)));
  }, [profileId, day.date]);

  const devices = useMemo(() => {
    const fromBlocks = (detail?.blocks ?? []).map((b) => b.device);
    const fromTraffic = Object.keys(detail?.activity?.devices ?? {});
    return [...new Set([...fromTraffic, ...fromBlocks])].sort((a, b) => deviceRole(b).localeCompare(deviceRole(a)));
  }, [detail]);

  // Minutes in use per hour and device: a 5-minute slot counts when the device sent at least
  // `activePackets` packets in it (the same rule as the overview), so background syncing does not count.
  const useOption = useMemo(() => {
    if (!detail?.activity) return null;
    const binMin = detail.activity.bin_minutes;
    const hourly = (bins: number[]) => {
      const out = Array<number>(24).fill(0);
      bins.forEach((v, i) => { if (v >= activePackets) out[Math.min(23, Math.floor((i * binMin) / 60))] += binMin; });
      return out;
    };
    const series = devices.filter((d) => detail.activity!.devices[d]).map((d, i) => ({
      name: deviceRole(d), type: "bar", barGap: "10%", barCategoryGap: "30%",
      data: hourly(detail.activity!.devices[d]), itemStyle: { color: deviceColor(d, i), borderRadius: [2, 2, 0, 0] },
    }));
    return {
      animation: false,
      legend: { top: 0, right: 0, data: series.map((x) => x.name), textStyle: { color: C.text2, fontSize: 11 }, icon: "roundRect", itemWidth: 12, itemHeight: 8 },
      grid: { left: 64, right: 12, top: 28, bottom: 40 },
      tooltip: { trigger: "axis", valueFormatter: (v: number) => `${fmtNum(v)} min in use` },
      xAxis: {
        type: "category", data: Array.from({ length: 24 }, (_, h) => `${String(h).padStart(2, "0")}:00`),
        ...axisName("hour of the day", "hh:00"), nameRotate: 0, nameGap: 24,
        axisLabel: { color: C.text2, fontSize: 10, interval: 2 }, axisTick: { show: false },
        axisLine: { lineStyle: { color: C.grid } },
      },
      yAxis: {
        type: "value", min: 0, max: 60, interval: 15, ...axisName("minutes in use", "per hour", 46),
        axisLabel: { color: C.text2, fontSize: 10 }, splitLine: { lineStyle: { color: C.grid } },
      },
      series,
    };
  }, [detail, devices, activePackets]);

  const activityOption = useMemo(() => {
    if (!detail?.activity) return null;
    const binMin = detail.activity.bin_minutes;
    const n = detail.activity.total.length;
    const xs = Array.from({ length: n }, (_, i) => {
      const m = i * binMin;
      return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
    });
    const series = devices.filter((d) => detail.activity!.devices[d]).map((d, i) => ({
      name: deviceRole(d), type: "line", step: "middle", symbol: "none",
      data: detail.activity!.devices[d], lineStyle: { width: 1.5, color: deviceColor(d, i) },
      itemStyle: { color: deviceColor(d, i) },
      areaStyle: { color: deviceColor(d, i), opacity: 0.12 },
    }));
    return {
      animation: false,
      legend: { top: 0, right: 0, data: series.map((x) => x.name), textStyle: { color: C.text2, fontSize: 11 }, icon: "roundRect", itemWidth: 12, itemHeight: 4 },
      grid: { left: 64, right: 12, top: 28, bottom: 40 },
      tooltip: { trigger: "axis", valueFormatter: (v: number) => `${fmtNum(v)} packets` },
      xAxis: {
        type: "category", data: xs, boundaryGap: false,
        ...axisName("clock time", "hh:mm"), nameRotate: 0, nameGap: 24,
        axisLabel: { color: C.text2, fontSize: 10, interval: 35 }, axisTick: { show: false },
        axisLine: { lineStyle: { color: C.grid } },
      },
      yAxis: {
        type: "value", ...axisName("packets", "per 5 min", 46),
        axisLabel: { color: C.text2, fontSize: 10, formatter: (v: number) => fmtNum(v, 0) },
        splitLine: { lineStyle: { color: C.grid } },
      },
      series,
    };
  }, [detail, devices]);

  const blocks = (detail?.blocks ?? []).filter((b) => !onlyClinical || b.phase === "profile");

  return (
    <section className="card">
      <div className="card-head">
        <h2><span className="step">6</span>{day.weekday} {fmtDay(day.date)} {day.phase === "baseline"
          ? <span className="pill pill-baseline">{phaseLabels.baseline.toLowerCase()}</span>
          : <span className="muted small" style={{ marginLeft: 8, fontFamily: "var(--sans)" }}>{(day.phase === "current" ? phaseLabels.current : day.phase).toLowerCase()}</span>}
          {!day.complete && <span className="pill pill-outline">still being recorded</span>}</h2>
        <p className="sub">{gt ? "When the devices were in use on this day, and what the test person was scripted to do." : "When this person's devices were in use on this day."}</p>
        <details className="howto">
          <summary>How is "in use" counted?</summary>
          <p>
            A device counts as in use for 5 minutes when it sends a clear amount of traffic in them; background syncing alone
            does not count. A day runs from midnight to midnight, so a late evening can show up on the next day.
          </p>
        </details>
      </div>

      <div className="kpis">
        {day.observed?.has_data && <Kpi label="Time in use" value={fmtHours(day.observed.online_hours)} />}
        {day.observed?.has_data && <Kpi label="Went quiet (night before)" value={fmtClock(day.observed.quiet_start)} />}
        {day.observed?.has_data && <Kpi label="Back online" value={fmtClock(day.observed.quiet_end)} />}
        {day.observed?.has_data && day.observed.sites != null && <Kpi label="Different sites" value={fmtNum(day.observed.sites)} />}
        {gt && <Kpi label="Scripted blocks" value={fmtNum(gt.n_blocks)} />}
        {gt && <Kpi label="of them clinical" value={fmtNum(gt.n_profile_blocks)} />}
        {gt && gt.n_sensitive > 0 && <Kpi label="Sensitive blocks" value={fmtNum(gt.n_sensitive)} warn />}
        {gt && gt.n_failed > 0 && <Kpi label="Failed blocks" value={fmtNum(gt.n_failed)} warn />}
      </div>

      {err && <p className="error">{err}</p>}
      {!detail && !err && <p className="muted">Loading day…</p>}

      {detail && activityOption && (
        <>
          {useOption && <Chart option={useOption} height={200} ariaLabel="Minutes in use per hour and device" />}
          {gt && <Gantt blocks={detail.blocks} devices={devices} day={day.date} />}
        </>
      )}

      {detail && activityOption && (
        <details className="fold">
          <summary>Raw network traffic (packets per 5 minutes, {fmtNum(day.packets_kept)} packets on this day)</summary>
          <Chart option={activityOption} height={200} ariaLabel="Packets per 5 minutes per device" />
        </details>
      )}

      <details className="fold">
        <summary>Show model details: score of this day per criterion (L = Σ w × μ)</summary>
        <CriterionBreakdown day={day} cfg={cfg} present={present} dayIndex={dayIndex} onAsk={onAsk} />
      </details>
      {gt && <details className="fold">
        <summary>All scripted blocks of this day ({blocks.length})</summary>
        <div className="row-between">
          <span />
          <label className="toggle">
            <input type="checkbox" checked={onlyClinical} onChange={(e) => setOnlyClinical(e.target.checked)} /> clinical only
          </label>
        </div>
        <BlockTable blocks={blocks} />
      </details>}
    </section>
  );
}

function Kpi({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className={`kpi ${warn ? "kpi-warn" : ""}`}>
      <div className="kpi-value">{value}</div>
      <div className="kpi-label">{label}</div>
    </div>
  );
}

function Gantt({ blocks, devices, day }: { blocks: Block[]; devices: string[]; day: string }) {
  return (
    <div className="gantt" aria-label="Scripted blocks over the day">
      {devices.map((dev, row) => (
        <div className="gantt-row" key={dev}>
          <div className="gantt-label">{deviceRole(dev) === "phone" || deviceRole(dev) === "laptop"
            ? <><Icon name={deviceRole(dev) as "phone" | "laptop"} label={deviceRole(dev)} /> {deviceRole(dev)}</> : deviceRole(dev)}</div>
          <div className="gantt-track">
            {row === 0 && [0, 6, 12, 18].map((h) => <div key={h} className="gantt-hour" style={{ left: `${(h / 24) * 100}%` }}>{String(h).padStart(2, "0")}</div>)}
            {blocks.filter((b) => b.device === dev).map((b) => {
              const s = minutesInDay(b.start, day), e = minutesInDay(b.end, day);
              const cls = ["gantt-bar", b.phase === "profile" ? "clin" : "base", b.flag === "sensitive" ? "sensitive" : "", b.status.startsWith("exit") || b.status === "not run" ? "failed" : "", b.status === "away" ? "away" : ""].join(" ");
              return (
                <div key={b.block_id} className={cls}
                  style={{ left: `${(s / 1440) * 100}%`, width: `max(3px, ${((e - s) / 1440) * 100}%)`, background: b.phase !== "profile" ? deviceColor(dev) : CLIN_HATCH, ...(b.flag === "sensitive" ? { outline: `2px solid ${C.alert}` } : {}) }}
                  title={`${fmtTime(b.start)}–${fmtTime(b.end)} ${b.profile_block} (${b.activity})\n${b.block_id}\nphase: ${b.phase}, status: ${b.status}${b.flag ? ", " + b.flag : ""}`} />
              );
            })}
          </div>
        </div>
      ))}
      <div className="gantt-legend">
        <span><i style={{ background: C.phone }} /> everyday block (phone)</span>
        <span><i style={{ background: C.laptop }} /> everyday block (laptop)</span>
        <span><i style={{ background: CLIN_HATCH }} /> clinical block</span>
        <span style={{ color: C.alert }}><Icon name="alert" label="sensitive" /> sensitive (crisis / self-harm site)</span>
        <span><i className="away-swatch" /><Icon name="away" label="away" /> away (no traffic expected)</span>
      </div>
    </div>
  );
}

function BlockTable({ blocks }: { blocks: Block[] }) {
  if (!blocks.length) return <p className="muted">No scripted blocks on this day.</p>;
  return (
    <div className="table-wrap scroll-y">
      <table className="block-table">
        <thead><tr><th>Time</th><th>Device</th><th>Block</th><th>Activity</th><th>Phase</th><th>Run</th></tr></thead>
        <tbody>
          {blocks.map((b) => (
            <tr key={b.block_id}>
              <td className="nowrap">{fmtTime(b.start)}–{fmtTime(b.end)}</td>
              <td>{deviceRole(b.device)}</td>
              <td title={b.block_id}>
                {b.profile_block}
                {b.flag === "sensitive" && <span className="tag" style={{ borderColor: C.alert, color: C.alert }}>sensitive</span>}
                <div className="note mono">{b.block_id}</div>
              </td>
              <td title={b.mix}>{b.activity}</td>
              <td>{b.phase === "profile" ? "clinical" : b.phase}</td>
              <td className={b.status.startsWith("exit") || b.status === "not run" ? "disagree" : ""}>
                {b.status}{b.late_s ? <div className="note">late {b.late_s}s</div> : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CriterionBreakdown({ day, cfg, present, dayIndex, onAsk }: { day: Day; cfg: Config; present: Partial<Record<CritKey, boolean[]>>; dayIndex: number; onAsk?: (q: string, f: string) => void }) {
  const crits = CRIT_KEYS.filter((c) => day.parts[c]);
  return (
    <div className="table-wrap">
      <table className="breakdown">
        <thead><tr><th>Metric</th><th className="num">Value</th><th className="num">μ</th><th className="num">w × μ</th></tr></thead>
        <tbody>
          {crits.map((c) => (
            <Fragment key={c}>
              <tr className="crit-row">
                <td><b>{c}</b> {cfg.criterion_names[c]}
                  {onAsk && <button className="link small explain-link" onClick={() => onAsk(`Explain the ${c} ${cfg.criterion_names[c]} score of ${fmtNum(day.L[c])} on ${day.date}, metric by metric (value, μ, weight), and what could explain it besides the criterion.`, `day ${day.date}, ${c}`)}>✦ explain</button>}</td>
                <td />
                <td />
                <td className="num"><b>{fmtNum(day.L[c])}</b>{present[c]?.[dayIndex] && <span className="status" style={{ color: C.alert }} title="present"> ● present</span>}</td>
              </tr>
              {Object.entries(day.parts[c]!).sort((a, b) => b[1].w * b[1].mu - a[1].w * a[1].mu).map(([k, m]) => (
                <tr key={c + k}>
                  <td className="indent">{metricName(k, cfg)}</td>
                  <td className="num">{fmtNum(m.value)}</td>
                  <td className="num">{fmtNum(m.mu)}</td>
                  <td className="num">{fmtNum(m.mu * m.w)}</td>
                </tr>
              ))}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}
