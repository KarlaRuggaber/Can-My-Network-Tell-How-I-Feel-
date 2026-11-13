import { render, screen, within } from "@testing-library/react";
import type { Config, Day, Timeline } from "../api";
import { phaseGate } from "../lib/gate";
import { agreement, CriteriaSummary } from "./CriteriaSummary";

describe("agreement", () => {
  it("compares the gate state with the profile expectation", () => {
    expect(agreement("present", true)).toBe("match");
    expect(agreement("present", false)).toBe("miss");
    expect(agreement("no", false)).toBe("match");
    expect(agreement("elevated", true)).toBe("miss");   // elevated means: stays below the gate
    expect(agreement("borderline", true)).toBe("open");
    expect(agreement("present", null)).toBe("open");
  });
});

const spec = { a: { w: 1, mf: { type: "tri", lo: 0, mid: 1, hi: 2 } } };
const cfg = {
  M: 14, N: 6, theta: 0.6, tau: 1, core: ["C2"],
  criteria: { C1: spec, C2: spec, C3: {}, C4: spec, C5: {}, C6: {}, C7: {}, C8: spec, C9: {} },
  criterion_names: { C1: "Depressed mood", C2: "Anhedonia", C3: "Appetite", C4: "Sleep", C5: "Psychomotor", C6: "Fatigue", C7: "Worthlessness", C8: "Concentration", C9: "Suicidality" },
  metric_labels: {}, metric_criterion: {}, fasl_config_path: "",
} as unknown as Config;

const day = (date: string, phase: string, c4: number): Day => ({
  date, weekday: "Mon", phase, complete: true, n_partitions: 288, packets_kept: 1,
  first_packet: null, last_packet: null, computed_at: "",
  ground_truth: { n_blocks: 0, n_profile_blocks: 0, n_sensitive: 0, n_failed: 0, n_not_run: 0, profile_blocks: {} },
  metrics: {}, parts: {},
  L: { C1: 0.1, C2: 0.1, C3: null, C4: c4, C5: null, C6: null, C7: null, C8: 0.1, C9: null },
});

const tl: Timeline = {
  dataset: "gw_x_a",
  persona: {
    name: "Ben", condition: "Insomnia", profile: null, baseline_profile: "9to5-worker", summary: "",
    expected: { C4: { present: "present", note: "" }, C1: { present: "elevated", note: "" } },
    episode: { expected: "no", note: "" },
  },
  days: [day("2026-11-07", "baseline", 0.1), day("2026-11-08", "baseline", 0.1),
    day("2026-11-09", "clinical", 0.9), day("2026-11-10", "clinical", 0.8)],
  gate: {
    params: { theta: 0.6, N: 2, M: 14, core: ["C2"], min_present: 5 },
    phases: {} as Timeline["gate"]["phases"],
    rolling: { present: {}, episode: [], note: "" },
  },
  baseline_stats: {},
};

const gate = { theta: 0.6, N: 2, M: 14, core: ["C2"], minPresent: 5 };

function phaseView(ph: "baseline" | "clinical") {
  const days = tl.days.filter((d) => d.phase === ph);
  const L = Object.fromEntries((["C1", "C2", "C4", "C8"] as const).map((c) => [c, days.map((d) => d.L[c])]));
  return {
    ...phaseGate(L, gate), counted: days.map((d) => d.date), inProgress: ph === "clinical" ? ["2026-11-11"] : [],
    plannedFirst: ph === "baseline" ? "2026-10-26" : "2026-11-09",
    plannedLast: ph === "baseline" ? "2026-11-08" : "2026-11-22", plannedDays: 14,
  };
}

describe("CriteriaSummary", () => {
  it("shows each phase's gate on its own days, the verdict, and only scored criteria in the table", () => {
    render(<CriteriaSummary tl={tl} cfg={cfg} gate={gate}
      phases={{ baseline: phaseView("baseline"), clinical: phaseView("clinical") }}
      selected={null} onSelect={() => undefined} />);
    const c4 = screen.getByRole("cell", { name: /C4 Sleep/ }).closest("tr")!;
    expect(within(c4).getByText("0 of 2")).toBeTruthy();          // baseline: 0 of its 2 days >= theta
    expect(within(c4).getByText("2 of 2")).toBeTruthy();          // clinical: 2 of its 2 days
    expect(within(c4).getByText("absent")).toBeTruthy();          // baseline gate
    expect(within(c4).getAllByText("present")).toHaveLength(2);   // expected + clinical gate (N = 2)
    expect(within(c4).getByText("✓ yes")).toBeTruthy();
    expect(screen.queryByRole("cell", { name: /Appetite/ })).toBeNull();   // not scored: footnote only
    expect(screen.getByText(/Not scored by the current configuration: C3 Appetite/)).toBeTruthy();
    expect(screen.getByText("preliminary · day 2 of 14")).toBeTruthy();
    expect(screen.getByText("26/10–08/11")).toBeTruthy();
    expect(screen.getByText(/expectations met so far/)).toBeTruthy();    // C4 met; C1 elevated met (absent)
  });
});
