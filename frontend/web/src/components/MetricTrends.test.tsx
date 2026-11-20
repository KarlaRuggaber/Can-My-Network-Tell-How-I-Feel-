import type { Config, Day, MetricPart } from "../api";
import { metricUnit, whatContributed } from "./MetricTrends";

const tri = (lo: number, hi: number, invert = false) => ({ type: "tri", lo, mid: hi, hi, invert });
const cfg = {
  criteria: {
    C4: {
      C4_F2_WakeAfter0400Min: { w: 0.65, mf: tri(120, 1085) },
      C4_F4_SleepDurationZAbs30d: { w: 0.2, mf: tri(0.25, 0.8) },
      C4_F7_DaytimeIdleRatio0818: { w: 0.05, mf: tri(0, 0.16) },
      X_Unknown: { w: 0.1, mf: tri(0, 1, true) },
    },
  },
  metric_labels: { X_Unknown: "Upload Volume" },
} as unknown as Config;

const day = (date: string, mus: Record<string, number>): Day => ({
  date, weekday: "Mon", phase: "current", complete: true,
  parts: { C4: Object.fromEntries(Object.entries(mus).map(([k, mu]) => [k, { value: 1, mu, w: (cfg.criteria.C4 as Record<string, { w: number }>)[k].w } as MetricPart])) },
} as unknown as Day);

describe("whatContributed", () => {
  it("names the top metrics by w·μ and their outlier days", () => {
    const days = [
      day("2026-11-10", { C4_F2_WakeAfter0400Min: 0.9, C4_F4_SleepDurationZAbs30d: 0.6, C4_F7_DaytimeIdleRatio0818: 0 }),
      day("2026-11-11", { C4_F2_WakeAfter0400Min: 0.8, C4_F4_SleepDurationZAbs30d: 0.2, C4_F7_DaytimeIdleRatio0818: 0 }),
      day("2026-11-12", { C4_F2_WakeAfter0400Min: 0.1, C4_F4_SleepDurationZAbs30d: 0.7, C4_F7_DaytimeIdleRatio0818: 0 }),
      day("2026-11-14", { C4_F2_WakeAfter0400Min: 0.7, C4_F4_SleepDurationZAbs30d: 0.1, C4_F7_DaytimeIdleRatio0818: 0 }),
    ];
    const r = whatContributed(days, "C4", cfg);
    // w·μ sums: F2 0.65·2.5 = 1.625 (≈ 80 %), F4 0.2·1.6 = 0.32 (≈ 16 %): F2 alone covers 75 %
    expect(r.items.map((i) => i.metric)).toEqual(["C4_F2_WakeAfter0400Min"]);
    expect(r.items[0].outlierDays).toEqual(["2026-11-10", "2026-11-11", "2026-11-14"]);
    expect(r.text).toBe("Mainly 3 mornings with the first use long after 04:00 (10/11, 11/11, 14/11).");
  });

  it("adds a second metric until 75 % is explained, and words metrics without outlier days", () => {
    const days = [
      day("2026-11-10", { C4_F2_WakeAfter0400Min: 0.6, C4_F4_SleepDurationZAbs30d: 0.4 }),
      day("2026-11-11", { C4_F2_WakeAfter0400Min: 0.1, C4_F4_SleepDurationZAbs30d: 0.4 }),
    ];
    // F2 0.65·0.7 = 0.455 (≈ 74 %), F4 0.2·0.8 = 0.16 (≈ 26 %)
    expect(whatContributed(days, "C4", cfg).text).toBe(
      "Mainly 1 morning with the first use long after 04:00 (10/11) and smaller shifts towards a quiet window unlike the last weeks on most nights.");
  });

  it("says 'almost entirely' for one dominant metric and falls back to the label for unknown metrics", () => {
    const days = [day("2026-11-10", { X_Unknown: 1 }), day("2026-11-11", { X_Unknown: 0.7 })];
    expect(whatContributed(days, "C4", cfg).text).toBe("Almost entirely 2 days with low upload volume (10/11, 11/11).");
  });

  it("caps the date list and handles empty input", () => {
    const many = Array.from({ length: 6 }, (_, i) => day(`2026-11-1${i}`, { C4_F2_WakeAfter0400Min: 1 }));
    expect(whatContributed(many, "C4", cfg).text).toContain("(10/11, 11/11, 12/11, 13/11 and 2 more)");
    expect(whatContributed([], "C4", cfg).text).toMatch(/No complete days/);
    expect(whatContributed([day("2026-11-10", { C4_F2_WakeAfter0400Min: 0 })], "C4", cfg).text).toMatch(/^Nothing contributed/);
  });
});

describe("metricUnit", () => {
  it("names a unit for every metric, with a fallback from the key", () => {
    expect(metricUnit("C4_F2_WakeAfter0400Min")).toBe("minutes after 04:00");
    expect(metricUnit("C9_F1_CrisisLineHits")).toBe("count per day");
    expect(metricUnit("Something")).toBe("value");
  });
});
