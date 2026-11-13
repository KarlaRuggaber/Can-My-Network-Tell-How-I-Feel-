import { useMemo } from "react";
import type { Config, CritKey, Timeline } from "../api";
import { fmtDay, fmtNum } from "../lib/format";
import { C } from "../theme";
import { Chart } from "./Chart";

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

/** Index range [first, last] of a phase, for the shaded band. */
function phaseRange(tl: Timeline, phase: string): [number, number] | null {
  const idx = tl.days.map((d, i) => (d.phase === phase ? i : -1)).filter((i) => i >= 0);
  return idx.length ? [idx[0], idx[idx.length - 1]] : null;
}

function baseOption(tl: Timeline, selectedDay: string | null) {
  const clin = phaseRange(tl, "current");
  const sel = tl.days.findIndex((d) => d.date === selectedDay);
  return {
    animation: false,
    grid: { left: 52, right: 12, top: 28, bottom: 28 },
    xAxis: {
      type: "category", data: tl.days.map((d) => fmtDay(d.date)), boundaryGap: true,
      axisLabel: { color: C.text2, fontSize: 10 }, axisTick: { show: false },
      axisLine: { lineStyle: { color: C.grid } },
    },
    tooltip: { trigger: "axis", axisPointer: { type: "line", lineStyle: { color: C.muted } } },
    _clin: clin,
    _sel: sel,
  };
}

function bands(clin: [number, number] | null, sel: number, clinLabel: string) {
  return {
    markArea: clin ? {
      silent: true, itemStyle: { color: C.clinicalTint },
      label: { show: true, position: "insideTopLeft", color: C.critical, fontSize: 10, formatter: clinLabel },
      data: [[{ xAxis: clin[0] }, { xAxis: clin[1] }]],
    } : undefined,
    markLine: sel >= 0 ? {
      silent: true, symbol: "none", label: { show: false },
      lineStyle: { color: C.text, width: 1, type: "solid" }, data: [{ xAxis: sel }],
    } : undefined,
  };
}

export function MetricTrends({ tl, cfg, crit, theta, present, presentLabel, selectedDay, onSelectDay }: Props) {
  const spec = cfg.criteria[crit] ?? {};
  const metrics = Object.entries(spec).sort((a, b) => b[1].w - a[1].w);

  const lOption = useMemo(() => {
    const b = baseOption(tl, selectedDay);
    const L = tl.days.map((d) => d.L[crit]);
    const bl = bands(b._clin, b._sel, tl.profile.phase_labels.current.toLowerCase());
    return {
      ...b,
      yAxis: { type: "value", min: 0, max: 1, splitNumber: 4, axisLabel: { color: C.text2, fontSize: 10 }, splitLine: { lineStyle: { color: C.grid } } },
      tooltip: {
        ...b.tooltip,
        formatter: (ps: { dataIndex: number }[]) => {
          const i = ps[0].dataIndex; const d = tl.days[i];
          return `<b>${d.date}</b> · ${d.phase}<br/>L<sub>${crit}</sub> = ${fmtNum(L[i])}${present[i] ? ` · <b>${presentLabel}</b>` : ""}`;
        },
      },
      series: [{
        name: `L ${crit}`, type: "line", data: L, symbol: "circle", symbolSize: 8, showSymbol: true,
        lineStyle: { width: 2, color: C.ink }, itemStyle: { color: C.ink, borderColor: C.surface, borderWidth: 2 },
        ...bl,
        markLine: {
          silent: true, symbol: "none",
          data: [
            { yAxis: theta, lineStyle: { color: C.critical, type: "dashed", width: 1 }, label: { formatter: `θ ${theta.toFixed(2)}`, color: C.critical, fontSize: 10, position: "insideEndTop" } },
            ...(b._sel >= 0 ? [{ xAxis: b._sel, lineStyle: { color: C.text, width: 1, type: "solid" }, label: { show: false } }] : []),
          ],
        },
      }],
    };
  }, [tl, crit, theta, present, presentLabel, selectedDay]);

  return (
    <section className="card">
      <div className="card-head">
        <h2><span className="step">3</span>Why: {crit} {cfg.criterion_names[crit]}</h2>
        <p className="sub">The likelihood over time, and the network metrics it is built from. Pick another criterion in the overview.</p>
        <details className="howto">
          <summary>How to read these charts</summary>
          <p>
            L<sub>{crit}</sub> = Σ w · μ(metric): each metric is turned into a score μ between 0 and 1 and weighted
            with w. The metric charts show the daily value, the baseline mean ± 1 SD (tan band) and the range where
            the metric starts to count (lo–hi, dotted). Dot colour = μ of that day. The shaded part is the {tl.profile.phase_labels.current.toLowerCase()} period.
          </p>
        </details>
      </div>
      <Chart option={lOption} height={180} ariaLabel={`Daily likelihood of ${crit}`}
        onClick={(p) => tl.days[p.dataIndex] && onSelectDay(tl.days[p.dataIndex].date)} />
      <div className="metric-grid">
        {metrics.map(([key, m]) => (
          <MetricChart key={key} tl={tl} cfg={cfg} crit={crit} metric={key} w={m.w}
            lo={m.mf.lo} hi={m.mf.hi} mid={m.mf.mid} invert={!!m.mf.invert}
            selectedDay={selectedDay} onSelectDay={onSelectDay} />
        ))}
      </div>
    </section>
  );
}

