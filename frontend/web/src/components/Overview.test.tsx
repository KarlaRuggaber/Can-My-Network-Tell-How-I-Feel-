import { fireEvent, render, screen, within } from "@testing-library/react";
import type { Day, RiskFlag, Timeline } from "../api";
import { DataLabel } from "./DataLabel";
import { Overview } from "./Overview";
import { Timeline as TimelineView } from "./Timeline";

// ECharts needs a real layout; the tests check the page structure, not the charts.
vi.mock("./Chart", () => ({ Chart: ({ ariaLabel }: { ariaLabel: string }) => <div role="img" aria-label={ariaLabel} /> }));

const obsDay = (date: string, phase: string, quiet_start: number, online_hours: number): Day => ({
  date, weekday: "Mon", phase, complete: true, n_partitions: 288, packets_kept: 1,
  first_packet: null, last_packet: null, computed_at: "", ground_truth: null, metrics: {}, hourly: null,
  L: { C1: null, C2: null, C3: null, C4: null, C5: null, C6: null, C7: null, C8: null, C9: null }, parts: {},
  observed: {
    quiet_start, quiet_end: 420, quiet_hours: (420 - quiet_start) / 60, online_hours, night_minutes: 5,
    chat_sessions: 3, sites: 20, active_hourly: Array.from({ length: 24 }, (_, h) => (h >= 8 && h < 22 ? 30 : 0)),
    has_data: true, deviation: {},
  },
});

const flag = (over: Partial<RiskFlag>): RiskFlag => ({
  id: "later_nights", title: "Later nights", track: "quiet_start", direction: 1, days: ["2026-11-10"], count: 4,
  window: 7, unit: "nights", phrase: "went quiet later than usual", text: "", sensitive: false, basis: "own", ...over,
});

const makeTl = (flags: RiskFlag[], extra: Partial<Timeline> = {}): Timeline => ({
  profile: {
    id: "ben", name: "Ben", source: "s", all_devices: false, devices: [{ ip: "10.0.0.2", label: "phone" }],
    baseline_first: null, baseline_last: null, persona: "s", view_key: "x", reference: null, reference_mode: "baseline",
    has_plan: true, phase_labels: { baseline: "Baseline", current: "Clinical" },
  },
  persona: { id: "s", source: "s", scripted: true, name: "Ben", condition: "", profile: null, baseline_profile: null, summary: "", expected: {}, episode: null },
  status: "ready",
  days: [obsDay("2026-11-09", "baseline", -60, 5), obsDay("2026-11-10", "current", 90, 7)],
  gate: { params: { theta: 0.6, N: 6, M: 14, core: [], min_present: 5 }, phases: {} as Timeline["gate"]["phases"], rolling: { present: {}, episode: [], note: "" } },
  baseline_stats: {},
  observed: {
    tracks: [
      { key: "quiet_start", label: "Went quiet", unit: "time", sensitive: false, risk: [1] },
      { key: "online_hours", label: "Time in use", unit: "h", sensitive: false, risk: [1, -1] },
    ],
    usual: { online_hours: { mean: 5, sd: 1, n: 14 }, quiet_start: { mean: -60, sd: 30, n: 14 } },
    reference: null,
    flags,
    params: { active_packets: 50, deviation_z: 1.5, flag_days: 3, flag_window: 7, sensitive_window: 7, night_from_hour: 0, night_to_hour: 6 },
  },
  ...extra,
});

const noop = () => undefined;

