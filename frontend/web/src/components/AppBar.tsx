import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { ProfileListItem } from "../api";
import { Icon, type IconName } from "./Icon";
import { Logo } from "./Logo";
import { PersonPicker } from "./PersonPicker";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { PRODUCT_NAME, PRODUCT_SUBTITLE } from "../theme";

export type AppTab = { key: string; label: string; short?: string; icon?: IconName; sub: string; dot?: string;
  disabled?: string };                // greyed out and not selectable; the text says why

/** The next selectable tab from index i for an arrow / Home / End key (skips disabled tabs), or -1. */
export function nextTab(tabs: AppTab[], i: number, key: string): number {
  const ok = (j: number) => !tabs[j].disabled;
  const n = tabs.length;
  if (key === "Home" || key === "End") {
    const order = Array.from({ length: n }, (_, j) => (key === "Home" ? j : n - 1 - j));
    return order.find(ok) ?? -1;
  }
  const dir = key === "ArrowRight" ? 1 : key === "ArrowLeft" ? -1 : 0;
  if (!dir) return -1;
  for (let s = 1; s < n; s++) { const j = (i + dir * s + n) % n; if (ok(j)) return j; }
  return -1;
}

type Props = {
  username: string;
  multi: boolean;
  tabs: AppTab[] | null;              // null: no section links (settings, no profile, data not ready)
  tab: string;
  onTab: (key: string) => void;
  onHome: () => void;
  profiles: ProfileListItem[];
  pid: string | undefined;
  onPick: (id: string) => void;
  showPicker: boolean;
  settings: boolean;
  onToggleSettings: () => void;
  backLabel: string;                  // "Back to <person>" while settings are open
  myWeek: boolean;                    // person only: "My week" is always in the account menu
  onToggleMyWeek: () => void;
  onLogout: () => void;
  thesis?: string;                    // clinician view only
};

/**
 * The app bar: wordmark, section links (tabs), person picker and account menu in one sticky row
 * (a second, scrollable row for the links on narrow screens), plus one small disclaimer line.
 */
export function AppBar(p: Props) {
  const strip = useRef<HTMLDivElement>(null);
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  // narrow screens: keep the active link inside the scrollable strip
  useEffect(() => {
    const s = strip.current, el = refs.current[p.tab];
    if (!s || !el) return;
    const left = el.offsetLeft - 16;
    if (left < s.scrollLeft || el.offsetLeft + el.offsetWidth > s.scrollLeft + s.clientWidth) s.scrollLeft = Math.max(0, left);
  }, [p.tab, p.tabs]);

  const onKey = (e: React.KeyboardEvent, i: number) => {
    const tabs = p.tabs ?? [];
    const to = nextTab(tabs, i, e.key);
    if (to < 0) return;
    e.preventDefault();
    p.onTab(tabs[to].key);
    refs.current[tabs[to].key]?.focus();
  };

  const initial = (p.username.trim()[0] ?? "?").toUpperCase();
  return (
    <>
      <header className="appbar">
        <button type="button" className="appbar-brand" onClick={p.onHome} title={PRODUCT_SUBTITLE} aria-label={`${PRODUCT_NAME}, ${PRODUCT_SUBTITLE}: go to Overview`}>
          <Logo className="appbar-logo" />
        </button>

        {p.settings ? (
          <div className="appbar-nav appbar-settings">
            <button type="button" className="appbar-back" onClick={p.onToggleSettings}>
              <span aria-hidden="true">&larr;</span> {p.backLabel}
            </button>
            <span className="appbar-state" aria-current="page">Settings</span>
          </div>
        ) : p.tabs && (
          <TooltipProvider delayDuration={400}>
            <nav className="appbar-nav" aria-label="Sections">
              <div className="appbar-tabs" role="tablist" aria-label="View" ref={strip}>
                {p.tabs.map((t, i) => {
                  const active = p.tab === t.key;
                  const subId = `tabsub-${t.key}`;
                  return (
                    <Tooltip key={t.key}>
                      <TooltipTrigger asChild>
                        <button type="button" role="tab" id={`tab-${t.key}`} aria-selected={active} aria-describedby={subId}
                          tabIndex={active ? 0 : -1} className={`appbar-tab${active ? " active" : ""}${t.disabled ? " disabled" : ""}`}
                          aria-disabled={t.disabled ? true : undefined}
                          ref={(el) => { refs.current[t.key] = el; }}
                          onClick={() => { if (!t.disabled) p.onTab(t.key); }} onKeyDown={(e) => onKey(e, i)}>
                          {t.icon && <Icon name={t.icon} size={16} />}
                          <span>{t.label}</span>
                          {t.dot && <span className="tab-dot" role="img" aria-label="incomplete" title={t.dot} />}
                          <span id={subId} className="sr-only">{t.disabled ?? t.sub}</span>
                        </button>
                      </TooltipTrigger>
                      <TooltipContent side="bottom" sideOffset={6}>{t.disabled ?? t.sub}</TooltipContent>
                    </Tooltip>
                  );
                })}
              </div>
            </nav>
          </TooltipProvider>
        )}

        {p.showPicker && !p.settings && (
          <div className="appbar-picker">
            <PersonPicker profiles={p.profiles} value={p.pid} onChange={p.onPick} />
          </div>
        )}

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button type="button" className="appbar-account" aria-label={`Account menu, signed in as ${p.username}`}>
              <span className="appbar-avatar" aria-hidden="true">{initial}</span>
              <span className="appbar-username">{p.username}</span>
              <span className="appbar-caret" aria-hidden="true">&#9662;</span>
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="appbar-menu w-auto min-w-44">
            {p.multi && <DropdownMenuItem onSelect={p.onToggleSettings}>{p.settings ? "Close settings" : "Settings"}</DropdownMenuItem>}
            {!p.multi && <DropdownMenuItem onSelect={p.onToggleMyWeek}>{p.myWeek ? "Close My week" : "My week"}</DropdownMenuItem>}
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={p.onLogout}>Log out</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </header>
      {p.tabs && !p.settings && <TabBar tabs={p.tabs} tab={p.tab} onTab={p.onTab} />}
      <p className="appbar-note">
        {PRODUCT_SUBTITLE} | Research prototype, not a diagnostic tool.
        {p.thesis && <> <span className="about-line">About: {p.thesis}.</span></>}
      </p>
    </>
  );
}

