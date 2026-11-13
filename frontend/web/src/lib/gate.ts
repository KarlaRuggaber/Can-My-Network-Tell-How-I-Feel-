// Rolling DSM gate, identical to cmn_frontend.fasl.gate_present_rolling / episode_flags.
// Shared test cases: frontend/shared/gate_cases.json.

export interface GateParams { theta: number; N: number; M: number; core: string[]; minPresent: number }

const finite = (v: number | null | undefined): v is number =>
  typeof v === "number" && Number.isFinite(v);

/** present[i]: at least N of the last M days with data (up to day i) have L >= theta. */
export function gatePresentRolling(
  L: (number | null)[], theta: number, N: number, M: number,
): boolean[] {
  const hist: number[] = [];
  return L.map((v) => {
    if (finite(v)) hist.push(v);
    const tail = M > 0 ? hist.slice(-M) : [];
    return tail.length > 0 && tail.filter((x) => x >= theta).length >= N;
  });
}

/** Episode likely on day i: >= minPresent criteria present, at least one of them core. */
export function episodeFlags(present: Record<string, boolean[]>, p: GateParams): boolean[] {
  const n = Math.max(0, ...Object.values(present).map((v) => v.length));
  return Array.from({ length: n }, (_, i) => {
    const on = Object.entries(present).filter(([, v]) => v[i]).map(([c]) => c);
    return on.length >= p.minPresent && on.some((c) => p.core.includes(c));
  });
}

/** Days with L >= theta in a set of day indices. */
export function daysAbove(L: (number | null)[], theta: number, idx: number[]): number {
  return idx.filter((i) => finite(L[i]) && (L[i] as number) >= theta).length;
}

export interface PhaseGate {
  days: number;                     // days in the window: the last M of the phase
  nPhaseDays: number;
  criteria: Record<string, { daysOver: number; present: boolean }>;
  totalPresent: number;
  corePresent: boolean;
  episode: boolean;
}

/** The gate on one phase's days only, identical to cmn_frontend.fasl.phase_gate and the
 * evaluation's score_phases: days_over counts the last M days of the phase (a missing L is a day,
 * not >= theta); present is the page's gate_present (last M days with data). */
export function phaseGate(L: Record<string, (number | null)[]>, p: GateParams): PhaseGate {
  const n = Math.max(0, ...Object.values(L).map((v) => v.length));
  const criteria: PhaseGate["criteria"] = {};
  for (const [c, vals] of Object.entries(L)) {
    const tail = p.M > 0 ? vals.slice(-p.M) : [];
    const withData = vals.filter(finite);
    const tailData = p.M > 0 ? withData.slice(-p.M) : [];
    criteria[c] = {
      daysOver: tail.filter((v) => finite(v) && v >= p.theta).length,
      present: tailData.length > 0 && tailData.filter((x) => x >= p.theta).length >= p.N,
    };
  }
  const on = Object.keys(criteria).filter((c) => criteria[c].present);
  const corePresent = on.some((c) => p.core.includes(c));
  return {
    days: p.M > 0 ? Math.min(n, p.M) : 0, nPhaseDays: n, criteria,
    totalPresent: on.length, corePresent, episode: corePresent && on.length >= p.minPresent,
  };
}
