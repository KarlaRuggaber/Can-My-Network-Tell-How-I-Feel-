import type { Day, Observed, RiskFlag } from "../api";
import { flagIcon, flagKind, flagSentence, fmtClock, fmtHours, inRange, percentileText, typicalRange, typicalWording } from "./observed";

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

describe("v3 reference helpers", () => {
  const obs = (reference: Observed["reference"]) => ({ usual: {}, reference } as unknown as Observed);
  it("takes the typical range from the percentiles, else from the v2 mean ± SD", () => {
    const v3 = typicalRange(obs({ source: "external", label: "15–18 y", tracks: { quiet_hours: { p16: 6.5, p50: 7.4, p84: 8.3, proxy_note: "upper bound" } } }), "quiet_hours");
    expect(v3).toMatchObject({ lo: 6.5, mid: 7.4, hi: 8.3, source: "external", percentiles: true, proxyNote: "upper bound" });
    const v2 = typicalRange(obs({ stats: { sites: { mean: 30, sd: 5, n: 40 } }, n_days: 40, people: ["A"] }), "sites");
    expect(v2).toMatchObject({ lo: 25, hi: 35, percentiles: false });
    expect(typicalRange(obs(null), "sites")).toBeNull();
  });
  it("words percentiles in the direction of the day", () => {
    expect(percentileText("quiet_start", 85)).toBe("later than 85 % of reference nights");
    expect(percentileText("quiet_start", 10)).toBe("earlier than 90 % of reference nights");
    expect(percentileText("sites", null)).toBeNull();
  });
  it("gives the alert icon only to crisis/self-harm sites", () => {
    const base = { id: "x", track: "quiet_start", sensitive: false, basis: "own" } as RiskFlag;
    expect(flagIcon({ ...base, id: "sensitive_sites", sensitive: true })).toBe("alert");
    expect(flagIcon({ ...base, icon: "alert" })).toBe("moon");
    expect(flagIcon({ ...base, kind: "change" })).toBe("change");
    expect(flagIcon({ ...base, id: "irregular_nights", track: "quiet_start_sd7" })).toBe("irregular");
    expect(flagKind({ ...base, kind: "change" })).toBe("change");
  });
  it("replaces healthy-people wording", () => {
    expect(typicalWording("Later nights than healthy people")).toBe("Later nights than typical");
  });
});
describe("typical wording in flag sentences", () => {
  it("keeps the sentence grammatical", () => {
    expect(typicalWording("Ben had fewer chat sessions than healthy people usually do.")).toBe("Ben had fewer chat sessions than is typical.");
  });
});
