import { blockTitle, spread } from "./ScrollRail";

describe("ScrollRail helpers", () => {
  it("takes the block title from data-rail or the first heading, without step numbers and icons", () => {
    const a = document.createElement("section");
    a.innerHTML = `<h2><span class="step">1</span>DSM-5 criteria</h2>`;
    expect(blockTitle(a)).toBe("DSM-5 criteria");
    const b = document.createElement("section");
    b.innerHTML = `<h2><svg aria-hidden="true"><title>About the data</title></svg> About the data</h2>`;
    expect(blockTitle(b)).toBe("About the data");
    const c = document.createElement("section");
    c.dataset.rail = "Week table";
    expect(blockTitle(c)).toBe("Week table");
    expect(blockTitle(document.createElement("section"))).toBeNull();
  });

  it("pushes dots apart so they never overlap and keeps them on the rail", () => {
    expect(spread([0, 0.01, 0.02], 0.05)).toEqual([0, 0.05, 0.1]);
    const end = spread([0.97, 0.98, 1], 0.05);
    expect(end[2]).toBeLessThanOrEqual(1);
    expect(end[1]).toBeCloseTo(0.95);
    expect(end[0]).toBeCloseTo(0.9);
  });
});
