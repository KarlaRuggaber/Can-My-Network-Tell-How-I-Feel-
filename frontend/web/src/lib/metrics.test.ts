import { describe, expect, it } from "vitest";
import { metricName, readable, visitText } from "./metrics";

describe("metric names", () => {
  it("never shows a code", () => {
    expect(readable("C4_F9_SomeNewMetricMin")).toBe("Some new metric (min)");
    expect(metricName("C9_F1_CrisisLineHits", { metric_labels: { C9_F1_CrisisLineHits: "Crisis-line sites" } })).toBe("Crisis-line sites");
    expect(metricName("C9_F12_NewThing", { metric_labels: {} })).toBe("New thing");
  });
  it("describes visits, not packets", () => {
    expect(visitText({ visits: 2, starts: ["23:40", "23:58"], minutes: 3 })).toBe("2 visits (23:40, 23:58), about 3 min");
    expect(visitText({ visits: 1, starts: ["09:00"], minutes: 1 })).toBe("1 visit (09:00), about 1 min");
    expect(visitText(null)).toBe("no visits");
  });
});
