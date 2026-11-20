// Shared ECharts helpers (frontend/VISUAL.md): one implementation for axis names, the baseline
// band and the usual / typical ranges, so every chart draws and names them the same way.
import { C, FONT } from "../theme";

/** Names used in every chart, legend and tooltip. */
export const BAND_LABELS = {
  baseline: "Baseline (usual weeks)",
  usual: "Usual range",
  typical: "Typical range",
} as const;

/**
 * Y-axis name: what is measured and its unit, e.g. axisName("Time in use", "minutes per hour").
 * Spread into the axis: `yAxis: { type: "value", ...axisName("Quiet window", "hours") }`.
 */
export function axisName(label: string, unit?: string, gap = 40) {
  const text = unit ? `${label} (${unit})` : label;
  return {
    name: text,
    nameLocation: "middle" as const,
    nameGap: gap,
    nameRotate: 90,
    nameTextStyle: { color: C.text2, fontSize: 11, fontFamily: FONT.sans },
  };
}

type Item = Record<string, unknown>;
export type MarkAreaPair = [Item, Item];
export interface MarkArea { silent: true; data: MarkAreaPair[] }

/** A day as the charts see it: only the phase matters here, the date for time axes. */
export interface PhaseDay { date?: string; phase?: string | null }

/**
 * The only shaded period: the baseline days, as a light neutral vertical band labelled
 * "Baseline (usual weeks)". Recent / clinical days get no shading. Works on a category axis
 * (day index, the default) or a time axis (`axis: "time"`, uses `date`). Non-contiguous baseline
 * days give one band per run; only the first carries the label.
 */
export function baselineMarkArea(
  days: readonly PhaseDay[],
  opts: { axis?: "category" | "time"; label?: boolean } = {},
): MarkArea {
  const { axis = "category", label = true } = opts;
  const runs: [number, number][] = [];
  days.forEach((d, i) => {
    if (d.phase !== "baseline") return;
    const last = runs[runs.length - 1];
    if (last && last[1] === i - 1) last[1] = i;
    else runs.push([i, i]);
  });
  const at = (i: number) => (axis === "time" ? days[i].date : i);
  return {
    silent: true,
    data: runs.map(([a, b], k): MarkAreaPair => [
      {
        name: BAND_LABELS.baseline,
        xAxis: at(a),
        itemStyle: { color: C.baselineShade },
        label: {
          show: label && k === 0, position: "insideTopLeft", color: C.text2, fontSize: 10,
          fontFamily: FONT.sans, formatter: BAND_LABELS.baseline,
        },
      },
      { xAxis: at(b) },
    ]),
  };
}

/** The person's own usual range (mean ± 1 SD of the usual weeks): a filled horizontal band. */
export function usualBand(stats: { mean: number; sd: number } | null | undefined): MarkArea {
  if (!stats || !Number.isFinite(stats.mean) || !Number.isFinite(stats.sd)) return { silent: true, data: [] };
  return {
    silent: true,
    data: [[
      { name: BAND_LABELS.usual, yAxis: stats.mean - stats.sd, itemStyle: { color: C.usualBand }, label: { show: false } },
      { yAxis: stats.mean + stats.sd },
    ]],
  };
}

/** Reference range of other people, P16–P84 (≈ mean ± 1 SD), with the median. */
export interface TypicalRange { p16: number; p50: number; p84: number }

/** The typical range (other people): a dashed outline, never filled. */
export function typicalBand(range: TypicalRange | null | undefined): MarkArea {
  if (!range || !Number.isFinite(range.p16) || !Number.isFinite(range.p84)) return { silent: true, data: [] };
  return {
    silent: true,
    data: [[
      {
        name: BAND_LABELS.typical, yAxis: range.p16,
        itemStyle: { color: "transparent", borderColor: C.typicalLine, borderWidth: 1, borderType: "dashed" },
        label: { show: false },
      },
      { yAxis: range.p84 },
    ]],
  };
}

/** One series has one markArea: combine baseline band and ranges, e.g.
 *  `markArea: mergeMarkAreas(baselineMarkArea(days), usualBand(s), typicalBand(r))`. */
export function mergeMarkAreas(...areas: (MarkArea | null | undefined)[]): MarkArea {
  return { silent: true, data: areas.flatMap((a) => a?.data ?? []) };
}

/** Colour of the neutral intensity scale for a value in [0, 1] (clamped; null → lightest step). */
export function intensityColor(t: number | null | undefined): string {
  const n = C.intensity.length;
  const v = typeof t === "number" && Number.isFinite(t) ? Math.min(1, Math.max(0, t)) : 0;
  return C.intensity[Math.round(v * (n - 1))];
}

/** Text colour readable on a given intensity step (white from `intensityWhiteFrom`, ink before). */
export function intensityTextColor(step: number): string {
  return step >= C.intensityWhiteFrom ? "#ffffff" : C.text;
}
