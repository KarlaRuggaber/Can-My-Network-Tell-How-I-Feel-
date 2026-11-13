import { useMemo } from "react";
import type { Config, CritKey, Timeline } from "../api";
import { CRIT_KEYS } from "../api";
import { fmtDay } from "../lib/format";
import { C } from "../theme";
import { Chart } from "./Chart";
import { c9Signal } from "./UnscoredMetrics";

type Cell = { x: number; y: number; fill: string; text: string; textFill: string; above?: boolean; present?: boolean };

const seqIndex = (L: number) => Math.max(0, Math.min(C.seq.length - 1, Math.round(L * (C.seq.length - 1))));
const seqColor = (L: number) => C.seq[seqIndex(L)];

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
        fill: ph === "current" ? C.clinical : ph === "baseline" ? C.baseline : "#f6f3ef",
        text: ph === "current" ? curShort : ph === "baseline" ? "base" : "", textFill: ph === "current" ? "#fff" : C.ink,
      });
      crits.forEach((c) => {
        const L = d.L[c];
        cells.push({
          x: i, y: rowOf(c), fill: L == null ? "#f6f3ef" : seqColor(L),
          text: L == null ? "" : L.toFixed(2).replace(/^0/, ""),
          textFill: L != null && seqIndex(L) >= C.seqWhiteFrom ? "#fff" : C.text,
          above: L != null && L >= theta, present: !!present[c]?.[i],
        });
      });
      if (showC9) cells.push({
        x: i, y: rowOf("C9 signal"), fill: c9Flags[i].length ? C.critical : "#f6f3ef",
        text: c9Flags[i].length ? "!" : "", textFill: "#fff",
      });
      cells.push({
        x: i, y: rowOf("Criteria present"), fill: nPresent[i] > 0 ? "#f6ece2" : "#f6f3ef",
        text: String(nPresent[i]), textFill: C.text,
      });
      if (canEpisode) cells.push({
        x: i, y: rowOf("Episode"), fill: episode[i] ? C.critical : "#f6f3ef",
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
            { type: "rect", shape: { x: cx - w / 2 + 1.5, y: cy - h / 2 + 1.5, width: w - 3, height: h - 3, r: 6 },
              style: { fill: cell.fill, stroke: sel ? C.text : null, lineWidth: sel ? 1.5 : 0 } },
            { type: "text", style: { text: cell.text, x: cx, y: cy, align: "center", verticalAlign: "middle", fill: cell.textFill, fontSize: 9 } },
          ];
          if (cell.above) children.push({ type: "circle", shape: { cx: cx + w / 2 - 6, cy: cy - h / 2 + 6, r: 2.5 }, style: { fill: C.ink, stroke: "#fff", lineWidth: 1 } });
          if (cell.present) children.push({ type: "rect", shape: { x: cx - w / 2 + 6, y: cy + h / 2 - 6, width: w - 12, height: 2.5, r: 1.25 }, style: { fill: C.ink } });
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
          Each cell is a day's likelihood L (darker = stronger signal).{" "}
          <span className="key"><i className="dot" style={{ background: C.ink }} /> reaches θ</span>{" "}
          <span className="key"><i className="bar" style={{ background: C.ink }} /> present{rolling
            ? <> (rolling {M}-day window, mixes phases)</> : <> in this phase</>}</span>.
          Click a day to open it below.
          {!canEpisode && <> No episode row: the configuration scores {crits.length} criteria, and an episode needs 5 present.</>}
          {c9 > 0 && <> <span className="key"><i className="dot" style={{ background: C.critical }} /> C9 signal (outside the gate)</span>.</>}
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
