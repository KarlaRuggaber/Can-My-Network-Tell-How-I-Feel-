import { fmtNum, fmtTime, minutesInDay } from "./format";

describe("format", () => {
  it("formats numbers", () => {
    expect(fmtNum(null)).toBe("–");
    expect(fmtNum(1234)).toBe("1,234");
    expect(fmtNum(884068)).toBe("884.1K");
    expect(fmtNum(0.256)).toBe("0.26");
    expect(fmtNum(0.000254)).toBe("2.5e-4");
  });
  it("reads wall-clock time from ISO strings", () => {
    expect(fmtTime("2026-11-11T00:28:57+01:00")).toBe("00:28");
  });
  it("clips blocks crossing midnight to the day", () => {
    expect(minutesInDay("2026-11-08T23:50:00+01:00", "2026-11-09")).toBe(0);
    expect(minutesInDay("2026-11-09T00:30:00+01:00", "2026-11-08")).toBe(1440);
    expect(minutesInDay("2026-11-09T01:30:30+01:00", "2026-11-09")).toBe(90.5);
  });
});
