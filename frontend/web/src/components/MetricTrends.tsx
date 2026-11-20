import { type ReactNode, useMemo, useState } from "react";
import type { Config, CritKey, Day, MetricSpec, Timeline } from "../api";
import { axisName, BAND_LABELS, baselineMarkArea, intensityColor, mergeMarkAreas, usualBand } from "../lib/chart";
import { fmtDay, fmtNum } from "../lib/format";
import { C } from "../theme";
import { Chart } from "./Chart";
import { Icon } from "./Icon";
import { metricName } from "../lib/metrics";

type Props = {
  tl: Timeline;
  cfg: Config;
  crit: CritKey;
  theta: number;
  present: boolean[];
  presentLabel: string;
  selectedDay: string | null;
  onSelectDay: (d: string) => void;
};

// ---------------------------------------------------------------------------------------------
// "What contributed" (D7): a plain-language sentence from the L = Σ w × μ breakdown, deterministic.

/** How a metric reads in a sentence: "<n> <noun> with <desc>". Written for the direction that counts. */
type Phrase = { noun: "days" | "nights" | "mornings"; desc: string };

const PHRASES: Record<string, Phrase> = {
  F1_DistinctSocial: { noun: "days", desc: "many different social and messaging sites" },
  F4_DownUpRatio: { noun: "days", desc: "much more received than sent" },
  F6_Fano: { noun: "days", desc: "very bursty use" },
  F7_HourlyCV: { noun: "days", desc: "use very uneven across the hours" },
  F8_NightDayRatioPkts: { noun: "nights", desc: "a large share of the day's use falling at night" },
  C2_F1_UniqueSLD: { noun: "days", desc: "few different websites" },
  C2_F3_ChatSessionCount: { noun: "days", desc: "few chat sessions" },
  C2_F4_MeanUpstreamRateBps: { noun: "days", desc: "little sent (posts, calls, uploads)" },
  C2_F6_ProductivityHits: { noun: "days", desc: "little use of work and study tools" },
  C4_F2_WakeAfter0400Min: { noun: "mornings", desc: "the first use long after 04:00" },
  C4_F4_SleepDurationZAbs30d: { noun: "nights", desc: "a quiet window unlike the last weeks" },
  C4_F7_DaytimeIdleRatio0818: { noun: "days", desc: "long quiet stretches between 08:00 and 18:00" },
  C4_F8_NightDayTrafficRatioBytes: { noun: "nights", desc: "a large share of the day's data used at night" },
  C8_F2_DNSBurstRatePerHour: { noun: "days", desc: "many sites opened in quick succession" },
  C8_F4_RepeatedQueryRatio60m: { noun: "days", desc: "the same sites opened again and again" },
  C8_F8_MedianIKSsec: { noun: "days", desc: "long pauses between actions" },
};

const SINGULAR = { days: "day", nights: "night", mornings: "morning" } as const;

export function metricPhrase(key: string, spec: MetricSpec | undefined, labels: Record<string, string>): Phrase {
  if (PHRASES[key]) return PHRASES[key];
  const label = (labels[key] ?? key).toLowerCase();
  return { noun: "days", desc: `${spec?.mf.invert ? "low" : "high"} ${label}` };
}

/** Unit of a metric's daily value, for the y-axis name. */
const UNITS: Record<string, string> = {
  F1_DistinctSocial: "sites per day",
  F4_DownUpRatio: "ratio received / sent",
  F6_Fano: "Fano factor",
  F7_HourlyCV: "coefficient of variation",
  F8_NightDayRatioPkts: "ratio night / day",
  C2_F1_UniqueSLD: "sites per day",
  C2_F3_ChatSessionCount: "count per day",
  C2_F4_MeanUpstreamRateBps: "bytes per second",
  C2_F6_ProductivityHits: "count per day",
  C4_F2_WakeAfter0400Min: "minutes after 04:00",
  C4_F4_SleepDurationZAbs30d: "|z| vs. 30 days",
  C4_F7_DaytimeIdleRatio0818: "share 0–1",
  C4_F8_NightDayTrafficRatioBytes: "ratio night / day",
  C8_F2_DNSBurstRatePerHour: "bursts per hour",
  C8_F4_RepeatedQueryRatio60m: "share 0–1",
  C8_F8_MedianIKSsec: "seconds",
};

