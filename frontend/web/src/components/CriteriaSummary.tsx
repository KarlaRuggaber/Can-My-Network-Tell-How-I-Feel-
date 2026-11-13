import type { Config, CritKey, Expectation, Timeline } from "../api";
import { CRIT_KEYS } from "../api";
import { daysAbove } from "../lib/gate";

type Props = {
  tl: Timeline;
  cfg: Config;
  present: Partial<Record<CritKey, boolean[]>>;
  episode: boolean[];
  theta: number;
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

/** Does the observed gate state agree with the profile's expectation? */
export function agreement(expected: Expectation | undefined, observed: boolean | null): "match" | "miss" | "open" {
  if (expected === undefined || observed === null) return "open";
  if (expected === "borderline" || expected === "flag") return "open";
  return (expected === "present") === observed ? "match" : "miss";
}

function lastIndex(days: Timeline["days"], pred: (d: Timeline["days"][number]) => boolean): number {
  for (let i = days.length - 1; i >= 0; i--) if (pred(days[i])) return i;
  return -1;
}

export function CriteriaSummary({ tl, cfg, present, episode, theta, selected, onSelect }: Props) {
  const days = tl.days;
  const baseIdx = days.map((d, i) => (d.phase === "baseline" ? i : -1)).filter((i) => i >= 0);
  const clinIdx = days.map((d, i) => (d.phase === "clinical" ? i : -1)).filter((i) => i >= 0);
  const lastBase = lastIndex(days, (d) => d.phase === "baseline");
  const lastClin = lastIndex(days, (d) => d.phase === "clinical");
  const nClinPlanned = 14;

  const state = (c: CritKey, i: number): boolean | null =>
    i < 0 || !present[c] ? null : !!present[c]![i];

  const cell = (v: boolean | null) =>
    v === null ? <span className="muted">–</span>
      : v ? <span className="status status-on">● present</span>
        : <span className="status status-off">○ absent</span>;

  return (
    <section className="card">
      <div className="card-head">
        <h2>DSM-5 criteria: expected vs. observed</h2>
        <p className="sub">
          Gate state at the end of the baseline and on the latest clinical day
          {lastClin >= 0 && ` (day ${clinIdx.length} of ${nClinPlanned})`}. Days ≥ θ counts the
          days whose likelihood reaches θ = {theta.toFixed(2)}. Click a row for its metrics.
        </p>
      </div>
      <div className="table-wrap">
        <table className="crit-table">
          <thead>
            <tr>
              <th>Criterion</th>
              <th>Expected (§9)</th>
              <th className="num">Baseline<br />days ≥ θ</th>
              <th>End of baseline</th>
              <th className="num">Clinical<br />days ≥ θ</th>
              <th>Latest clinical</th>
              <th>vs. expected</th>
            </tr>
          </thead>
          <tbody>
            {CRIT_KEYS.map((c) => {
              const configured = Object.keys(cfg.criteria[c] ?? {}).length > 0;
              const exp = tl.persona.expected[c];
              const L = days.map((d) => d.L[c]);
              const obs = state(c, lastClin);
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
                  <td className="num">{configured ? daysAbove(L, theta, baseIdx) + " / " + baseIdx.length : "–"}</td>
                  <td>{configured ? cell(state(c, lastBase)) : <span className="muted">–</span>}</td>
                  <td className="num">{configured ? daysAbove(L, theta, clinIdx) + " / " + clinIdx.length : "–"}</td>
                  <td>{configured ? cell(obs) : <span className="muted">–</span>}</td>
                  <td>
                    {agr === "match" && <span className="agree">✓ as expected</span>}
                    {agr === "miss" && <span className="disagree">✗ differs</span>}
                    {agr === "open" && <span className="muted">{configured && exp ? "see note" : "–"}</span>}
                  </td>
                </tr>
              );
            })}
            <tr className="episode-row">
              <td><b>Episode</b> ≥ 5 present incl. core ({cfg.core.join(", ")})</td>
              <td title={tl.persona.episode?.note}>
                {tl.persona.episode?.expected ?? "–"}
                {tl.persona.episode?.note && <div className="note">{tl.persona.episode.note}</div>}
              </td>
              <td />
              <td>{lastBase >= 0 ? (episode[lastBase] ? <span className="status status-on">● likely</span> : <span className="status status-off">○ no</span>) : "–"}</td>
              <td />
              <td>{lastClin >= 0 ? (episode[lastClin] ? <span className="status status-on">● likely</span> : <span className="status status-off">○ no</span>) : "–"}</td>
              <td />
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  );
}
