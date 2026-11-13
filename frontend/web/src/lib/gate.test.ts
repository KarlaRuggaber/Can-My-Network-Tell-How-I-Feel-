import cases from "../../../shared/gate_cases.json";
import { daysAbove, episodeFlags, gatePresentRolling } from "./gate";

describe("gatePresentRolling", () => {
  it.each(cases.cases)("matches the shared Python cases %#", (c) => {
    expect(gatePresentRolling(c.L, c.theta, c.N, c.M)).toEqual(c.present);
  });
});

describe("episodeFlags", () => {
  const p = { theta: 0.6, N: 1, M: 1, core: ["C2"], minPresent: 5 };
  it("needs five criteria including a core one", () => {
    const five = { C1: [true], C3: [true], C4: [true], C5: [true], C6: [true] };
    expect(episodeFlags(five, p)).toEqual([false]);
    expect(episodeFlags({ ...five, C2: [true] }, p)).toEqual([true]);
    expect(episodeFlags({ C1: [true], C2: [true], C4: [true], C8: [true] }, p)).toEqual([false]);
  });
  it("handles no criteria", () => expect(episodeFlags({}, p)).toEqual([]));
});

describe("daysAbove", () => {
  it("counts finite values at or above theta in the given days", () => {
    expect(daysAbove([0.6, null, 0.9, 0.1], 0.6, [0, 1, 2, 3])).toBe(2);
    expect(daysAbove([0.6, null, 0.9, 0.1], 0.6, [3])).toBe(0);
  });
});