/**
 * Phones: the sections as a floating glass tab bar at the bottom of the screen (iOS tab bar
 * pattern: icon above a short label, the selected tab on a sliding lens). Shown only below 640px
 * (CSS); the top strip is hidden there, so only one tab list is ever in the accessibility tree.
 * Rendered into <body>: the page gets a transform while it glides and is a layout container, and
 * either would pin a fixed bar to the page instead of the screen.
 */
export function TabBar({ tabs, tab, onTab }: { tabs: AppTab[]; tab: string; onTab: (key: string) => void }) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const bar = useRef<HTMLElement>(null);
  const index = Math.max(0, tabs.findIndex((t) => t.key === tab));
  // Icons only as soon as one label would be cut off: all labels go, never some. The labels stay in
  // the DOM (visually hidden) as the tabs' names and to measure their natural width.
  const [iconsOnly, setIconsOnly] = useState(false);
  useLayoutEffect(() => {
    const el = bar.current;
    if (!el) return;
    const check = () => {
      const tabEls = Array.from(el.querySelectorAll<HTMLElement>(".tabbar-tab"));
      if (!tabEls.length || !tabEls[0].clientWidth) return;            // hidden (desktop) or not laid out
      const fits = tabEls.every((t) => {
        const label = t.querySelector<HTMLElement>(".tabbar-label");
        return !label || label.scrollWidth <= t.clientWidth - 6;
      });
      setIconsOnly(!fits);
    };
    check();
    const ro = new ResizeObserver(check);
    ro.observe(el);
    document.fonts?.ready.then(check).catch(() => undefined);
    return () => ro.disconnect();
  }, [tabs]);
  const onKey = (e: React.KeyboardEvent, i: number) => {
    const to = nextTab(tabs, i, e.key);
    if (to < 0) return;
    e.preventDefault();
    onTab(tabs[to].key);
    refs.current[tabs[to].key]?.focus();
  };
  return createPortal(
    <nav ref={bar} className={`tabbar${iconsOnly ? " icons-only" : ""}`} aria-label="Sections" style={{ "--tabs": tabs.length, "--tab-i": index } as React.CSSProperties}>
      <span className="tabbar-lens" aria-hidden="true" />
      <div className="tabbar-tabs" role="tablist" aria-label="View">
        {tabs.map((t, i) => {
          const active = t.key === tab;
          return (
            <button key={t.key} type="button" role="tab" aria-selected={active} tabIndex={active ? 0 : -1}
              aria-label={t.short && t.short !== t.label ? t.label : undefined}
              aria-disabled={t.disabled ? true : undefined} title={t.disabled}
              className={`tabbar-tab${active ? " active" : ""}${t.disabled ? " disabled" : ""}`} ref={(el) => { refs.current[t.key] = el; }}
              onClick={() => { if (!t.disabled) onTab(t.key); }} onKeyDown={(e) => onKey(e, i)}>
              <span className="tabbar-icon">
                {t.icon && <Icon name={t.icon} size={22} />}
                {t.dot && <span className="tabbar-dot" role="img" aria-label="incomplete" title={t.dot} />}
              </span>
              <span className="tabbar-label">{t.short ?? t.label}</span>
            </button>
          );
        })}
      </div>
    </nav>,
    document.body,
  );
}
