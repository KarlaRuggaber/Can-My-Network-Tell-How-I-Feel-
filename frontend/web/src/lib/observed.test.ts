import type { Day, RiskFlag } from "../api";
import { flagSentence, fmtClock, fmtHours, inRange } from "./observed";

describe("observed helpers", () => {
  it("formats clock times across midnight", () => {
    expect(fmtClock(-90)).toBe("22:30");
    expect(fmtClock(0)).toBe("00:00");
    expect(fmtClock(405)).toBe("06:45");
    expect(fmtClock(null)).toBe("–");
    expect(fmtHours(8.25)).toBe("8 h 15");
    expect(fmtHours(7)).toBe("7 h");
  });
  it("words a flag for the person and for others", () => {
    const f = { id: "later_nights", count: 4, window: 7, unit: "nights", phrase: "went quiet later than usual" } as RiskFlag;
    expect(flagSentence(f, null)).toBe("On 4 of the last 7 nights you went quiet later than usual.");
    expect(flagSentence(f, "Maria")).toBe("On 4 of the last 7 nights Maria went quiet later than usual.");
  });
  it("selects the range from the last day back", () => {
    const days = Array.from({ length: 20 }, (_, i) => ({ date: `2026-11-${String(i + 1).padStart(2, "0")}` })) as Day[];
    expect(inRange(days, "7", "", "").map((d) => d.date)).toEqual(days.slice(-7).map((d) => d.date));
    expect(inRange(days, "custom", "2026-11-05", "2026-11-06").length).toBe(2);
    expect(inRange(days, "all", "", "").length).toBe(20);
  });
});
