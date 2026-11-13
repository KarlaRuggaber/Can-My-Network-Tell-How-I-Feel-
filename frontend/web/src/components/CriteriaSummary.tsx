import type { Config, CritKey, Expectation, PhaseKey, Timeline } from "../api";
import { CRIT_KEYS } from "../api";
import { fmtDay } from "../lib/format";
import type { GateParams, PhaseGate } from "../lib/gate";

/** Gate result of one phase plus what it was computed on. */
export interface PhaseView extends PhaseGate {
  counted: string[];              // dates in the window (last M complete days of the phase)
  inProgress: string[];           // today's day while it is still being ingested (not counted)
  plannedFirst: string | null;
  plannedLast: string | null;
  plannedDays: number;
}

type Props = {
  tl: Timeline;
  cfg: Config;
  phases: Record<PhaseKey, PhaseView>;
  gate: GateParams;
  selected: CritKey | null;
  onSelect: (c: CritKey) => void;
};

const EXPECT_LABEL: Record<Expectation, string> = {
  present: "present",
  no: "absent",
  elevated: "elevated, below gate",
  borderline: "borderline",
  flag: "flag (outside gate)",
};

const PHASE_TITLE: Record<PhaseKey, string> = { baseline: "Baseline", clinical: "Clinical" };

/** Does the observed gate state agree with the profile's expectation? */
export function agreement(expected: Expectation | undefined, observed: boolean | null): "match" | "miss" | "open" {
  if (expected === undefined || observed === null) return "open";
  if (expected === "borderline" || expected === "flag") return "open";
  return (expected === "present") === observed ? "match" : "miss";
}

export function phaseSpan(p: PhaseView): string {
  return p.plannedFirst && p.plannedLast ? `${fmtDay(p.plannedFirst)}–${fmtDay(p.plannedLast)}` : "";
}

/** Fewer days than the window M: the gate cannot reach its final state yet. */
export function isPreliminary(p: PhaseView, gate: GateParams): boolean {
  return p.days < gate.M;
}

export function CriteriaSummary({ tl, cfg, phases, gate, selected, onSelect }: Props) {
  const clin = phases.clinical;
  const prelim = isPreliminary(clin, gate);
  const order: PhaseKey[] = ["baseline", "clinical"];

  const gateCell = (v: boolean | undefined, p: PhaseView) =>
    v === undefined || p.days === 0 ? <span className="muted">–</span>
      : v ? <span className="status status-on">● present</span>
        : <span className="status status-off">○ absent</span>;

  return (
    <section className="card">
      <div className="card-head">
        <h2>DSM-5 criteria: baseline phase vs. clinical phase</h2>
        <p className="sub">
          The gate is evaluated on each phase's own days: a criterion is present when L ≥ θ = {gate.theta.toFixed(2)} on
          at least N = {gate.N} of the phase's last M = {gate.M} days. Warm-up and the day still being ingested
          {clin.inProgress.length > 0 && ` (${clin.inProgress.map(fmtDay).join(", ")})`} are not counted.
          Click a row for its metrics.
        </p>
        {prelim && clin.days > 0 && (
          <p className="prelim">
            <b>Preliminary:</b> the clinical phase has {clin.days} of {gate.M} days so far
            ({clin.plannedDays} planned, until {clin.plannedLast ? fmtDay(clin.plannedLast) : "–"}); a criterion needs
            L ≥ θ on {gate.N} of {gate.M}. "Clinical vs. expected" compares the current state.
          </p>
        )}
      </div>
      <div className="table-wrap">
        <table className="crit-table">
          <thead>
            <tr>
              <th rowSpan={2}>Criterion</th>
              <th rowSpan={2}>Expected (§9, clinical)</th>
              {order.map((ph) => (
                <th key={ph} colSpan={2} className="phase-head">
                  {PHASE_TITLE[ph]} {phaseSpan(phases[ph]) && <span className="muted">({phaseSpan(phases[ph])})</span>}
                  {ph === "clinical" && prelim && <span className="tag tag-warn">preliminary</span>}
                </th>
              ))}
              <th rowSpan={2}>Clinical vs. expected</th>
            </tr>
            <tr>
              {order.map((ph) => [
                <th key={`${ph}-n`} className="num">days L ≥ θ</th>,
                <th key={`${ph}-g`}>gate</th>,
              ])}
            </tr>
          </thead>
          <tbody>
            {CRIT_KEYS.map((c) => {
              const configured = Object.keys(cfg.criteria[c] ?? {}).length > 0;
              const exp = tl.persona.expected[c];
              const obs = clin.days > 0 ? clin.criteria[c]?.present ?? null : null;
              const agr = configured ? agreement(exp?.present, obs) : "open";
              return (
                <tr key={c}
                  className={`${configured ? "clickable" : "unconfigured"} ${selected === c ? "selected" : ""}`}
                  onClick={() => configured && onSelect(c)}>
                  <td>
                    <b>{c}</b> {cfg.criterion_names[c]}
                    {cfg.core.includes(c) && <span className="tag">core</span>}
                    {!configured && <span className="tag tag-muted">not configured</span>}
                  </td>
                  <td title={exp?.note}>
                    {exp ? EXPECT_LABEL[exp.present] : "–"}
                    {exp?.note && <div className="note">{exp.note}</div>}
                  </td>
                  {order.map((ph) => {
                    const p = phases[ph];
                    const r = p.criteria[c];
                    return [
                      <td key={`${ph}-n`} className="num">
                        {configured && r ? `${r.daysOver} of ${p.days}` : "–"}
                      </td>,
                      <td key={`${ph}-g`}>{configured ? gateCell(r?.present, p) : <span className="muted">–</span>}</td>,
                    ];
                  })}
                  <td>
                    {agr === "match" && <span className="agree">✓ as expected{prelim ? " so far" : ""}</span>}
                    {agr === "miss" && <span className="disagree">✗ differs{prelim ? " so far" : ""}</span>}
                    {agr === "open" && <span className="muted">{configured && exp ? "see note" : "–"}</span>}
                  </td>
                </tr>
              );
            })}
            <tr className="episode-row">
              <td><b>Episode</b> ≥ {gate.minPresent} present incl. core ({cfg.core.join(", ")})</td>
              <td title={tl.persona.episode?.note}>
                {tl.persona.episode?.expected ?? "–"}
                {tl.persona.episode?.note && <div className="note">{tl.persona.episode.note}</div>}
              </td>
              {order.map((ph) => {
                const p = phases[ph];
                return [
                  <td key={`${ph}-n`} className="num">{p.days > 0 ? `${p.totalPresent} present` : "–"}</td>,
                  <td key={`${ph}-g`}>
                    {p.days === 0 ? <span className="muted">–</span>
                      : p.episode ? <span className="status status-on">● likely</span>
                        : <span className="status status-off">○ no</span>}
                  </td>,
                ];
              })}
              <td />
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  );
}
