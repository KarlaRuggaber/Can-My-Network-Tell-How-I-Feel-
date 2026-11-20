import type { Config, CritKey, Expectation, PhaseKey, Timeline } from "../api";
import { CRIT_KEYS } from "../api";
import { fmtDay } from "../lib/format";
import type { GateParams, PhaseGate } from "../lib/gate";
import { C } from "../theme";

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
  elevated: "raised, below the rule",
  borderline: "borderline",
  flag: "flag only",
};

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

const presentList = (p: PhaseView, crits: CritKey[]) => crits.filter((c) => p.criteria[c]?.present);

/** With fewer scored criteria than an episode needs (or no core criterion), no episode can be likely. */
export function episodePossible(cfg: Config, gate: GateParams): boolean {
  const scored = CRIT_KEYS.filter((c) => Object.keys(cfg.criteria[c] ?? {}).length > 0);
  return scored.length >= gate.minPresent && scored.some((c) => gate.core.includes(c));
}

function PhaseTile({ ph, title, p, crits, cfg, gate }: { ph: PhaseKey; title: string; p: PhaseView; crits: CritKey[]; cfg: Config; gate: GateParams }) {
  const on = presentList(p, crits);
  const prelim = isPreliminary(p, gate);
  return (
    <div className={`phase-tile${ph === "baseline" ? " phase-tile-baseline" : " phase-tile-plain"}`}
      style={ph === "baseline" ? undefined : { background: C.surface }}>
      <div className="phase-tile-head">
        <span className="phase-tile-title">{title}</span>
        <span className="muted small">{phaseSpan(p)}</span>
        {ph === "current" && prelim && <span className="pill pill-neutral">preliminary, day {p.days} of {gate.M}</span>}
      </div>
      {p.days === 0 ? <p className="muted">No complete days yet.</p> : (
        <>
          <div className="phase-tile-big">
            <b>{on.length}</b> <span>of {crits.length} criteria present</span>
          </div>
          <div className="chips">
            {on.length === 0 && <span className="muted small">none</span>}
            {on.map((c) => <span key={c} className="pill pill-alert">{c} {cfg.criterion_names[c]}</span>)}
          </div>
          <div className="small">
            Episode: {!episodePossible(cfg, gate)
              ? <span className="muted" title={`Only ${crits.length} of 9 criteria are scored; an episode needs ${gate.minPresent} present criteria.`}>not possible with this configuration</span>
              : p.episode ? <b style={{ color: C.alert }}>likely</b> : <span>no</span>}
          </div>
        </>
      )}
    </div>
  );
}

