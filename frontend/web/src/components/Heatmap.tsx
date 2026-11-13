import { useMemo } from "react";
import type { Config, CritKey, Timeline } from "../api";
import { CRIT_KEYS } from "../api";
import { fmtDay } from "../lib/format";
import { C } from "../theme";
import { Chart } from "./Chart";

type Cell = { x: number; y: number; fill: string; text: string; textFill: string; above?: boolean; present?: boolean };

function seqColor(L: number): string {
  const i = Math.max(0, Math.min(C.seq.length - 1, Math.round(L * (C.seq.length - 1))));
  return C.seq[i];
}

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
};

/** Day × criterion grid of daily likelihoods L, with the phase strip and gate state. */
export function Heatmap({ tl, cfg, present, episode, theta, rolling, M, selectedDay, onSelectDay }: Props) {
  const gateWord = rolling ? `rolling ${M}-day window, mixes phases` : "gate of this day's phase";
  const crits = CRIT_KEYS.filter((c) => Object.keys(cfg.criteria[c] ?? {}).length > 0);
  const days = tl.days;
  const xs = days.map((d) => `${fmtDay(d.date)}\n${d.weekday.slice(0, 2)}`);
  // rows top to bottom: phase, criteria, gate count, episode
  const rows = ["Episode", "Criteria present", ...[...crits].reverse(), "Phase"];
  const rowOf = (name: string) => rows.indexOf(name);

  const option = useMemo(() => {
    const nPresent = days.map((_, i) => crits.filter((c) => present[c]?.[i]).length);
    const selIdx = days.findIndex((d) => d.date === selectedDay);
    const cells: Cell[] = [];
    days.forEach((d, i) => {
      const ph = d.phase;
      cells.push({
        x: i, y: rowOf("Phase"),
        fill: ph === "clinical" ? C.laptop : ph === "baseline" ? "#b9b8b2" : "#e6e5e1",
        text: ph === "clinical" ? "clin" : ph === "baseline" ? "base" : "", textFill: "#fff",
      });
      crits.forEach((c) => {
        const L = d.L[c];
        cells.push({
          x: i, y: rowOf(c), fill: L == null ? "#f2f1ee" : seqColor(L),
          text: L == null ? "" : L.toFixed(2).replace(/^0/, ""),
          textFill: L != null && L > 0.55 ? "#fff" : C.text,
          above: L != null && L >= theta, present: !!present[c]?.[i],
        });
      });
      cells.push({
        x: i, y: rowOf("Criteria present"), fill: nPresent[i] > 0 ? "#fbe4e4" : "#f2f1ee",
        text: String(nPresent[i]), textFill: C.text,
      });
      cells.push({
        x: i, y: rowOf("Episode"), fill: episode[i] ? C.critical : "#f2f1ee",
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
          const head = `<b>${d.date} (${d.weekday})</b> · ${d.phase}${d.complete ? "" : " · incomplete"}`;
          if (row === "Phase") return `${head}<br/>${d.ground_truth.n_blocks} scripted blocks, ${d.ground_truth.n_profile_blocks} clinical-profile`;
          if (row === "Criteria present") return `${head}<br/>${nPresent[i]} criteria present (${gateWord})`;
          if (row === "Episode") return `${head}<br/>episode ${episode[i] ? "likely" : "not likely"} (${gateWord})`;
          const c = row as CritKey;
          const L = d.L[c];
          const lines = Object.entries(d.parts[c] ?? {})
            .sort((a, b) => b[1].w * b[1].mu - a[1].w * a[1].mu)
            .map(([k, m]) => `${cfg.metric_labels[k] ?? k}: μ ${m.mu.toFixed(2)} × w ${m.w}`);
          return `${head}<br/><b>${c}</b> L = ${L == null ? "–" : L.toFixed(2)}${present[c]?.[i] ? ` · <b>present</b> (${gateWord})` : ""}<br/><span style="color:${C.text2}">${lines.join("<br/>")}</span>`;
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
            { type: "rect", shape: { x: cx - w / 2 + 1, y: cy - h / 2 + 1, width: w - 2, height: h - 2, r: 3 },
              style: { fill: cell.fill, stroke: sel ? C.text : null, lineWidth: sel ? 1.5 : 0 } },
            { type: "text", style: { text: cell.text, x: cx, y: cy, align: "center", verticalAlign: "middle", fill: cell.textFill, fontSize: 9 } },
          ];
          if (cell.above) children.push({ type: "circle", shape: { cx: cx + w / 2 - 6, cy: cy - h / 2 + 6, r: 2.5 }, style: { fill: C.warning } });
          if (cell.present) children.push({ type: "rect", shape: { x: cx - w / 2 + 4, y: cy + h / 2 - 5, width: w - 8, height: 2.5 }, style: { fill: C.critical } });
          return { type: "group", children };
        },
      }],
    };
  }, [tl, cfg, present, episode, theta, rolling, M, selectedDay]); // eslint-disable-line react-hooks/exhaustive-deps

  const height = 60 + rows.length * 34;
  return (
    <section className="card">
      <div className="card-head">
        <h2>Daily criterion likelihoods</h2>
        <p className="sub">
          Cell = likelihood L<sub>k</sub> of the day (darker = higher).{" "}
          <span className="key"><i className="dot" style={{ background: C.warning }} /> L ≥ θ</span>{" "}
          <span className="key"><i className="bar" style={{ background: C.critical }} /> {rolling
            ? <>criterion present in a rolling window of the last {M} days <span className="tag tag-warn">mixes phases</span></>
            : <>criterion present in the day's phase (gate on that phase's days; marked on the counted days)</>}</span>.
          Click a day for its ground truth.
        </p>
      </div>
      <Chart option={option} height={height}
        ariaLabel="Heatmap of daily criterion likelihoods per day"
        onClick={(p) => {
          const i = (p.data as number[])[0];
          if (days[i]) onSelectDay(days[i].date);
        }} />
    </section>
  );
}
