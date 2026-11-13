import { Fragment, useEffect, useMemo, useState } from "react";
import type { Block, Config, CritKey, Day, DayDetail as DD, PhaseKey } from "../api";
import { api, CRIT_KEYS } from "../api";
import { fmtDay, fmtNum, fmtTime, minutesInDay } from "../lib/format";
import { C, deviceColor, deviceRole } from "../theme";
import { Chart } from "./Chart";

type Props = {
  profileId: string; day: Day; cfg: Config; present: Partial<Record<CritKey, boolean[]>>; dayIndex: number;
  phaseLabels: Record<PhaseKey, string>;
};

export function DayDetail({ profileId, day, cfg, present, dayIndex, phaseLabels }: Props) {
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
      legend: { top: 0, right: 0, textStyle: { color: C.text2, fontSize: 11 }, icon: "roundRect", itemWidth: 12, itemHeight: 4 },
      grid: { left: 56, right: 12, top: 24, bottom: 24 },
      tooltip: { trigger: "axis", valueFormatter: (v: number) => `${fmtNum(v)} packets` },
      xAxis: {
        type: "category", data: xs, boundaryGap: false,
        axisLabel: { color: C.text2, fontSize: 10, interval: 35 }, axisTick: { show: false },
        axisLine: { lineStyle: { color: C.grid } },
      },
      yAxis: {
        type: "value", name: "packets / 5 min", nameTextStyle: { color: C.text2, fontSize: 10, align: "left" },
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
        <h2><span className="step">4</span>{day.weekday} {fmtDay(day.date)} <span className={`pill ${day.phase === "current" ? "pill-red" : "pill-beige"}`}>{(day.phase === "current" || day.phase === "baseline" ? phaseLabels[day.phase as PhaseKey] : day.phase).toLowerCase()}</span>
          {!day.complete && <span className="pill pill-outline">still being recorded</span>}</h2>
        <p className="sub">{gt ? "What the persona was scripted to do, and the traffic the gateway saw." : "The traffic of this person's devices over the day."}</p>
        <details className="howto">
          <summary>Notes</summary>
          <p>
            Traffic is shown after the app's background filter, the same packets the metrics use. Days are calendar
            days, so a block planned for the evening of one day can show up on the next. {fmtNum(day.n_partitions)} capture
            files on this day.
          </p>
        </details>
      </div>

      <div className="kpis">
        <Kpi label="Packets" value={fmtNum(day.packets_kept)} />
        {gt && <Kpi label="Scripted blocks" value={fmtNum(gt.n_blocks)} />}
        {gt && <Kpi label="of them clinical" value={fmtNum(gt.n_profile_blocks)} />}
        {gt && gt.n_sensitive > 0 && <Kpi label="Sensitive blocks" value={fmtNum(gt.n_sensitive)} warn />}
        {gt && gt.n_failed > 0 && <Kpi label="Failed blocks" value={fmtNum(gt.n_failed)} warn />}
        {day.first_packet && <Kpi label="First – last packet" value={`${fmtTime(day.first_packet)}–${fmtTime(day.last_packet)}`} />}
      </div>

      {err && <p className="error">{err}</p>}
      {!detail && !err && <p className="muted">Loading day…</p>}

      {detail && activityOption && (
        <>
          <Chart option={activityOption} height={200} ariaLabel="Packets per 5 minutes per device" />
          {gt && <Gantt blocks={detail.blocks} devices={devices} day={day.date} />}
        </>
      )}

      <details className="fold">
        <summary>Score of this day per criterion (L = Σ w · μ)</summary>
        <CriterionBreakdown day={day} cfg={cfg} present={present} dayIndex={dayIndex} />
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
          <div className="gantt-label">{deviceRole(dev)}</div>
          <div className="gantt-track">
            {row === 0 && [0, 6, 12, 18].map((h) => <div key={h} className="gantt-hour" style={{ left: `${(h / 24) * 100}%` }}>{String(h).padStart(2, "0")}</div>)}
            {blocks.filter((b) => b.device === dev).map((b) => {
              const s = minutesInDay(b.start, day), e = minutesInDay(b.end, day);
              const cls = ["gantt-bar", b.phase === "profile" ? "clin" : "base", b.flag === "sensitive" ? "sensitive" : "", b.status.startsWith("exit") || b.status === "not run" ? "failed" : "", b.status === "away" ? "away" : ""].join(" ");
              return (
                <div key={b.block_id} className={cls}
                  style={{ left: `${(s / 1440) * 100}%`, width: `max(3px, ${((e - s) / 1440) * 100}%)`, ...(b.phase !== "profile" ? { background: deviceColor(dev) } : {}) }}
                  title={`${fmtTime(b.start)}–${fmtTime(b.end)} ${b.profile_block} (${b.activity})\n${b.block_id}\nphase: ${b.phase} · status: ${b.status}${b.flag ? " · " + b.flag : ""}`} />
              );
            })}
          </div>
        </div>
      ))}
      <div className="gantt-legend">
        <span><i style={{ background: C.phone }} /> everyday block (phone)</span>
        <span><i style={{ background: C.laptop }} /> everyday block (laptop)</span>
        <span><i className="clin-swatch" /> clinical block</span>
        <span><i className="sens-swatch" /> sensitive</span>
        <span><i className="away-swatch" /> away (no traffic expected)</span>
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
            <tr key={b.block_id} className={b.phase === "profile" ? "clin" : ""}>
              <td className="nowrap">{fmtTime(b.start)}–{fmtTime(b.end)}</td>
              <td>{deviceRole(b.device)}</td>
              <td title={b.block_id}>
                {b.profile_block}
                {b.flag === "sensitive" && <span className="tag tag-warn">sensitive</span>}
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

function CriterionBreakdown({ day, cfg, present, dayIndex }: { day: Day; cfg: Config; present: Partial<Record<CritKey, boolean[]>>; dayIndex: number }) {
  const crits = CRIT_KEYS.filter((c) => day.parts[c]);
  return (
    <div className="table-wrap">
      <table className="breakdown">
        <thead><tr><th>Metric</th><th className="num">Value</th><th className="num">μ</th><th className="num">w·μ</th></tr></thead>
        <tbody>
          {crits.map((c) => (
            <Fragment key={c}>
              <tr className="crit-row">
                <td><b>{c}</b> {cfg.criterion_names[c]}</td>
                <td />
                <td />
                <td className="num"><b>{fmtNum(day.L[c])}</b>{present[c]?.[dayIndex] && <span className="status status-on"> ●</span>}</td>
              </tr>
              {Object.entries(day.parts[c]!).sort((a, b) => b[1].w * b[1].mu - a[1].w * a[1].mu).map(([k, m]) => (
                <tr key={c + k}>
                  <td className="indent" title={k}>{cfg.metric_labels[k] ?? k}</td>
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
