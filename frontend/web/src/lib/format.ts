export function fmtNum(v: unknown, digits = 2): string {
  if (typeof v !== "number" || !Number.isFinite(v)) return "–";
  const a = Math.abs(v);
  if (a >= 1e5) return v.toLocaleString("en-US", { notation: "compact", maximumFractionDigits: 1 });
  if (a !== 0 && a < 1e-3) return v.toExponential(1);
  if (Number.isInteger(v)) return v.toLocaleString("en-US");
  return v.toLocaleString("en-US", { maximumFractionDigits: a >= 100 ? 0 : digits });
}

export function fmtDay(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "2-digit" });
}

export function fmtTime(iso: string | null): string {
  if (!iso) return "–";
  // keep the local wall-clock time written in the ISO string (Europe/Zurich)
  const m = iso.match(/T(\d{2}:\d{2})/);
  return m ? m[1] : iso;
}

/** Minutes since local midnight of `day` for an ISO timestamp with offset (wall clock). */
export function minutesInDay(iso: string, day: string): number {
  const [d, t] = iso.split("T");
  const [hh, mm, ss] = t.slice(0, 8).split(":").map(Number);
  const base = hh * 60 + mm + (ss || 0) / 60;
  if (d < day) return 0;
  if (d > day) return 24 * 60;
  return base;
}
