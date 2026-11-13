import { render, screen, within } from "@testing-library/react";
import type { Config, Day, Timeline } from "../api";
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
  gate: { params: { theta: 0.6, N: 2, M: 14, core: ["C2"], min_present: 5 }, present: {}, episode: [] },
  baseline_stats: {},
};

describe("CriteriaSummary", () => {
  it("shows gate state at end of baseline and on the latest clinical day", () => {
    const present = {
      C1: [false, false, false, false], C2: [false, false, false, false],
      C4: [false, false, false, true], C8: [false, false, false, false],
    };
    render(<CriteriaSummary tl={tl} cfg={cfg} present={present} episode={[false, false, false, false]}
      theta={0.6} selected={null} onSelect={() => undefined} />);
    const c4 = screen.getByText("Sleep").closest("tr")!;
    expect(within(c4).getByText("0 / 2")).toBeTruthy();          // baseline days >= theta
    expect(within(c4).getByText("2 / 2")).toBeTruthy();          // clinical days >= theta
    expect(within(c4).getByText("● present")).toBeTruthy();
    expect(within(c4).getByText("✓ as expected")).toBeTruthy();
    const c3 = screen.getByText("Appetite").closest("tr")!;
    expect(within(c3).getByText("not configured")).toBeTruthy();
    expect(screen.getByText(/day 2 of 14/)).toBeTruthy();
  });
});