export function metricUnit(key: string): string {
  if (UNITS[key]) return UNITS[key];
  if (/Min$/.test(key)) return "minutes";
  if (/(sec|Sec|Seconds)$/.test(key)) return "seconds";
  if (/Bps$/.test(key)) return "bytes per second";
  if (/Ratio/.test(key)) return "ratio";
  if (/(Count|Hits|Visits|Sessions)$/.test(key)) return "count per day";
  return "value";
}

/** A day counts as an outlier for a metric when the metric scores at least this μ on it. */
export const OUTLIER_MU = 0.5;
const MAX_DATES = 4;

export interface Contribution {
  metric: string;
  share: number;          // of Σ w × μ over the days considered
  outlierDays: string[];  // dates with μ >= OUTLIER_MU
  phrase: Phrase;
}

export interface WhatContributed { text: string; items: Contribution[] }

const dateList = (dates: string[]) => {
  const shown = dates.slice(0, MAX_DATES).map(fmtDay).join(", ");
  return dates.length > MAX_DATES ? `${shown} and ${dates.length - MAX_DATES} more` : shown;
};

function part(c: Contribution): string {
  const n = c.outlierDays.length;
  if (n === 0) return `smaller shifts towards ${c.phrase.desc} on most ${c.phrase.noun}`;
  return `${n} ${n === 1 ? SINGULAR[c.phrase.noun] : c.phrase.noun} with ${c.phrase.desc} (${dateList(c.outlierDays)})`;
}

