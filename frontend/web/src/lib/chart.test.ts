import { C } from "../theme";
import {
  BAND_LABELS, axisName, baselineMarkArea, intensityColor, intensityTextColor, mergeMarkAreas, typicalBand, usualBand,
} from "./chart";

describe("chart helpers", () => {
  it("names an axis with what and unit", () => {
    expect(axisName("Time in use", "minutes per hour")).toMatchObject({ name: "Time in use (minutes per hour)", nameLocation: "middle" });
    expect(axisName("likelihood 0–1").name).toBe("likelihood 0–1");
  });

  it("shades only the baseline days, one band per run, labelled once", () => {
    const days = ["baseline", "baseline", "current", "baseline", "current", "current"].map((phase, i) => ({ phase, date: `2026-11-0${i + 1}` }));
    const area = baselineMarkArea(days);
    expect(area.data).toHaveLength(2);
    expect(area.data[0][0]).toMatchObject({ xAxis: 0, name: BAND_LABELS.baseline, itemStyle: { color: C.baselineShade } });
    expect(area.data[0][1]).toEqual({ xAxis: 1 });
    expect(area.data[1][0].xAxis).toBe(3);
    expect((area.data[0][0].label as { show: boolean; formatter: string })).toMatchObject({ show: true, formatter: "Baseline (usual weeks)" });
    expect((area.data[1][0].label as { show: boolean }).show).toBe(false);
    expect(baselineMarkArea(days, { axis: "time" }).data[0][0].xAxis).toBe("2026-11-01");
    expect(baselineMarkArea([{ phase: "current" }]).data).toEqual([]);
  });

  it("draws the usual range filled and the typical range as a dashed outline", () => {
    const u = usualBand({ mean: 10, sd: 2 }).data[0];
    expect(u[0]).toMatchObject({ yAxis: 8, itemStyle: { color: C.usualBand } });
    expect(u[1]).toEqual({ yAxis: 12 });
    const t = typicalBand({ p16: 5, p50: 7, p84: 9 }).data[0];
    expect(t[0]).toMatchObject({ yAxis: 5, itemStyle: { color: "transparent", borderType: "dashed", borderColor: C.typicalLine } });
    expect(t[1]).toEqual({ yAxis: 9 });
    expect(usualBand(null).data).toEqual([]);
    expect(typicalBand(undefined).data).toEqual([]);
  });

  it("merges bands into one markArea", () => {
    const m = mergeMarkAreas(baselineMarkArea([{ phase: "baseline" }]), usualBand({ mean: 1, sd: 1 }), null, typicalBand({ p16: 0, p50: 1, p84: 2 }));
    expect(m.silent).toBe(true);
    expect(m.data).toHaveLength(3);
  });

  it("maps values onto the neutral intensity scale", () => {
    expect(C.intensity).toHaveLength(8);
    expect(intensityColor(0)).toBe(C.intensity[0]);
    expect(intensityColor(1)).toBe(C.intensity[7]);
    expect(intensityColor(2)).toBe(C.intensity[7]);
    expect(intensityColor(null)).toBe(C.intensity[0]);
    expect(intensityTextColor(C.intensityWhiteFrom)).toBe("#ffffff");
    expect(intensityTextColor(0)).toBe(C.text);
  });
});
