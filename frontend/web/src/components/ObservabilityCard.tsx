import type { Config, CritKey } from "../api";
import { CRIT_KEYS } from "../api";
import { Icon } from "./Icon";

export const OBS_LEVEL: Record<string, [string, string]> = {
  good: ["Good", "clear, fairly specific signal"],
  partial: ["Partial", "signal present but ambiguous or needs the person's baseline"],
  none: ["Barely", "no reliable network trace; use questionnaires or interviews"],
};

/** Observability per DSM-5 criterion C1–C9 (profiles/symptom-network-mapping.md §3, §8). */
export function ObservabilityTable({ cfg, focus, onAsk }: {
  cfg: Config; focus: CritKey[]; onAsk?: (q: string, f: string) => void;
}) {
  const obs = cfg.observability;
  if (!obs) return null;
  return (
    <>
      <div className="table-wrap">
        <table className="obs-table">
          <thead><tr><th>Criterion</th><th>Observable</th><th>What the network sees</th><th>What it cannot see</th><th>Caveats</th><th /></tr></thead>
          <tbody>
            {CRIT_KEYS.map((c) => {
              const o = obs[c];
              if (!o) return null;
              return (
                <tr key={c} className={focus.includes(c) ? "selected" : ""}>
                  <td><b>{c}</b> {cfg.criterion_names[c]}
                    {focus.includes(c) && <span className="tag">focus</span>}
                    {!o.scored && <span className="tag tag-muted">not scored</span>}</td>
                  <td><span className={`obs obs-${o.level}`} title={OBS_LEVEL[o.level][1]}>{OBS_LEVEL[o.level][0]}</span></td>
                  <td>{o.observes}</td>
                  <td className="muted">{o.cannot}</td>
                  <td className="small muted">{o.caveats.join(" ")}</td>
                  <td>{onAsk && <button className="link small explain-link" onClick={() => onAsk(`What exactly can the network tell about ${c} ${cfg.criterion_names[c]}, which metrics carry it, and how should a clinician read its likelihood?`, `observability, ${c}`)}>
                    <Icon name="explain" label="Ask the assistant" /> ask</button>}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="muted small">Good: {OBS_LEVEL.good[1]}. Partial: {OBS_LEVEL.partial[1]}. Barely: {OBS_LEVEL.none[1]}.</p>
    </>
  );
}

/** What the network can tell per DSM-5 criterion, as a card. Superseded by the "About the data" tab (AboutData). */
export function ObservabilityCard({ cfg, focus, onAsk, step }: {
  cfg: Config; focus: CritKey[]; onAsk?: (q: string, f: string) => void; step: number;
}) {
  if (!cfg.observability) return null;
  return (
    <section className="card">
      <div className="card-head">
        <h2><span className="step">{step}</span>What the network can tell</h2>
        <p className="sub">How well each criterion can be seen from home-network metadata (when and how much devices are in use,
          which sites by hostname; no content, no search terms), from the project's symptom–network mapping.</p>
      </div>
      <ObservabilityTable cfg={cfg} focus={focus} onAsk={onAsk} />
    </section>
  );
}
