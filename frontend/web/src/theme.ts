// Chart colors (validated reference palette of the dataviz method, light mode).
export const C = {
  text: "#0b0b0b",
  text2: "#52514e",
  muted: "#8a8984",
  grid: "#e6e5e1",
  surface: "#fcfcfb",
  phone: "#2a78d6",      // categorical slot 1
  laptop: "#eb6834",     // categorical slot 2
  baselineBand: "rgba(82,81,78,0.10)",
  clinicalTint: "rgba(235,104,52,0.07)",
  critical: "#e34948",   // status: criterion present / episode
  warning: "#eda100",
  good: "#008300",
  // sequential blue, near-zero recedes to the surface
  seq: ["#f4f8fd", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"],
};

export const deviceColor = (device: string) =>
  device.endsWith("_laptop") ? C.laptop : C.phone;

export const deviceRole = (device: string) =>
  device.endsWith("_laptop") ? "laptop" : device.endsWith("_phone") ? "phone" : device;