export function CriteriaSummary({ tl, cfg, phases, gate, selected, onSelect }: Props) {
  const clin = phases.current;
  const prelim = isPreliminary(clin, gate);
  const order: PhaseKey[] = ["baseline", "current"];
  const title = tl.profile.phase_labels;
  const hasExpect = Object.keys(tl.persona.expected ?? {}).length > 0;
  const scored = CRIT_KEYS.filter((c) => Object.keys(cfg.criteria[c] ?? {}).length > 0);
  const unscored = CRIT_KEYS.filter((c) => !scored.includes(c));

  const expectedPresent = scored.filter((c) => tl.persona.expected[c]?.present === "present");
  const judged = scored.filter((c) => agreement(tl.persona.expected[c]?.present, clin.days > 0 ? !!clin.criteria[c]?.present : null) !== "open");
  const matched = judged.filter((c) => agreement(tl.persona.expected[c]?.present, !!clin.criteria[c]?.present) === "match");

  return (
    <section className="card">
      <div className="card-head">
        <h2><span className="step">1</span>DSM-5 criteria</h2>
        <p className="sub">
          Which DSM-5 criteria count as present in each period. Each period is judged on its own days only.
        </p>
      </div>

      <div className="phase-tiles">
        {order.map((ph) => <PhaseTile key={ph} ph={ph} title={title[ph]} p={phases[ph]} crits={scored} cfg={cfg} gate={gate} />)}
        {hasExpect && <div className="phase-tile phase-tile-verdict">
          <div className="phase-tile-head"><span className="phase-tile-title">Expected (test script)</span></div>
          <div className="phase-tile-big">
            <b>{matched.length}</b> <span>of {judged.length} expectations met{prelim ? " so far" : ""}</span>
          </div>
          <div className="small">
            Should be present in the {title.current.toLowerCase()} phase: {expectedPresent.length
              ? expectedPresent.map((c) => <span key={c} className="pill pill-outline">{c}</span>)
              : <span className="muted">none</span>}
          </div>
          <div className="small muted">Episode expected: {tl.persona.episode?.expected ?? "–"}</div>
          {(tl.persona.condition || tl.persona.summary) && (
            <details className="howto script">
              <summary>About the script</summary>
              <p><b>{tl.persona.condition}</b>{tl.persona.baseline_profile && <> (everyday profile: {tl.persona.baseline_profile})</>}.
                {tl.persona.summary && <> {tl.persona.summary}</>}</p>
            </details>
          )}
        </div>}
      </div>

      <div className="table-wrap">
        <table className="crit-table">
          <thead>
            <tr>
              <th>Criterion</th>
              {hasExpect && <th>Expected</th>}
              {order.map((ph) => (
                <th key={ph}>{title[ph]} <span className="muted">, days with score ≥ {gate.theta.toFixed(2)}</span></th>
              ))}
              {hasExpect && <th>Match</th>}
            </tr>
          </thead>
          <tbody>
            {scored.map((c) => {
              const exp = tl.persona.expected[c];
              const obs = clin.days > 0 ? clin.criteria[c]?.present ?? null : null;
              const agr = agreement(exp?.present, obs);
              return (
                <tr key={c} className={`clickable ${selected === c ? "selected" : ""}`} onClick={() => onSelect(c)}
                  title="Show the metrics behind this criterion">
                  <td>
                    <b>{c}</b> {cfg.criterion_names[c]}
                    {cfg.core.includes(c) && <span className="pill pill-outline">core</span>}
                    {cfg.observability?.[c] && <span className={`obs obs-${cfg.observability[c].level}`} title={`Network sees: ${cfg.observability[c].observes}`}>{cfg.observability[c].level === "none" ? "barely" : cfg.observability[c].level} observable</span>}
                    {tl.care?.clinical?.criteria.includes(c) && <span className="tag">focus</span>}
                  </td>
                  {hasExpect && <td title={exp?.note}>{exp ? EXPECT_LABEL[exp.present] : "–"}</td>}
                  {order.map((ph) => {
                    const p = phases[ph];
                    const r = p.criteria[c];
                    if (!r || p.days === 0) return <td key={ph} className="muted">–</td>;
                    return (
                      <td key={ph}>
                        {r.present ? <span className="pill pill-alert">present</span> : <span className="pill pill-grey">absent</span>}
                        <span className="days-count">{r.daysOver} of {p.days}</span>
                      </td>
                    );
                  })}
                  {hasExpect && <td>
                    {agr === "match" && <span className="agree">✓ yes</span>}
                    {agr === "miss" && <span className="disagree">✗ no</span>}
                    {agr === "open" && <span className="muted">–</span>}
                  </td>}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {unscored.length > 0 && (
        <p className="small muted unscored">
          Not scored by the current configuration: {unscored.map((c) => `${c} ${cfg.criterion_names[c]}`
            + (hasExpect && tl.persona.expected[c] ? ` (expected ${EXPECT_LABEL[tl.persona.expected[c]!.present]})` : "")).join("; ")}.
        </p>
      )}

      <details className="howto">
        <summary>How is this decided?</summary>
        <p>
          Every day, each criterion gets a score between 0 and 1 from the network measures behind it (how far they are from the
          person's usual range). A criterion counts as <b>present</b> in a period when its score is at least {gate.theta.toFixed(2)} on
          {" "}{gate.N} or more of that period's last {gate.M} days, so a single unusual day never decides it. Like the DSM-5, an
          <b> episode</b> needs at least {gate.minPresent} present criteria, one of them a core criterion
          ({cfg.core.join(", ")}).{!episodePossible(cfg, gate) && <> The model scores only {scored.length} criteria so far, so an
          episode cannot be reached; it is shown for completeness.</>} {tl.profile.has_plan
            ? <>The {title.baseline.toLowerCase()} and {title.current.toLowerCase()} phase come from the scripted plan; the warm-up day is not counted.</>
            : <>The baseline is the person's usual behaviour ({phaseSpan(phases.baseline) || "first 14 days"}, set under People and devices); every later day is “{title.current.toLowerCase()}”.</>}
          {" "}Today (still being recorded
          {clin.inProgress.length > 0 && `, ${clin.inProgress.map(fmtDay).join(", ")}`}) are not counted.
          {prelim && clin.days > 0 && <> The {title.current.toLowerCase()} period has {clin.days} of {gate.M} days so far, so its result can still change.</>}
          {hasExpect && <> Expectations come from the script of this test person; "raised, below the rule" means the criterion should rise but not count as present.</>}
          Click a criterion to see the metrics behind it.
        </p>
      </details>
    </section>
  );
}
