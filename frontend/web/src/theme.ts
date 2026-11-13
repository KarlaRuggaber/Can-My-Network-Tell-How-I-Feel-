// Look of the midterm presentation: Book Antiqua titles, Arial text, red #DC3A4F and beige #EBD6C1,
// thin black outlines. Data colors checked with the dataviz palette validator (light mode).
export const BRAND = { red: "#DC3A4F", beige: "#EBD6C1", ink: "#262626" };

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
  // devices (categorical): blue and a tan from the beige family; brand red stays free for
  // "clinical" and "present". Validated: CVD ΔE 25 (protan), contrast >= 3:1.
  phone: "#2f6fb8",
  laptop: "#a8702c",
  clinical: BRAND.red,              // clinical phase (strip, shading, Gantt)
  baseline: BRAND.beige,            // baseline phase (strip)
  baselineBand: "rgba(168,112,44,0.12)",
  clinicalTint: "rgba(220,58,79,0.07)",
  critical: "#b3243a",              // status: present / episode (text 6.5:1 on white)
  good: "#2e7d32",
  // sequential, light beige -> beige -> brand red -> dark red (OKLab, lightness monotonic)
  seq: ["#faf6f2", "#f3e7db", "#ecd8c3", "#ecab9d", "#e77976", "#dd3d50", "#ad283b", "#7e1527"],
  seqWhiteFrom: 5,                  // white cell text from this step on (contrast >= 4.3)
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
