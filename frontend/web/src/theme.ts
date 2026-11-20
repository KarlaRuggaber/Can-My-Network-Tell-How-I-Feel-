// Look of the midterm presentation: Book Antiqua titles, Arial text, thin black outlines. v3 rules
// (frontend/VISUAL.md): red only for alerts, one neutral intensity scale, only the baseline period
// shaded. Data colours checked with the dataviz palette validator (light mode, white surface).
export const BRAND = { red: "#DC3A4F", beige: "#EBD6C1", ink: "#262626" };

/** Placeholder product name (decision §8); the thesis title stays only in an "About" line. */
export const PRODUCT_NAME = "Rhythm";
export const PRODUCT_SUBTITLE = "Home network overview";

export const FONT = {
  serif: '"Book Antiqua", "Palatino Linotype", Palatino, "URW Palladio L", Georgia, serif',
  sans: 'Arial, "Helvetica Neue", Helvetica, sans-serif',
};

export const C = {
  text: "#1a1a1a",
  text2: "#57524d",
  muted: "#8a837c",
  grid: "#e9e2da",
  surface: "#ffffff",
  ink: BRAND.ink,
  // devices (categorical, unchanged from v2): blue and a tan from the beige family.
  // Validated: CVD ΔE 25 (protan), contrast >= 3:1.
  phone: "#2f6fb8",
  laptop: "#a8702c",

  // Neutral sequential scale for "more / less use" (heatmaps, 24-hour strip, μ dots, likelihood
  // grid): light warm grey -> dark brown-grey, one hue (OKLCH h 62°), lightness only, L 0.775 ->
  // 0.27 in even steps. Validator (--ordinal): monotone, every gap ΔL >= 0.06, light end 2.04:1;
  // steps 2+ clear 3:1 as marks.
  intensity: ["#bcb4ae", "#a69d96", "#92877e", "#7e7268", "#6a5d51", "#57483c", "#443528", "#322315"],
  intensityWhiteFrom: 3,            // white cell text from this step on (>= 4.67:1); ink before it (>= 4.96:1)

  // The only reds: a flag that needs attention, crisis/self-harm sites, "present", the C9 signal,
  // recording. alert is 6.5:1 on white (text and marks); alertSoft is a background tint.
  alert: "#b3243a",
  alertSoft: "#fdeef0",
  // Neutral accent for a notable change (improvement), always with the "change" icon and a label.
  // Validator vs alert: CVD ΔE 10.8 (deutan), normal ΔE 21.3; 5.7:1 on white.
  change: "#4e6a7a",

  // Bands. Only the baseline period is shaded (vertical band, labelled "Baseline (usual weeks)");
  // the person's own usual range is a filled horizontal band; the typical range (other people) is
  // a dashed outline, never filled.
  baselineShade: "rgba(126,114,104,0.10)",
  usualBand: "rgba(106,93,81,0.18)",
  typicalLine: "#6a5d51",           // intensity[4], 6.4:1 on white, drawn dashed

  baseline: BRAND.beige,            // baseline phase swatch (phase strip)
  /** @deprecated use baselineShade */
  baselineBand: "rgba(126,114,104,0.10)",
  /** @deprecated use alert */
  critical: "#b3243a",
  good: "#2e7d32",
};

// Fixed device order (validated: CVD ΔE >= 8, normal >= 16, contrast >= 3:1); the legend names
// every series. A fifth device and beyond is drawn in grey rather than with a generated hue.
export const DEVICE_SERIES = [C.phone, C.laptop, "#2f8f6a", "#8a5cb8"];
export const DEVICE_OTHER = "#9a948e";

/** Colour of a device: scripted names keep phone/laptop; others follow the fixed order. */
export const deviceColor = (device: string, index = 0) =>
  device.endsWith("_laptop") ? C.laptop : device.endsWith("_phone") ? C.phone
    : DEVICE_SERIES[index] ?? DEVICE_OTHER;

export const deviceRole = (device: string) =>
  device.endsWith("_laptop") ? "laptop" : device.endsWith("_phone") ? "phone" : device;

/** Everyday names of the criteria for the person view (no clinical terms; same as the backend). */
export const AREA_NAMES: Record<string, string> = {
  C1: "Daily rhythm", C2: "Variety and social contact", C3: "Appetite-related use", C4: "Sleep",
  C5: "Restlessness", C6: "Energy", C7: "Self-related browsing", C8: "Focus", C9: "Sensitive searches",
};
