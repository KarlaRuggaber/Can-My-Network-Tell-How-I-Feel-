import type { SourceItem } from "../api";
import { jumpTarget } from "./jump";

const base: SourceItem = { kind: "metric", id: "x", name: "x", icon: null, unit: null, values: [], usual: null, detail: null, code: null, days: [] };
const days = ["2025-10-30", "2025-10-31"];
const cfg = { metric_criterion: { C4_F2_WakeAfter0400Min: "C4" as const } };

describe("jumpTarget", () => {
  it("a day selects that day, only when the page has it", () => {
    expect(jumpTarget({ ...base, kind: "day", id: "2025-10-31" }, { multi: true, days })).toEqual({ day: "2025-10-31" });
    expect(jumpTarget({ ...base, kind: "day", id: "2024-01-01" }, { multi: true, days })).toEqual({});
  });
  it("a criterion opens the Details tab for clinicians", () => {
    const c = { ...base, kind: "criterion" as const, id: "C4", code: "C4", days: ["2025-10-31"] };
    expect(jumpTarget(c, { multi: true, days })).toEqual({ day: "2025-10-31", crit: "C4", tab: "details" });
    expect(jumpTarget({ ...c, code: null, id: "Sleep" }, { multi: true, days })).toEqual({ day: "2025-10-31" });
  });
  it("a scored metric opens its criterion and scrolls to its chart", () => {
    const m = { ...base, id: "C4_F2_WakeAfter0400Min", code: "C4_F2_WakeAfter0400Min", days: ["2025-10-30"] };
    expect(jumpTarget(m, { multi: true, days, cfg })).toEqual({ day: "2025-10-30", crit: "C4", tab: "details", scrollId: "metric-C4_F2_WakeAfter0400Min" });
  });
  it("an observed metric or a flag selects the latest named day; the person only ever gets a day", () => {
    expect(jumpTarget({ ...base, days: ["2025-10-30", "2025-10-31"] }, { multi: true, days })).toEqual({ day: "2025-10-31" });
    expect(jumpTarget({ ...base, kind: "flag", days: ["2025-10-30"] }, { multi: false, days })).toEqual({ day: "2025-10-30" });
    expect(jumpTarget({ ...base, kind: "criterion", code: "C4", days: ["2025-10-30"] }, { multi: false, days })).toEqual({ day: "2025-10-30" });
  });
});
