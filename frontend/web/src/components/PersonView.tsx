import { useMemo } from "react";
import type { Config, CritKey, Timeline } from "../api";
import { fmtDay, fmtNum } from "../lib/format";
import type { GateParams } from "../lib/gate";
import { AREA_NAMES, C } from "../theme";
import { Chart } from "./Chart";
import type { PhaseView } from "./CriteriaSummary";

type Props = { tl: Timeline; cfg: Config; recent: PhaseView; gate: GateParams };

export type AreaStatus = "usual" | "some" | "different" | "unknown";

/** Everyday status of an area in the recent period: no numbers, no clinical terms. */
export function areaStatus(p: PhaseView, c: string): AreaStatus {
  const r = p.criteria[c];
  if (!r || p.days === 0) return "unknown";
  if (r.present) return "different";
  return r.daysOver > 0 ? "some" : "usual";
}

const STATUS_TEXT: Record<AreaStatus, string> = {
  usual: "As usual",
  some: "A few different days",
  different: "Noticeably different",
  unknown: "Not enough days yet",
};

/** The person's own view: how their recent weeks compare with their usual weeks, in plain words. */
export function PersonView({ tl, cfg, recent, gate }: Props) {
  const areas = (Object.keys(cfg.criteria) as CritKey[]).filter((c) => Object.keys(cfg.criteria[c] ?? {}).length > 0);
  const recentDays = tl.days.filter((d) => recent.counted.includes(d.date));

  const trafficOption = useMemo(() => ({
    animation: false,
    grid: { left: 48, right: 8, top: 10, bottom: 28 },
    tooltip: { trigger: "axis", valueFormatter: (v: number) => `${fmtNum(v)} packets` },
    xAxis: { type: "category", data: tl.days.map((d) => fmtDay(d.date)), axisLabel: { color: C.text2, fontSize: 10 }, axisTick: { show: false }, axisLine: { lineStyle: { color: C.grid } } },
    yAxis: { type: "value", axisLabel: { color: C.text2, fontSize: 10, formatter: (v: number) => fmtNum(v, 0) }, splitLine: { lineStyle: { color: C.grid } } },
    series: [{
      type: "bar", barMaxWidth: 18,
      data: tl.days.map((d) => ({ value: d.packets_kept, itemStyle: { color: d.phase === "current" ? C.ink : C.baseline, borderRadius: [4, 4, 0, 0] } })),
    }],
  }), [tl]);

  return (
    <>
      <section className="card person-intro">
        <h2>Hello {tl.persona.name}</h2>
        <p>
          This page compares how your devices were used in the <b>recent days</b> with your <b>usual weeks</b>.
          It looks only at when and how much your devices were online, never at what you read or wrote.
          It is a research prototype, not a diagnosis.
        </p>
        {recent.days > 0 && recent.days < gate.M && (
          <p className="muted small">So far {recent.days} recent day{recent.days === 1 ? "" : "s"}; the picture becomes clearer after {gate.M} days.</p>
        )}
      </section>

      <section className="card">
        <div className="card-head"><h2>Recent days compared with your usual weeks</h2></div>
        <div className="area-grid">
          {areas.map((c) => {
            const st = areaStatus(recent, c);
            const L = recentDays.map((d) => d.L[c]);
            return (
              <div key={c} className={`area-card area-${st}`}>
                <div className="area-name">{AREA_NAMES[c] ?? c}</div>
                <div className="area-status">{STATUS_TEXT[st]}</div>
                <div className="area-dots" aria-label={`${AREA_NAMES[c]}: ${STATUS_TEXT[st]}`}>
                  {recentDays.map((d, i) => (
                    <span key={d.date} className={`dot ${L[i] != null && (L[i] as number) >= gate.theta ? "dot-on" : ""}`}
                      title={`${d.weekday} ${fmtDay(d.date)}: ${L[i] != null && (L[i] as number) >= gate.theta ? "different from usual" : "usual"}`} />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
        <p className="muted small">Each dot is one recent day; a filled dot means that day looked different from your usual weeks in this area.
          Single different days are normal — travel, guests or a busy week can cause them.</p>
      </section>

      <section className="card">
        <div className="card-head">
          <h2>How much your devices were online</h2>
          <p className="sub">Network activity per day; recent days in dark, your usual weeks in beige.</p>
        </div>
        <Chart option={trafficOption} height={180} ariaLabel="Network activity per day" />
      </section>

      <section className="card care">
        <p>If you are worried about how you feel, talk to someone you trust or to your doctor.
          In an emergency in Switzerland call <b>144</b>, or <b>143</b> (Die Dargebotene Hand) to talk to someone.</p>
      </section>
    </>
  );
}
