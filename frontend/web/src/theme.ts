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

export const deviceColor = (device: string) =>
  device.endsWith("_laptop") ? C.laptop : C.phone;

export const deviceRole = (device: string) =>
  device.endsWith("_laptop") ? "laptop" : device.endsWith("_phone") ? "phone" : device;
