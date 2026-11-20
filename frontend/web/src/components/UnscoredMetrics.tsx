import { useMemo, useState } from "react";
import type { Config, CritKey, Timeline } from "../api";
import { CRIT_KEYS } from "../api";
import { fmtDay, fmtNum } from "../lib/format";
import { axisName, BAND_LABELS, baselineMarkArea, mergeMarkAreas, usualBand } from "../lib/chart";
import { C } from "../theme";
import { Chart } from "./Chart";
import { Icon } from "./Icon";
import { metricUnit } from "./MetricTrends";
import { metricName, SITE_GROUP_OF, visitText } from "../lib/metrics";

type Props = { tl: Timeline; cfg: Config; selectedDay: string | null; onSelectDay: (d: string) => void; step: number;
  onAsk?: (question: string, focus: string) => void };

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
export function UnscoredMetrics({ tl, cfg, selectedDay, onSelectDay, step, onAsk }: Props) {
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
        <p className="sub">These criteria are measured every day but are not part of the model's scoring yet, so they have no daily
          score and never count as present. Shown as measured, for review.</p>
      </div>

      {flags.length > 0 && (
        <div className="flag-box" role="note" style={{ background: C.alertSoft, borderColor: C.alert }}>
          <span style={{ color: C.alert, marginRight: 6 }}><Icon name="alert" label="Alert" /></span>
          <b>{cfg.criterion_names.C9}: more than usual on {flags.length} day{flags.length === 1 ? "" : "s"}</b>{" "}
          (not part of the scoring, shown as a warning): {flags.map((f, i) => {
            const day = tl.days.find((d) => d.date === f.date);
            const what = f.metrics.map((m) => {
              const g = SITE_GROUP_OF[m];
              const v = g ? day?.observed?.site_visits?.[g] : undefined;
              return v ? `${metricName(m, cfg).toLowerCase()} ${visitText(v)}` : metricName(m, cfg).toLowerCase();
            }).join("; ");
            return (
              <span key={f.date}>{i > 0 && "; "}<button className="link" onClick={() => onSelectDay(f.date)}>{fmtDay(f.date)}</button>
                {" "}({what})
                {onAsk && <button className="link small explain-link" onClick={() => onAsk(`What happened on ${f.date} with ${f.metrics.map((m) => metricName(m, cfg).toLowerCase()).join(" and ")}: how many visits, when, and how does it compare with this person's usual days? What else could explain it?`, `C9, day ${f.date}`)}>explain</button>}</span>
            );
          })}
        </div>
      )}

      <div className="seg" role="tablist">
        {crits.map((c) => (
          <button key={c} role="tab" aria-selected={c === active} className={c === active ? "active" : ""} onClick={() => setTab(c)}>
            <b>{c}</b> {cfg.criterion_names[c]}{c === "C9" && flags.length > 0 && <span className="flag-dot" style={{ background: C.alert }} aria-label="signal" />}
          </button>
        ))}
      </div>

      <div className="metric-grid">
        {varying.map((k) => <RawMetric key={k} tl={tl} metric={k} label={metricName(k, cfg)} selectedDay={selectedDay} onSelectDay={onSelectDay} />)}
      </div>
      {zero.length > 0 && (
        <p className="muted small">Always 0 or missing: {zero.map((k) => metricName(k, cfg)).join("; ")}</p>
      )}
      {varying.length > 0 && (
        <div className="small muted" style={{ display: "flex", flexWrap: "wrap", gap: "4px 14px" }}>
          <span className="key"><i style={{ display: "inline-block", width: 16, height: 0, borderTop: `2px solid ${C.ink}`, margin: "0 5px 3px 0", verticalAlign: "middle" }} />daily value</span>
          <span className="key"><i style={{ display: "inline-block", width: 16, height: 10, background: C.usualBand, borderRadius: 2, marginRight: 5, verticalAlign: -1 }} />{BAND_LABELS.usual} (baseline mean ± 1 SD)</span>
          {tl.days.some((d) => d.phase === "baseline") && <span className="key"><i style={{ display: "inline-block", width: 16, height: 10, background: C.baselineShade, borderRadius: 2, marginRight: 5, verticalAlign: -1 }} />{BAND_LABELS.baseline}</span>}
        </div>
      )}
    </section>
  );
}

function RawMetric({ tl, metric, label, selectedDay, onSelectDay }: { tl: Timeline; metric: string; label: string; selectedDay: string | null; onSelectDay: (d: string) => void }) {
  // site groups (crisis lines, therapy booking, …): visits per day instead of the packet count
  const group = SITE_GROUP_OF[metric];
  const asVisits = !!group && tl.days.some((d) => d.observed?.site_visits !== undefined);
  const option = useMemo(() => {
    const vals = asVisits
      ? tl.days.map((d) => (d.observed?.has_data ? d.observed.site_visits?.[group]?.visits ?? 0 : null))
      : tl.days.map((d) => num(d.metrics[metric]));
    const stats = asVisits ? undefined : tl.baseline_stats[metric];
    const unit = asVisits ? "visits" : metricUnit(metric);
    const sel = tl.days.findIndex((d) => d.date === selectedDay);
    return {
      animation: false,
      grid: { left: 60, right: 10, top: 22, bottom: 24 },
      tooltip: asVisits
        ? { trigger: "axis", formatter: (ps: { dataIndex: number }[]) => {
            const d = tl.days[ps[0]?.dataIndex];
            return d ? `<b>${d.weekday} ${fmtDay(d.date)}</b><br/>${visitText(d.observed?.site_visits?.[group])}` : "";
          } }
        : { trigger: "axis", valueFormatter: (v: number) => `${fmtNum(v)}${unit === "value" ? "" : ` ${unit}`}` },
      xAxis: { type: "category", data: tl.days.map((d) => fmtDay(d.date)), axisLabel: { color: C.text2, fontSize: 9 }, axisTick: { show: false }, axisLine: { lineStyle: { color: C.grid } } },
      yAxis: { type: "value", scale: true, ...axisName(unit, undefined, 44), axisLabel: { color: C.text2, fontSize: 9, formatter: (v: number) => fmtNum(v, 1) }, splitLine: { lineStyle: { color: C.grid } } },
      series: [{
        type: "line", data: vals, connectNulls: false, symbolSize: 5,
        lineStyle: { width: 1.5, color: C.ink }, itemStyle: { color: C.ink },
        markArea: mergeMarkAreas(baselineMarkArea(tl.days, { label: false }), usualBand(stats)),
        markLine: sel >= 0 ? { silent: true, symbol: "none", label: { show: false }, lineStyle: { color: C.text, width: 1, type: "solid" }, data: [{ xAxis: sel }] } : undefined,
      }],
    };
  }, [tl, metric, selectedDay, asVisits, group]);
  return (
    <div className="metric-card">
      <div className="metric-head">
        <span className="metric-name">{label}</span>
        {asVisits && <span className="metric-meta">visits per day</span>}
      </div>
      <Chart option={option} height={130} ariaLabel={`Daily values: ${label}`}
        onClick={(p) => tl.days[p.dataIndex] && onSelectDay(tl.days[p.dataIndex].date)} />
    </div>
  );
}
