import { render, screen } from "@testing-library/react";
import type { Config, Day, Timeline } from "../api";
import { phaseGate } from "../lib/gate";
import { areaStatus, PersonView } from "./PersonView";

vi.mock("./Chart", () => ({ Chart: () => null }));   // ECharts needs a real browser

const spec = { a: { w: 1, mf: { type: "tri", lo: 0, mid: 1, hi: 2 } } };
const cfg = {
  M: 14, N: 2, theta: 0.6, tau: 1, core: ["C2"],
  criteria: { C1: spec, C2: spec, C3: {}, C4: spec, C5: {}, C6: {}, C7: {}, C8: spec, C9: {} },
  criterion_names: { C1: "Depressed mood", C2: "Anhedonia", C3: "", C4: "Sleep timing", C5: "", C6: "", C7: "", C8: "Concentration", C9: "Suicidality" },
  metric_labels: {}, metric_criterion: {}, fasl_config_path: "",
} as unknown as Config;
const day = (date: string, phase: string, c4: number): Day => ({
  date, weekday: "Mon", phase, complete: true, n_partitions: 1, packets_kept: 1000,
  first_packet: null, last_packet: null, computed_at: "", ground_truth: null, metrics: {}, parts: {},
  L: { C1: 0.1, C2: 0.1, C3: null, C4: c4, C5: null, C6: null, C7: null, C8: 0.7, C9: null },
});
const days = [day("2026-11-01", "baseline", 0.1), day("2026-11-09", "current", 0.9), day("2026-11-10", "current", 0.8)];
const gate = { theta: 0.6, N: 2, M: 14, core: ["C2"], minPresent: 5 };
const cur = days.filter((d) => d.phase === "current");
const recent = {
  ...phaseGate(Object.fromEntries((["C1", "C2", "C4", "C8"] as const).map((c) => [c, cur.map((d) => d.L[c])])), gate),
  counted: cur.map((d) => d.date), inProgress: [], plannedFirst: null, plannedLast: null, plannedDays: 0,
};
const tl = {
  profile: { id: "ben", name: "Ben", source: "s", all_devices: true, devices: [], baseline_first: null, baseline_last: null,
    persona: null, view_key: "all", has_plan: false, phase_labels: { baseline: "Usual weeks", current: "Recent" } },
  persona: { id: "ben", source: "s", scripted: false, name: "Ben", condition: "", profile: null, baseline_profile: null,
    summary: "", expected: {}, episode: null },
  status: "ready", days, gate: { params: { theta: 0.6, N: 2, M: 14, core: ["C2"], min_present: 5 }, phases: {} as Timeline["gate"]["phases"],
    rolling: { present: {}, episode: [], note: "" } }, baseline_stats: {},
} as Timeline;

describe("PersonView", () => {
  it("shows everyday areas with plain statuses and no clinical terms", () => {
    expect(areaStatus(recent, "C4")).toBe("different");
    expect(areaStatus(recent, "C1")).toBe("usual");
    const { container } = render(<PersonView tl={tl} cfg={cfg} recent={recent} gate={gate} />);
    expect(screen.getByText("Hello Ben")).toBeTruthy();
    expect(screen.getByText("Sleep")).toBeTruthy();
    expect(screen.getAllByText("Noticeably different")).toHaveLength(2);   // Sleep and Focus
    const text = container.textContent ?? "";
    for (const word of ["Depressed", "Anhedonia", "Suicidality", "DSM", "C4", "expected", "θ"]) {
      expect(text).not.toContain(word);
    }
  });
});
