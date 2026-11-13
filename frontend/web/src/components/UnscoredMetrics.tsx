import { useMemo, useState } from "react";
import type { Config, CritKey, Timeline } from "../api";
import { CRIT_KEYS } from "../api";
import { fmtDay, fmtNum } from "../lib/format";
import { C } from "../theme";
import { Chart } from "./Chart";

type Props = { tl: Timeline; cfg: Config; selectedDay: string | null; onSelectDay: (d: string) => void; step: number };

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

/** A C9 value counts as a signal when it is above the person's baseline: above mean + 2 SD, or above
 * zero for a metric that was always 0 in the baseline. Some C9 metrics are non-zero every day (e.g.
 * forum traffic), so "above zero" alone would flag every day. */
// Not used for the flag: without URLs in the gateway data, this metric counts all reddit.com packets.
const NOT_A_C9_SIGNAL = new Set(["C9_F4_SelfHarmForumVisits"]);

export function c9Signal(tl: Timeline, key: string, v: unknown): boolean {
  if (NOT_A_C9_SIGNAL.has(key)) return false;
  const x = num(v);
  if (x === null || x <= 0) return false;
  const s = tl.baseline_stats[key];
  if (!s) return true;                     // no baseline values: any activity is notable
  return x > s.mean + 2 * s.sd;
}

/** Days with a C9 (suicidality) signal: a flag outside the gate. */
export function c9Days(tl: Timeline): { date: string; metrics: string[] }[] {
  return tl.days
    .map((d) => ({ date: d.date, metrics: Object.entries(d.metrics).filter(([k, v]) => k.startsWith("C9_") && c9Signal(tl, k, v)).map(([k]) => k) }))
    .filter((x) => x.metrics.length > 0);
}

/** Metrics the thesis code computes for criteria the configuration does not score (no likelihood). */
export function UnscoredMetrics({ tl, cfg, selectedDay, onSelectDay, step }: Props) {
  const unscored = CRIT_KEYS.filter((c) => Object.keys(cfg.criteria[c] ?? {}).length === 0);
  const byCrit = useMemo(() => {
    const out: Partial<Record<CritKey, string[]>> = {};
    const keys = new Set(tl.days.flatMap((d) => Object.keys(d.metrics)));
    for (const k of keys) {
      const c = cfg.metric_criterion[k] ?? (k.match(/^(C\d)_/)?.[1] as CritKey | undefined);
      if (c && unscored.includes(c)) (out[c] ??= []).push(k);
    }
    for (const c of Object.keys(out) as CritKey[]) out[c]!.sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
    return out;
  }, [tl, cfg]); // eslint-disable-line react-hooks/exhaustive-deps
  const flags = useMemo(() => c9Days(tl), [tl]);
  const crits = unscored.filter((c) => byCrit[c]?.length);
  const [tab, setTab] = useState<CritKey | null>(null);
  const active = tab && crits.includes(tab) ? tab : (flags.length && crits.includes("C9") ? "C9" : crits[0]);
  if (!crits.length) return null;

  const metrics = byCrit[active] ?? [];
  const varying = metrics.filter((k) => tl.days.some((d) => (num(d.metrics[k]) ?? 0) !== 0));
  const zero = metrics.filter((k) => !varying.includes(k));

  return (
    <section className="card">
      <div className="card-head">
        <h2><span className="step">{step}</span>Other criteria (not scored)</h2>
        <p className="sub">The thesis code computes these metrics every day, but <code>fasl_config.json</code> gives them no weights,
          so they have no likelihood and do not count for the gate. Shown as raw values for review.</p>
      </div>

      {flags.length > 0 && (
        <div className="flag-box" role="note">
          <b>C9 {cfg.criterion_names.C9}: signal on {flags.length} day{flags.length === 1 ? "" : "s"}</b>{" "}
          (above the baseline, outside the gate): {flags.map((f, i) => (
            <span key={f.date}>{i > 0 && ", "}<button className="link" onClick={() => onSelectDay(f.date)}>{fmtDay(f.date)}</button>
              {" "}({f.metrics.map((m) => cfg.metric_labels[m] ?? m).join(", ")})</span>
          ))}
        </div>
      )}

      <div className="seg" role="tablist">
        {crits.map((c) => (
          <button key={c} role="tab" aria-selected={c === active} className={c === active ? "active" : ""} onClick={() => setTab(c)}>
            <b>{c}</b> {cfg.criterion_names[c]}{c === "C9" && flags.length > 0 && <span className="flag-dot" aria-label="signal" />}
          </button>
        ))}
      </div>

      <div className="metric-grid">
        {varying.map((k) => <RawMetric key={k} tl={tl} metric={k} label={cfg.metric_labels[k] ?? k} selectedDay={selectedDay} onSelectDay={onSelectDay} />)}
      </div>
      {zero.length > 0 && (
        <p className="muted small">Always 0 or missing: {zero.map((k) => cfg.metric_labels[k] ?? k).join(" · ")}</p>
      )}
    </section>
  );
}

function RawMetric({ tl, metric, label, selectedDay, onSelectDay }: { tl: Timeline; metric: string; label: string; selectedDay: string | null; onSelectDay: (d: string) => void }) {
  const option = useMemo(() => {
    const vals = tl.days.map((d) => num(d.metrics[metric]));
    const stats = tl.baseline_stats[metric];
    const cur = tl.days.map((d, i) => (d.phase === "current" ? i : -1)).filter((i) => i >= 0);
    const sel = tl.days.findIndex((d) => d.date === selectedDay);
    return {
      animation: false,
      grid: { left: 48, right: 10, top: 12, bottom: 24 },
      tooltip: { trigger: "axis", valueFormatter: (v: number) => fmtNum(v) },
      xAxis: { type: "category", data: tl.days.map((d) => fmtDay(d.date)), axisLabel: { color: C.text2, fontSize: 9 }, axisTick: { show: false }, axisLine: { lineStyle: { color: C.grid } } },
      yAxis: { type: "value", scale: true, axisLabel: { color: C.text2, fontSize: 9, formatter: (v: number) => fmtNum(v, 1) }, splitLine: { lineStyle: { color: C.grid } } },
      series: [{
        type: "line", data: vals, connectNulls: false, symbolSize: 5,
        lineStyle: { width: 1.5, color: C.ink }, itemStyle: { color: C.ink },
        markArea: {
          silent: true,
          data: [
            ...(stats ? [[{ yAxis: stats.mean - stats.sd, itemStyle: { color: C.baselineBand } }, { yAxis: stats.mean + stats.sd }]] : []),
            ...(cur.length ? [[{ xAxis: cur[0], itemStyle: { color: C.clinicalTint } }, { xAxis: cur[cur.length - 1] }]] : []),
          ],
        },
        markLine: sel >= 0 ? { silent: true, symbol: "none", label: { show: false }, lineStyle: { color: C.text, width: 1, type: "solid" }, data: [{ xAxis: sel }] } : undefined,
      }],
    };
  }, [tl, metric, selectedDay]);
  return (
    <div className="metric-card">
      <div className="metric-head">
        <span className="metric-name" title={metric}>{label}</span>
        <span className="metric-meta"><code>{metric}</code></span>
      </div>
      <Chart option={option} height={130} ariaLabel={`Daily values of ${metric}`}
        onClick={(p) => tl.days[p.dataIndex] && onSelectDay(tl.days[p.dataIndex].date)} />
    </div>
  );
}
