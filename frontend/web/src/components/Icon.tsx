import type { ReactNode } from "react";

// Line icons on a 24px grid, 1.75 stroke, round caps, drawn in currentColor. Each name has one
// fixed meaning (frontend/VISUAL.md); "alert" is the only red icon. Always pair an icon with a
// visible text label or pass `label` (becomes the accessible name and the tooltip).

export const ICON_MEANING = {
  moon: "Night / quiet window",
  sunrise: "Back online in the morning",
  clock: "Time in use",
  "night-use": "Use at night",
  chat: "Chat",
  globe: "Different sites",
  alert: "Crisis / self-harm sites, needs attention",
  irregular: "Irregular nights",
  change: "Notable change",
  note: "Note",
  explain: "Explain",
  away: "Away",
  phone: "Phone",
  laptop: "Laptop",
  person: "Person",
  data: "Data",
  lock: "Private / protected",
  days: "Timeline, day by day",
  show: "Show (e.g. the charts)",
  hide: "Hide (e.g. the charts)",
  home: "Back to the overview",
} as const;

export type IconName = keyof typeof ICON_MEANING;
export const ICON_NAMES = Object.keys(ICON_MEANING) as IconName[];

const dot = (cx: number, cy: number, r = 1) => <circle cx={cx} cy={cy} r={r} fill="currentColor" stroke="none" />;

const MOON = "M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z";

const PATHS: Record<IconName, ReactNode> = {
  moon: <path d={MOON} />,
  sunrise: <>
    <path d="M3 19h18M7 19a5 5 0 0 1 10 0" />
    <path d="M12 5v4M5.6 10.6 7 12M18.4 10.6 17 12M2.5 15h2M19.5 15h2" />
  </>,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  "night-use": <><path transform="translate(0 3) scale(0.82)" strokeWidth={2.13} d={MOON} />{dot(19.5, 5.5, 2)}</>,
  chat: <path d="M4 5h16v11H9.5L5 20v-4H4z" />,
  globe: <><circle cx="12" cy="12" r="9" /><ellipse cx="12" cy="12" rx="4" ry="9" /><path d="M3 12h18" /></>,
  alert: <><path d="M12 3.5 2.5 20h19z" /><path d="M12 10v4.5" />{dot(12, 17.2)}</>,
  irregular: <path d="M2.5 13 6 7l3 10 3-12 3 10 3-7 3.5 5" />,
  change: <path d="M5 19 19 5M10 5h9v9" />,
  note: <path d="M4 20l1-4.5L16.3 4.2a2 2 0 0 1 2.9 0l.6.6a2 2 0 0 1 0 2.9L8.5 19zM14 6.5l3.5 3.5" />,
  explain: <><circle cx="12" cy="12" r="9" /><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .8-1 1.5v.6" />{dot(12, 16.8)}</>,
  away: <><rect x="3" y="7" width="18" height="13" rx="2" /><path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2M3 12.5h18" /></>,
  phone: <><rect x="7" y="2.5" width="10" height="19" rx="2" /><path d="M11 18.5h2" /></>,
  laptop: <><rect x="5" y="5" width="14" height="10" rx="1" /><path d="M2.5 19h19M5 15l-2.5 4M19 15l2.5 4" /></>,
  person: <><circle cx="12" cy="8" r="3.5" /><path d="M5 20a7 7 0 0 1 14 0" /></>,
  data: <path d="M4 20h16M7 16v-4M12 16V7M17 16V9" />,
  lock: <><rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V8a4 4 0 0 1 8 0v3" /></>,
  days: <><rect x="3.5" y="5" width="17" height="15" rx="2" /><path d="M3.5 10h17M8 3v4M16 3v4" />{dot(8, 14)}{dot(12, 14)}{dot(16, 14)}</>,
  show: <><path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" /><circle cx="12" cy="12" r="3" /></>,
  hide: <><path d="M9.9 5.8A9 9 0 0 1 12 5.5c6 0 9.5 6.5 9.5 6.5a16 16 0 0 1-2.6 3.4M6.6 6.9C4 8.6 2.5 12 2.5 12S6 18.5 12 18.5c1.8 0 3.3-.5 4.6-1.3" /><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2M3 3l18 18" /></>,
  home: <><path d="M3.5 11 12 4l8.5 7" /><path d="M5.5 9.5V20h4.5v-5.5h4V20h4.5V9.5" /></>,
};

export interface IconProps {
  name: IconName;
  /** Accessible name and tooltip. Leave out only when a visible text label sits next to the icon. */
  label?: string;
  size?: number;
  className?: string;
}

export function Icon({ name, label, size = 18, className }: IconProps) {
  const tone = name === "alert" ? " icon-alert" : name === "change" ? " icon-change" : "";
  const a11y = label ? { role: "img", "aria-label": label } : { "aria-hidden": true as const };
  return (
    <svg className={`icon icon-${name}${tone}${className ? " " + className : ""}`} width={size} height={size}
      viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round"
      strokeLinejoin="round" focusable="false" {...a11y}>
      {label && <title>{label}</title>}
      {PATHS[name]}
    </svg>
  );
}

export default Icon;
