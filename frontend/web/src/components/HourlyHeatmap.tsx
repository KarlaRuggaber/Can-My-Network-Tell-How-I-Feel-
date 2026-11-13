import { useMemo } from "react";
import type { Timeline } from "../api";
import { fmtDay, fmtNum } from "../lib/format";
import { C } from "../theme";
import { Chart } from "./Chart";

type Props = { tl: Timeline; selectedDay: string | null; onSelectDay: (d: string) => void; step: number };

/** Day × hour grid of packets: late nights, early waking and quiet days at a glance. */
export function HourlyHeatmap({ tl, selectedDay, onSelectDay, step }: Props) {
  const days = tl.days.filter((d) => d.hourly);
  const labels = tl.profile.phase_labels;

  const option = useMemo(() => {
    // Log scale between the 10th and 98th percentile of all hours: background traffic runs in most
    // hours, so a 0-to-max scale would colour nearly everything dark.
    const logs = days.flatMap((d) => d.hourly as number[]).filter((v) => v > 0).map(Math.log1p).sort((a, b) => a - b);
    const q = (p: number) => logs.length ? logs[Math.min(logs.length - 1, Math.floor(p * (logs.length - 1)))] : 0;
    const lo = q(0.10), hi = Math.max(q(0.98), lo + 1e-6);
    const level = (v: number) => Math.min(1, Math.max(0, (Math.log1p(v) - lo) / (hi - lo)));
    const color = (v: number) => (v <= 0 ? "#f6f3ef" : C.seq[Math.round(level(v) * (C.seq.length - 1))]);
    const sel = days.findIndex((d) => d.date === selectedDay);
    const data = days.flatMap((d, y) => (d.hourly as number[]).map((v, h) => [h, y, v]));
    return {
      animation: false,
      grid: { left: 96, right: 12, top: 8, bottom: 28 },
      tooltip: {
        formatter: (p: { data: number[] }) => {
          const [h, y, v] = p.data;
          const d = days[y];
          const ph = d.phase === "current" ? labels.current : d.phase === "baseline" ? labels.baseline : d.phase;
          return `<b>${d.weekday} ${d.date}</b> · ${ph.toLowerCase()}<br/>${String(h).padStart(2, "0")}:00–${String(h + 1).padStart(2, "0")}:00: ${fmtNum(v)} packets`;
        },
      },
      xAxis: {
        type: "category", data: Array.from({ length: 24 }, (_, h) => String(h).padStart(2, "0")),
        axisLabel: { color: C.text2, fontSize: 10 }, axisTick: { show: false }, axisLine: { show: false },
      },
      yAxis: {
        type: "category", inverse: true,
        data: days.map((d) => `${d.phase === "current" ? "● " : ""}${d.weekday.slice(0, 2)} ${fmtDay(d.date)}`),
        axisLabel: { color: C.text2, fontSize: 10 }, axisTick: { show: false }, axisLine: { show: false },
      },
      series: [{
        type: "custom", data, encode: { x: 0, y: 1, tooltip: [2] },
        renderItem: (_: unknown, api: { value: (i: number) => number; coord: (v: number[]) => number[]; size: (v: number[]) => number[] }) => {
          const [cx, cy] = api.coord([api.value(0), api.value(1)]);
          const [w, h] = api.size([1, 1]);
          const isSel = api.value(1) === sel;
          return {
            type: "rect",
            shape: { x: cx - w / 2 + 1, y: cy - h / 2 + 1, width: w - 2, height: h - 2, r: 3 },
            style: { fill: color(api.value(2)), stroke: isSel ? C.text : null, lineWidth: isSel ? 1 : 0 },
          };
        },
      }],
    };
  }, [tl, selectedDay]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!days.length) return null;
  return (
    <section className="card">
      <div className="card-head">
        <h2><span className="step">{step}</span>When the devices were online</h2>
        <p className="sub">Packets per hour and day (darker = more, log scale, relative to this person's own hours; ● = {labels.current.toLowerCase()} period).
          Late nights, early waking and quiet days show up as patterns. Click a day to open it below.</p>
      </div>
      <Chart option={option} height={46 + days.length * 20} ariaLabel="Packets per hour of each day"
        onClick={(p) => { const y = (p.data as number[])[1]; if (days[y]) onSelectDay(days[y].date); }} />
    </section>
  );
}