type MProps = {
  tl: Timeline; cfg: Config; crit: CritKey; metric: string; w: number;
  lo: number; mid: number; hi: number; invert: boolean;
  selectedDay: string | null; onSelectDay: (d: string) => void;
};

function MetricChart({ tl, cfg, crit, metric, w, lo, mid, hi, invert, selectedDay, onSelectDay }: MProps) {
  const option = useMemo(() => {
    const b = baseOption(tl, selectedDay);
    const vals = tl.days.map((d) => {
      const v = d.metrics[metric];
      return typeof v === "number" ? v : null;
    });
    const mus = tl.days.map((d) => d.parts[crit]?.[metric]?.mu ?? null);
    const stats = tl.baseline_stats[metric];
    const bl = bands(b._clin, b._sel, tl.profile.phase_labels.current.toLowerCase());
    const markAreaData: object[] = [...(bl.markArea?.data ?? [])];
    if (stats) {
      markAreaData.push([
        { yAxis: stats.mean - stats.sd, itemStyle: { color: C.baselineBand } },
        { yAxis: stats.mean + stats.sd },
      ]);
    }
    return {
      ...b,
      grid: { left: 56, right: 12, top: 12, bottom: 24 },
      yAxis: {
        type: "value", scale: true, splitNumber: 3,
        axisLabel: { color: C.text2, fontSize: 10, formatter: (v: number) => fmtNum(v, 1) },
        splitLine: { lineStyle: { color: C.grid } },
      },
      tooltip: {
        ...b.tooltip,
        formatter: (ps: { dataIndex: number }[]) => {
          const i = ps[0].dataIndex; const d = tl.days[i];
          return `<b>${d.date}</b> · ${d.phase}<br/>value ${fmtNum(vals[i])}<br/>μ ${fmtNum(mus[i])} × w ${w} = ${fmtNum((mus[i] ?? 0) * w)}` +
            (stats ? `<br/><span style="color:${C.text2}">baseline ${fmtNum(stats.mean)} ± ${fmtNum(stats.sd)}</span>` : "");
        },
      },
      series: [{
        name: metric, type: "line", data: vals, connectNulls: false,
        symbol: "circle", symbolSize: 7, lineStyle: { width: 2, color: C.text2 },
        itemStyle: {
          // dot color: how strongly the day counts towards L (μ)
          color: (p: { dataIndex: number }) => {
            const mu = mus[p.dataIndex] ?? 0;
            return C.seq[Math.min(C.seq.length - 1, Math.round(1 + mu * (C.seq.length - 2)))];
          },
          borderColor: C.text2, borderWidth: 1,
        },
        markArea: { silent: true, itemStyle: { color: C.clinicalTint }, data: markAreaData },
        markLine: {
          silent: true, symbol: "none",
          data: [
            { yAxis: lo, lineStyle: { color: C.muted, type: "dotted" }, label: { formatter: "lo", color: C.muted, fontSize: 9, position: "insideStartTop" } },
            ...(hi !== lo ? [{ yAxis: hi, lineStyle: { color: C.muted, type: "dotted" }, label: { formatter: mid === hi ? "mid=hi" : "hi", color: C.muted, fontSize: 9, position: "insideStartTop" } }] : []),
            ...(b._sel >= 0 ? [{ xAxis: b._sel, lineStyle: { color: C.text, width: 1, type: "solid" }, label: { show: false } }] : []),
          ],
        },
      }],
    };
  }, [tl, metric, crit, w, lo, mid, hi, selectedDay]);

  return (
    <div className="metric-card">
      <div className="metric-head">
        <span className="metric-name" title={metric}>{cfg.metric_labels[metric] ?? metric}</span>
        <span className="metric-meta">w {w}{invert ? " · inverted" : ""} · <code>{metric}</code></span>
      </div>
      <Chart option={option} height={150} ariaLabel={`Daily values of ${metric}`}
        onClick={(p) => tl.days[p.dataIndex] && onSelectDay(tl.days[p.dataIndex].date)} />
    </div>
  );
}