const joinAnd = (xs: string[]) => (xs.length <= 1 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`);

/**
 * Plain-language summary of what drove L for one criterion over the given days: the metrics with the
 * largest Σ w × μ (until they explain 75 % of it, at most 3, each at least 10 %), and per metric the
 * days on which it scored μ >= 0.5. No numbers beyond counts and dates, so it reads without the model.
 */
export function whatContributed(days: Day[], crit: CritKey, cfg: Config): WhatContributed {
  const spec = cfg.criteria[crit] ?? {};
  const sum: Record<string, number> = {};
  const outliers: Record<string, string[]> = {};
  for (const d of days) {
    for (const [k, p] of Object.entries(d.parts[crit] ?? {})) {
      const c = (p.w ?? spec[k]?.w ?? 0) * (p.mu ?? 0);
      sum[k] = (sum[k] ?? 0) + c;
      if ((p.mu ?? 0) >= OUTLIER_MU) (outliers[k] ??= []).push(d.date);
    }
  }
  const total = Object.values(sum).reduce((a, b) => a + b, 0);
  if (!days.length) return { text: "No complete days in this period yet.", items: [] };
  if (total <= 1e-9) return { text: "Nothing contributed: none of the metrics moved into the range where it counts.", items: [] };

  const ranked = Object.entries(sum).filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  const items: Contribution[] = [];
  let cum = 0;
  for (const [k, v] of ranked) {
    const share = v / total;
    if (items.length >= 3 || (items.length > 0 && (cum >= 0.75 || share < 0.1))) break;
    items.push({ metric: k, share, outlierDays: (outliers[k] ?? []).sort(), phrase: metricPhrase(k, spec[k], cfg.metric_labels) });
    cum += share;
  }
  const lead = items.length === 1 && items[0].share >= 0.9 ? "Almost entirely" : "Mainly";
  const text = `${lead} ${joinAnd(items.map(part))}.`;
  return { text, items };
}

/** The days the sentence is about: the complete days of the current period, else all complete days. */
export function contributionDays(tl: Timeline): Day[] {
  const cur = tl.days.filter((d) => d.phase === "current" && d.complete);
  return cur.length ? cur : tl.days.filter((d) => d.complete);
}

// ---------------------------------------------------------------------------------------------

function baseOption(tl: Timeline, selectedDay: string | null) {
  const sel = tl.days.findIndex((d) => d.date === selectedDay);
  return {
    animation: false,
    xAxis: {
      type: "category", data: tl.days.map((d) => fmtDay(d.date)), boundaryGap: true,
      axisLabel: { color: C.text2, fontSize: 10 }, axisTick: { show: false },
      axisLine: { lineStyle: { color: C.grid } },
    },
    tooltip: { trigger: "axis", axisPointer: { type: "line", lineStyle: { color: C.muted } } },
    _sel: sel,
  };
}

const selLine = (sel: number) => (sel >= 0 ? [{ xAxis: sel, lineStyle: { color: C.text, width: 1, type: "solid" }, label: { show: false } }] : []);

/** Key under a chart: every line and band named (rule §2.5). */
function ChartKey({ items }: { items: { swatch: ReactNode; label: string }[] }) {
  return (
    <div className="chart-key small muted" style={{ display: "flex", flexWrap: "wrap", gap: "4px 14px", margin: "2px 0 6px" }}>
      {items.map((it) => <span key={it.label} className="key">{it.swatch}{it.label}</span>)}
    </div>
  );
}

const sw = {
  line: (color: string, dashed = false) => <i style={{ display: "inline-block", width: 16, height: 0, borderTop: `2px ${dashed ? "dashed" : "solid"} ${color}`, margin: "0 5px 3px 0", verticalAlign: "middle" }} />,
  dot: (color: string) => <i className="dot" style={{ background: color, marginRight: 5 }} />,
  band: (color: string) => <i style={{ display: "inline-block", width: 16, height: 10, background: color, borderRadius: 2, margin: "0 5px 0 0", verticalAlign: -1 }} />,
};

export function MetricTrends({ tl, cfg, crit, theta, present, presentLabel, selectedDay, onSelectDay }: Props) {
  const [model, setModel] = useState(false);
  const spec = cfg.criteria[crit] ?? {};
  const metrics = Object.entries(spec).sort((a, b) => b[1].w - a[1].w);
  const why = useMemo(() => whatContributed(contributionDays(tl), crit, cfg), [tl, crit, cfg]);
  const period = tl.profile.phase_labels.current.toLowerCase();
  const hasBaseline = tl.days.some((d) => d.phase === "baseline");

  const lOption = useMemo(() => {
    const b = baseOption(tl, selectedDay);
    const L = tl.days.map((d) => d.L[crit]);
    return {
      ...b,
      grid: { left: 64, right: 12, top: 28, bottom: 28 },
      yAxis: {
        type: "value", min: 0, max: 1, splitNumber: 4, ...axisName("likelihood", "0–1", 34),
        axisLabel: { color: C.text2, fontSize: 10 }, splitLine: { lineStyle: { color: C.grid } },
      },
      tooltip: {
        ...b.tooltip,
        formatter: (ps: { dataIndex: number }[]) => {
          const i = ps[0].dataIndex; const d = tl.days[i];
          return `<b>${d.date}</b>, ${d.phase === "current" ? period : d.phase}<br/>likelihood ${fmtNum(L[i])}${present[i] ? `, <b style="color:${C.alert}">${presentLabel}</b>` : ""}`;
        },
      },
      series: [{
        name: `likelihood ${crit}`, type: "line", data: L, symbol: "circle", symbolSize: 8, showSymbol: true,
        lineStyle: { width: 2, color: C.ink },
        itemStyle: { color: (p: { dataIndex: number }) => (present[p.dataIndex] ? C.alert : C.ink), borderColor: C.surface, borderWidth: 2 },
        markArea: baselineMarkArea(tl.days),
        markLine: {
          silent: true, symbol: "none",
          data: [
            { yAxis: theta, lineStyle: { color: C.muted, type: "dashed", width: 1 }, label: { formatter: `threshold ${theta.toFixed(2)}`, color: C.text2, fontSize: 10, position: "insideEndTop" } },
            ...selLine(b._sel),
          ],
        },
      }],
    };
  }, [tl, crit, theta, present, presentLabel, selectedDay, period]);

  return (
    <section className="card">
      <div className="card-head">
        <h2><span className="step">4</span>Why: {crit} {cfg.criterion_names[crit]}</h2>
        <p className="sub">The likelihood over time, and the network metrics it is built from. Pick another criterion in the overview.</p>
      </div>

      <div className="contrib" role="note" style={{ border: "1px solid var(--border)", borderRadius: 12, padding: "10px 14px", margin: "0 0 12px" }}>
        <div className="small muted" style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <Icon name="explain" label="What contributed" /> What contributed in the {period} period
        </div>
        <p style={{ margin: "4px 0 0" }} data-testid="what-contributed">{why.text}</p>
      </div>

      <div className="row-between" style={{ marginBottom: 6 }}>
        <span />
        <label className="toggle">
          <input type="checkbox" checked={model} onChange={(e) => setModel(e.target.checked)} /> Show model details
        </label>
      </div>
      {model && (
        <div className="small" style={{ color: "var(--text2)", margin: "0 0 10px", maxWidth: 880 }}>
          <p style={{ margin: 0 }}>
            L<sub>{crit}</sub> = Σ w × μ(metric). Each metric's daily value is turned into a score μ between 0 and 1
            (0 below lo, rising to 1 at mid, staying 1 up to hi; inverted metrics count when they are low) and weighted
            with w. A criterion is present when L ≥ θ = {theta.toFixed(2)} on enough days. z = (value − baseline mean) / baseline SD.
            A day counts as an outlier in the sentence above when μ ≥ {OUTLIER_MU}.
          </p>
          {why.items.length > 0 && (
            <table className="breakdown" style={{ marginTop: 6 }}>
              <thead><tr><th>Metric</th><th className="num">w</th><th className="num">share of Σ w × μ</th><th className="num">days μ ≥ {OUTLIER_MU}</th></tr></thead>
              <tbody>
                {why.items.map((it) => (
                  <tr key={it.metric}>
                    <td>{metricName(it.metric, cfg)}</td>
                    <td className="num">{spec[it.metric]?.w ?? "–"}</td>
                    <td className="num">{Math.round(it.share * 100)} %</td>
                    <td className="num">{it.outlierDays.length}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      <Chart option={lOption} height={180} ariaLabel={`Daily likelihood of ${crit}`}
        onClick={(p) => tl.days[p.dataIndex] && onSelectDay(tl.days[p.dataIndex].date)} />
      <ChartKey items={[
        { swatch: sw.line(C.ink), label: `daily likelihood ${crit}` },
        { swatch: sw.dot(C.alert), label: presentLabel },
        { swatch: sw.line(C.muted, true), label: `threshold for "present" (${theta.toFixed(2)})` },
        ...(hasBaseline ? [{ swatch: sw.band(C.baselineShade), label: BAND_LABELS.baseline }] : []),
      ]} />

      <div className="metric-grid">
        {metrics.map(([key, m]) => (
          <MetricChart key={key} tl={tl} cfg={cfg} crit={crit} metric={key} w={m.w}
            lo={m.mf.lo} hi={m.mf.hi} mid={m.mf.mid} invert={!!m.mf.invert} model={model}
            selectedDay={selectedDay} onSelectDay={onSelectDay} />
        ))}
      </div>
      <ChartKey items={[
        { swatch: sw.line(C.text2), label: "daily value" },
        { swatch: sw.band(C.usualBand), label: `${BAND_LABELS.usual} (baseline mean ± 1 SD)` },
        ...(hasBaseline ? [{ swatch: sw.band(C.baselineShade), label: BAND_LABELS.baseline }] : []),
        ...(model ? [
          { swatch: sw.line(C.muted, true), label: "lo / hi: where the metric starts and stops counting" },
          { swatch: <><i className="dot" style={{ background: C.intensity[0] }} /><i className="dot" style={{ background: C.intensity[C.intensity.length - 1], marginRight: 5 }} /></>, label: "dot shade = μ of the day (light 0 → dark 1)" },
        ] : []),
      ]} />
    </section>
  );
}

type MProps = {
  tl: Timeline; cfg: Config; crit: CritKey; metric: string; w: number;
  lo: number; mid: number; hi: number; invert: boolean; model: boolean;
  selectedDay: string | null; onSelectDay: (d: string) => void;
};

function MetricChart({ tl, cfg, crit, metric, w, lo, mid, hi, invert, model, selectedDay, onSelectDay }: MProps) {
  const unit = metricUnit(metric);
  const option = useMemo(() => {
    const b = baseOption(tl, selectedDay);
    const vals = tl.days.map((d) => {
      const v = d.metrics[metric];
      return typeof v === "number" ? v : null;
    });
    const mus = tl.days.map((d) => d.parts[crit]?.[metric]?.mu ?? null);
    const stats = tl.baseline_stats[metric];
    return {
      ...b,
      grid: { left: 64, right: 12, top: 22, bottom: 24 },
      yAxis: {
        type: "value", scale: true, splitNumber: 3, ...axisName(unit, undefined, 46),
        axisLabel: { color: C.text2, fontSize: 10, formatter: (v: number) => fmtNum(v, 1) },
        splitLine: { lineStyle: { color: C.grid } },
      },
      tooltip: {
        ...b.tooltip,
        formatter: (ps: { dataIndex: number }[]) => {
          const i = ps[0].dataIndex; const d = tl.days[i];
          const v = vals[i];
          let s = `<b>${d.date}</b><br/>${fmtNum(v)} ${unit === "value" ? "" : unit}`;
          if (stats) s += `<br/><span style="color:${C.text2}">usual ${fmtNum(stats.mean - stats.sd)}–${fmtNum(stats.mean + stats.sd)}</span>`;
          if (model) {
            const z = stats && stats.sd > 0 && v != null ? (v - stats.mean) / stats.sd : null;
            s += `<br/><span style="color:${C.text2}">μ ${fmtNum(mus[i])} × w ${w} = ${fmtNum((mus[i] ?? 0) * w)}${z != null ? `, z ${fmtNum(z, 1)}` : ""}</span>`;
          }
          return s;
        },
      },
      series: [{
        name: metric, type: "line", data: vals, connectNulls: false,
        symbol: "circle", symbolSize: 7, lineStyle: { width: 2, color: C.text2 },
        itemStyle: model ? {
          // dot shade: how strongly the day counts towards L (μ), neutral intensity scale
          color: (p: { dataIndex: number }) => intensityColor(mus[p.dataIndex] ?? 0),
          borderColor: C.surface, borderWidth: 1,
        } : { color: C.text2, borderColor: C.surface, borderWidth: 1 },
        markArea: mergeMarkAreas(baselineMarkArea(tl.days, { label: false }), usualBand(stats)),
        markLine: {
          silent: true, symbol: "none",
          data: [
            ...(model ? [
              { yAxis: lo, lineStyle: { color: C.muted, type: "dashed" }, label: { formatter: "lo", color: C.muted, fontSize: 9, position: "insideStartTop" } },
              ...(hi !== lo ? [{ yAxis: hi, lineStyle: { color: C.muted, type: "dashed" }, label: { formatter: mid === hi ? "mid=hi" : "hi", color: C.muted, fontSize: 9, position: "insideStartTop" } }] : []),
            ] : []),
            ...selLine(b._sel),
          ],
        },
      }],
    };
  }, [tl, metric, crit, w, lo, mid, hi, selectedDay, model, unit]);

  return (
    <div className="metric-card" id={`metric-${metric}`}>
      <div className="metric-head">
        <span className="metric-name">{metricName(metric, cfg)}</span>
        {model && <span className="metric-meta">weight {w}{invert ? ", lower counts" : ""}</span>}
      </div>
      <Chart option={option} height={150} ariaLabel={`Daily values: ${metricName(metric, cfg)} in ${unit}`}
        onClick={(p) => tl.days[p.dataIndex] && onSelectDay(tl.days[p.dataIndex].date)} />
    </div>
  );
}
