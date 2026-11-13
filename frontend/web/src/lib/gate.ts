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