describe("Overview, person view", () => {
  it("shows the week table, no data label (own tab), no flags and no charts until asked", () => {
    render(<Overview tl={makeTl([flag({})])} person selectedDay={null} onSelectDay={noop} />);
    expect(screen.queryByText("What this page is based on")).toBeNull();
    expect(screen.queryByText(/Hello/)).toBeNull();
    expect(screen.queryByText("What stands out")).toBeNull();
    expect(screen.queryByText("Later nights")).toBeNull();
    const table = screen.getByRole("table");
    expect(within(table).getByText("7 h")).toBeTruthy();          // time in use on the last day
    expect(within(table).getByText("01:30")).toBeTruthy();        // went quiet after midnight
    expect(within(table).getByText(/usual weeks/)).toBeTruthy();
    expect(screen.queryByText("Devices quiet at night")).toBeNull();
    expect(screen.queryByRole("group", { name: "Time range" })).toBeNull();
  });
  it("has the data label on its own 'About the data' tab", () => {
    render(<DataLabel tl={makeTl([])} />);
    expect(screen.getByText("What this page is based on")).toBeTruthy();
    expect(screen.getByText("Collected")).toBeTruthy();
    expect(screen.getByText("Not collected")).toBeTruthy();
    expect(screen.getByText("Search terms")).toBeTruthy();
    expect(screen.getByText(/Your care team also sees/)).toBeTruthy();
  });
  it("shows the charts behind a button, with the toolbar hidden by default", () => {
    render(<Overview tl={makeTl([])} person selectedDay={null} onSelectDay={noop} />);
    fireEvent.click(screen.getByRole("button", { name: "Show charts" }));
    expect(screen.getByText("Devices quiet at night")).toBeTruthy();
    expect(screen.queryByText(/Quiet window at night/)).toBeNull();
    expect(screen.queryByRole("group", { name: "Time range" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Chart options/ }));
    expect(screen.getByRole("group", { name: "Time range" })).toBeTruthy();
  });
});

describe("Overview, clinician view", () => {
  it("renders risk, alert and change flags with their labels", () => {
    const flags = [
      flag({}),
      flag({ id: "sensitive_sites", title: "Crisis or self-harm sites", track: "sensitive_days", sensitive: true, text: "Visits above the usual level." }),
      flag({ id: "earlier_nights", title: "Earlier nights", kind: "change", icon: "change", phrase: "went quiet earlier than usual" }),
      flag({ id: "irregular_nights", title: "Irregular nights", track: "quiet_start_sd7", icon: "irregular", phrase: "had more irregular nights" }),
    ];
    const { container } = render(<Overview tl={makeTl(flags)} person={false} selectedDay={null} onSelectDay={noop} />);
    expect(screen.getByText("What stands out")).toBeTruthy();
    expect(container.querySelectorAll(".flag-alert")).toHaveLength(1);
    expect(container.querySelector(".flag-alert")?.textContent).toContain("Crisis or self-harm sites");
    expect(container.querySelector(".flag-change")?.textContent).toContain("to discuss");
    expect(screen.getByText("Notable changes, to discuss")).toBeTruthy();
    expect([...container.querySelectorAll(".flag-title")].some((e) => e.textContent === "Irregular nights")).toBe(true);
    expect(screen.getByRole("group", { name: "Time range" })).toBeTruthy();
  });
  it("orders the comparisons by the care-plan purpose", () => {
    const tl = makeTl([], { care: { purpose: "assessment", routine: null, away_periods: [], clinical: null, updated: {} } });
    tl.observed!.reference = { source: "external", label: "typical 15–18 y, actigraphy", tracks: { quiet_start: { p16: -90, p50: -30, p84: 30 } } };
    render(<Overview tl={tl} person={false} selectedDay={null} onSelectDay={noop} />);
    const titles = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(titles.indexOf("Compared with the typical range")).toBeLessThan(titles.indexOf("Compared with Ben's usual weeks"));
    expect(screen.getByText(/typical 15–18 y, actigraphy/)).toBeTruthy();
  });
});

describe("Timeline, person view", () => {
  it("shows one line per day with the three facts and a labelled strip", () => {
    const { container } = render(<TimelineView tl={makeTl([flag({})])} person notes={[]} onNotes={noop} selectedDay={null} onSelectDay={noop} />);
    expect(container.querySelectorAll(".tlp-day")).toHaveLength(2);
    expect(screen.getByText(/empty = no use/)).toBeTruthy();
    expect(container.querySelectorAll(".hour")).toHaveLength(48);
    expect(screen.queryByText("Later nights")).toBeNull();
    expect(screen.queryByText(/Add note/)).toBeNull();
  });
});
