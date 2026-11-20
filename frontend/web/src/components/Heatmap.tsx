import { useMemo, useState } from "react";
import type { Config, CritKey, Timeline } from "../api";
import { CRIT_KEYS } from "../api";
import { fmtDay } from "../lib/format";
import { C } from "../theme";
import { Chart } from "./Chart";
import { Icon } from "./Icon";
import { c9Signal } from "./UnscoredMetrics";

type Cell = { x: number; y: number; fill: string; text: string; textFill: string; above?: boolean; present?: boolean };

/** Neutral intensity step of a likelihood (rule §2.3): lightness only, no red. */
export const intensityIndex = (L: number) => Math.max(0, Math.min(C.intensity.length - 1, Math.round(L * (C.intensity.length - 1))));
const intensityColor = (L: number) => C.intensity[intensityIndex(L)];
const EMPTY = "#f6f3ef";

type Props = {
  tl: Timeline;
  cfg: Config;
  present: Partial<Record<CritKey, boolean[]>>;
  episode: boolean[];
  theta: number;
  rolling: boolean;
  M: number;
  selectedDay: string | null;
  onSelectDay: (d: string) => void;
  onAsk?: (question: string, focus: string) => void;
};

/** Day × criterion grid of daily likelihoods L, with the phase strip and gate state. */
export function Heatmap({ tl, cfg, present, episode, theta, rolling, M, selectedDay, onSelectDay, onAsk }: Props) {
  const [pop, setPop] = useState<{ x: number; y: number; i: number; row: string } | null>(null);
  const gateWord = rolling ? `rolling ${M}-day window, mixes phases` : "gate of this day's period";
  const labels = tl.profile.phase_labels;
  const curShort = labels.current === "Clinical" ? "clin" : "recent";
  const phaseName = (ph: string) => (ph === "current" ? labels.current : ph === "baseline" ? labels.baseline : ph).toLowerCase();
  const crits = CRIT_KEYS.filter((c) => Object.keys(cfg.criteria[c] ?? {}).length > 0);
  const days = tl.days;
  const xs = days.map((d) => `${fmtDay(d.date)}\n${d.weekday.slice(0, 2)}`);
  // rows top to bottom: phase, criteria, gate count, episode
  // The episode row is shown only when the configuration can reach an episode (enough scored criteria).
  const canEpisode = crits.length >= 5 && crits.some((c) => cfg.core.includes(c));
  // C9 (suicidality) is not scored, but any C9 metric above zero is marked as a flag row.
  const c9Flags = days.map((d) => Object.entries(d.metrics).filter(([k, v]) => k.startsWith("C9_") && c9Signal(tl, k, v)).map(([k]) => k));
  const c9 = c9Flags.filter((x) => x.length).length;
  const showC9 = c9 > 0 && !crits.includes("C9");
  const rows = [...(canEpisode ? ["Episode"] : []), "Criteria present", ...(showC9 ? ["C9 signal"] : []), ...[...crits].reverse(), "Phase"];
  const rowOf = (name: string) => rows.indexOf(name);

  const option = useMemo(() => {
    const nPresent = days.map((_, i) => crits.filter((c) => present[c]?.[i]).length);
    const selIdx = days.findIndex((d) => d.date === selectedDay);
    const cells: Cell[] = [];
    days.forEach((d, i) => {
      const ph = d.phase;
      cells.push({
        x: i, y: rowOf("Phase"),
        // baseline neutral and shaded, the current period plain (rule §2.4)
        fill: ph === "baseline" ? C.baselineShade : C.surface,
        text: ph === "current" ? curShort : ph === "baseline" ? "base" : "", textFill: ph === "baseline" ? C.ink : C.text2,
      });
      crits.forEach((c) => {
        const L = d.L[c];
        cells.push({
          x: i, y: rowOf(c), fill: L == null ? EMPTY : intensityColor(L),
          text: L == null ? "" : L.toFixed(2).replace(/^0/, ""),
          textFill: L != null && intensityIndex(L) >= C.intensityWhiteFrom ? "#fff" : C.text,
          above: L != null && L >= theta, present: !!present[c]?.[i],
        });
      });
      if (showC9) cells.push({
        x: i, y: rowOf("C9 signal"), fill: c9Flags[i].length ? C.alert : EMPTY,
        text: c9Flags[i].length ? "!" : "", textFill: "#fff",
      });
      cells.push({
        x: i, y: rowOf("Criteria present"), fill: EMPTY,
        text: String(nPresent[i]), textFill: nPresent[i] > 0 ? C.text : C.muted,
      });
      if (canEpisode) cells.push({
        x: i, y: rowOf("Episode"), fill: episode[i] ? C.alert : EMPTY,
        text: episode[i] ? "yes" : "", textFill: "#fff",
      });
    });

    return {
      animation: false,
      grid: { left: 150, right: 16, top: 8, bottom: 44 },
      tooltip: {
        trigger: "item",
        formatter: (p: { data: number[] }) => {
          const i = p.data[0];
          const d = days[i];
          const row = rows[p.data[1]];
          const head = `<b>${d.date} (${d.weekday})</b> · ${phaseName(d.phase)}${d.complete ? "" : " · incomplete"}`;
          if (row === "Phase") return d.ground_truth ? `${head}<br/>${d.ground_truth.n_blocks} scripted blocks, ${d.ground_truth.n_profile_blocks} clinical` : head;
          if (row === "C9 signal") return `${head}<br/>${c9Flags[i].length ? `C9 above baseline: ${c9Flags[i].map((k) => cfg.metric_labels[k] ?? k).join(", ")}` : "no C9 signal"} (not scored, outside the gate)`;
          if (row === "Criteria present") return `${head}<br/>${nPresent[i]} criteria present (${gateWord})`;
          if (row === "Episode") return `${head}<br/>episode ${episode[i] ? "likely" : "not likely"} (${gateWord})`;
          const c = row as CritKey;
          const L = d.L[c];
          const lines = Object.entries(d.parts[c] ?? {})
            .filter(([, m]) => m.w * m.mu > 0)
            .sort((a, b) => b[1].w * b[1].mu - a[1].w * a[1].mu)
            .slice(0, 3)
            .map(([k]) => cfg.metric_labels[k] ?? k);
          return `${head}<br/><b>${c}</b> likelihood ${L == null ? "–" : L.toFixed(2)}${present[c]?.[i] ? ` · <b style="color:${C.alert}">present</b> (${gateWord})` : ""}` +
            `<br/><span style="color:${C.text2}">${lines.length ? `mainly: ${lines.join(", ")}` : "no metric counted on this day"}</span>`;
        },
      },
      xAxis: {
        type: "category", data: xs,
        axisLabel: { color: C.text2, fontSize: 10, interval: 0 }, axisTick: { show: false },
        axisLine: { show: false },
      },
      yAxis: {
        type: "category",
        data: rows.map((r) => (/^C\d$/.test(r) ? `${r} ${cfg.criterion_names[r as CritKey]}` : r)),
        axisLabel: { color: C.text, fontSize: 11, width: 140, overflow: "truncate" },
        axisTick: { show: false }, axisLine: { show: false },
      },
      series: [{
        type: "custom",
        data: cells.map((c, k) => [c.x, c.y, k]),
        encode: { x: 0, y: 1, tooltip: [] },
        renderItem: (_: unknown, api: { value: (i: number) => number; coord: (v: number[]) => number[]; size: (v: number[]) => number[] }) => {
          const cell = cells[api.value(2)];
          const [cx, cy] = api.coord([api.value(0), api.value(1)]);
          const [w, h] = api.size([1, 1]);
          const sel = cell.x === selIdx;
          const children: object[] = [
            { type: "rect", shape: { x: cx - w / 2 + 1.5, y: cy - h / 2 + 1.5, width: w - 3, height: h - 3, r: 6 },
              style: { fill: cell.fill, stroke: sel ? C.text : null, lineWidth: sel ? 1.5 : 0 } },
            { type: "text", style: { text: cell.text, x: cx, y: cy, align: "center", verticalAlign: "middle", fill: cell.textFill, fontSize: 9 } },
          ];
          if (cell.above) children.push({ type: "circle", shape: { cx: cx + w / 2 - 6, cy: cy - h / 2 + 6, r: 2.5 }, style: { fill: C.ink, stroke: "#fff", lineWidth: 1 } });
          if (cell.present) children.push({ type: "rect", shape: { x: cx - w / 2 + 6, y: cy + h / 2 - 6, width: w - 12, height: 2.5, r: 1.25 }, style: { fill: C.alert, stroke: "#fff", lineWidth: 0.5 } });
          return { type: "group", children };
        },
      }],
    };
  }, [tl, cfg, present, episode, theta, rolling, M, selectedDay]); // eslint-disable-line react-hooks/exhaustive-deps

  const height = 60 + rows.length * 34;
  return (
    <section className="card">
      <div className="card-head">
        <h2><span className="step">2</span>Day by day</h2>
        <p className="sub">
          Each cell is a day's likelihood L of a criterion (0–1). Click a day to open it below.
          {!canEpisode && <> No episode row: the configuration scores {crits.length} criteria, and an episode needs 5 present.</>}
        </p>
        <div className="small muted" style={{ display: "flex", flexWrap: "wrap", gap: "4px 14px", marginTop: 6 }}>
          <span className="key" title="Neutral scale: lighter = weaker, darker = stronger signal">
            likelihood 0 {C.intensity.map((c) => <i key={c} style={{ display: "inline-block", width: 10, height: 10, background: c }} />)} 1
          </span>
          <span className="key"><i className="dot" style={{ background: C.ink }} /> reaches θ</span>
          <span className="key"><i className="bar" style={{ background: C.alert }} /> present{rolling
            ? <> (rolling {M}-day window, mixes phases)</> : <> in this period</>}</span>
          <span className="key"><i style={{ display: "inline-block", width: 14, height: 10, background: C.baselineShade, marginRight: 4 }} /> Baseline (usual weeks)</span>
          {c9 > 0 && <span className="key" style={{ color: C.alert }}><Icon name="alert" label="C9 signal" /> C9 signal (outside the gate)</span>}
          {canEpisode && <span className="key"><i style={{ display: "inline-block", width: 14, height: 10, background: C.alert, marginRight: 4 }} /> episode likely</span>}
        </div>
      </div>
      <div className="pop-host">
        <Chart option={option} height={height}
          ariaLabel="Heatmap of daily criterion likelihoods per day"
          onClick={(p) => {
            const [i, y] = p.data as number[];
            if (!days[i]) return;
            onSelectDay(days[i].date);
            const ev = p.event as unknown as { offsetX: number; offsetY: number } | undefined;
            if (onAsk && ev) setPop({ x: ev.offsetX, y: ev.offsetY, i, row: rows[y] });
          }} />
        {pop && onAsk && days[pop.i] && (
          <ExplainPop x={pop.x} y={pop.y} onClose={() => setPop(null)}
            title={`${days[pop.i].weekday} ${days[pop.i].date} · ${pop.row}`}
            actions={[
              ...(/^C\d$/.test(pop.row) && days[pop.i].L[pop.row as CritKey] != null ? [{
                label: `Explain L = ${days[pop.i].L[pop.row as CritKey]!.toFixed(2)}`,
                run: () => onAsk(`Explain why ${pop.row} ${cfg.criterion_names[pop.row as CritKey]} has a likelihood of ${days[pop.i].L[pop.row as CritKey]!.toFixed(2)} on ${days[pop.i].date}: which metrics and values drove it, how they compare with the usual range, and how much this can be trusted from network data.`, `heatmap, ${pop.row}, day ${days[pop.i].date}`),
              }] : []),
              ...(pop.row === "C9 signal" ? [{
                label: "How do these hits come about?",
                run: () => onAsk(`How do the C9 signals on ${days[pop.i].date} come about? Which metric counted what (domain hits, not content), how does it compare with the baseline, and what else could cause it?`, `C9 signal, day ${days[pop.i].date}`),
              }] : []),
              ...(pop.row === "Criteria present" || pop.row === "Episode" ? [{
                label: "Explain the gate on this day",
                run: () => onAsk(`Explain the gate state on ${days[pop.i].date}: which criteria count as present, why, and why an episode is or is not likely.`, `heatmap, gate, day ${days[pop.i].date}`),
              }] : []),
            ]} />
        )}
      </div>
    </section>
  );
}

/** Small menu at the clicked cell: explain the value with the assistant. */
export function ExplainPop({ x, y, title, actions, onClose }: {
  x: number; y: number; title: string; actions: { label: string; run: () => void }[]; onClose: () => void;
}) {
  if (!actions.length) return null;
  return (
    <div className="explain-pop" style={{ left: Math.max(8, x - 40), top: y + 12 }} role="dialog" aria-label="Explain">
      <div className="explain-pop-head"><span>{title}</span><button className="link small" onClick={onClose} aria-label="Close">×</button></div>
      {actions.map((a) => (
        <button key={a.label} className="btn small explain-btn" onClick={() => { a.run(); onClose(); }}>✦ {a.label}</button>
      ))}
    </div>
  );
}
