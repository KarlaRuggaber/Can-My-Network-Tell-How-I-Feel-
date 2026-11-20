import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { ProfileAttention, ProfileListItem } from "../api";
import { Icon } from "./Icon";

type Props = {
  profiles: ProfileListItem[];
  value: string | undefined;
  onChange: (id: string) => void;
};

const fold = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

const needsAttention = (a?: ProfileAttention) => !!a && (a.alert || a.flags > 0);

/** People with an alert first, then by number of new flags, then in the list's own order. */
export function sortByAttention(profiles: ProfileListItem[]): ProfileListItem[] {
  const rank = (p: ProfileListItem) => (p.attention?.alert ? 1_000_000 : 0) + (p.attention?.flags ?? 0);
  return profiles.map((p, i) => ({ p, i }))
    .sort((a, b) => rank(b.p) - rank(a.p) || a.i - b.i)
    .map((x) => x.p);
}

/** Search on name, id and condition; every word of the query has to match. */
export function filterPeople(profiles: ProfileListItem[], query: string): ProfileListItem[] {
  const words = fold(query).split(/\s+/).filter(Boolean);
  if (!words.length) return profiles;
  return profiles.filter((p) => {
    const hay = fold(`${p.name} ${p.id} ${p.condition ?? ""}`);
    return words.every((w) => hay.includes(w));
  });
}

const describe = (p: ProfileListItem) =>
  `${p.scripted ? "scripted run" : "live"} · ${p.config.all_devices ? "all devices" : `${p.config.devices.length} device${p.config.devices.length === 1 ? "" : "s"}`}`;

/** Attention per person (from /api/profiles): new flags as a neutral count, crisis/self-harm sites
 *  as the red alert icon. Nothing is shown while the backend does not send `attention`. */
export function AttentionMarker({ attention }: { attention?: ProfileAttention }) {
  if (!attention) return null;
  const { flags, alert } = attention;
  if (!alert && flags <= 0) return null;
  return (
    <span className="pp-marker">
      {flags > 0 && (
        <span className="pp-flags" title={`${flags} new flag${flags === 1 ? "" : "s"} to review`}>
          {flags} new
        </span>
      )}
      {alert && (
        <span className="pp-alert" title="Crisis or self-harm sites visited">
          <Icon name="alert" label="Crisis or self-harm sites" />
        </span>
      )}
    </span>
  );
}

/** Patient selector for clinicians: one button showing the selected person; it opens a searchable
 *  list that stays usable with hundreds of people (search, arrow keys, Enter, Escape). */
export function PersonPicker({ profiles, value, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [onlyAttention, setOnlyAttention] = useState(false);
  const [active, setActive] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const uid = useId();
  const listId = `${uid}-list`;
  const optId = (i: number) => `${uid}-opt-${i}`;

  const current = profiles.find((p) => p.id === value);
  const hasAttention = profiles.some((p) => p.attention);
  const nAttention = profiles.filter((p) => needsAttention(p.attention)).length;
  const sorted = useMemo(() => sortByAttention(profiles), [profiles]);
  const shown = useMemo(() => {
    const base = onlyAttention ? sorted.filter((p) => needsAttention(p.attention)) : sorted;
    return filterPeople(base, query);
  }, [sorted, query, onlyAttention]);

  const openList = (initial = "") => {
    setQuery(initial);
    setOpen(true);
  };
  const close = (focusTrigger = true) => {
    setOpen(false);
    if (focusTrigger) triggerRef.current?.focus();
  };
  const choose = (p: ProfileListItem | undefined) => {
    if (!p) return;
    onChange(p.id);
    close();
  };

  // on open: focus the search field and start at the selected person (if visible)
  useEffect(() => {
    if (!open) return;
    inputRef.current?.focus();
    const i = shown.findIndex((p) => p.id === value);
    setActive(i >= 0 && !query ? i : 0);
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (open) setActive(0); }, [query, onlyAttention]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!open) return;
    const el = document.getElementById(optId(active));
    el?.scrollIntoView?.({ block: "nearest" });
  }, [active, open]); // eslint-disable-line react-hooks/exhaustive-deps

  // click outside closes
  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onDown);
    return () => document.removeEventListener("pointerdown", onDown);
  }, [open]);

  const onTriggerKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); openList(); return; }
    // start typing on the button: open the list with that letter as the search
    if (e.key.length === 1 && !e.metaKey && !e.ctrlKey && !e.altKey && e.key !== " ") { e.preventDefault(); openList(e.key); }
  };
  const onInputKey = (e: React.KeyboardEvent) => {
    const last = shown.length - 1;
    switch (e.key) {
      case "ArrowDown": e.preventDefault(); setActive((a) => Math.min(last, a + 1)); break;
      case "ArrowUp": e.preventDefault(); setActive((a) => Math.max(0, a - 1)); break;
      case "PageDown": e.preventDefault(); setActive((a) => Math.min(last, a + 10)); break;
      case "PageUp": e.preventDefault(); setActive((a) => Math.max(0, a - 10)); break;
      case "Enter": e.preventDefault(); choose(shown[active]); break;
      case "Escape": e.preventDefault(); e.stopPropagation(); close(); break;
    }
  };

  return (
    <div className="person-picker" ref={rootRef}
      onBlur={(e) => { if (open && !rootRef.current?.contains(e.relatedTarget as Node | null)) setOpen(false); }}>
      <span className="pp-label" id={`${uid}-label`}><Icon name="person" /> Person</span>
      <button ref={triggerRef} type="button" className="pp-trigger" aria-haspopup="listbox" aria-expanded={open}
        aria-labelledby={`${uid}-label ${uid}-current`} onClick={() => (open ? close() : openList())} onKeyDown={onTriggerKey}>
        <span id={`${uid}-current`} className="pp-current">
          <span className="pp-name">{current?.name ?? "Choose a person"}</span>
          {current && <span className="pp-sub">{describe(current)}</span>}
        </span>
        {current && <AttentionMarker attention={current.attention} />}
        <span className="pp-chevron" aria-hidden="true">▾</span>
      </button>

      {open && (
        <div className="pp-pop" role="dialog" aria-label="Choose a person">
          <input ref={inputRef} className="pp-search" type="search" role="combobox" value={query}
            onChange={(e) => setQuery(e.target.value)} onKeyDown={onInputKey}
            placeholder={`Search ${profiles.length} ${profiles.length === 1 ? "person" : "people"} by name`}
            aria-label="Search people" aria-expanded="true" aria-controls={listId} aria-autocomplete="list"
            aria-activedescendant={shown[active] ? optId(active) : undefined} />
          {hasAttention && (
            <label className="pp-filter">
              <input type="checkbox" checked={onlyAttention} onChange={(e) => setOnlyAttention(e.target.checked)} />
              Only people with new flags or alerts ({nAttention})
            </label>
          )}
          <ul ref={listRef} id={listId} className="pp-list" role="listbox" aria-label="People">
            {shown.map((p, i) => (
              <li key={p.id} id={optId(i)} role="option" aria-selected={p.id === value}
                className={`pp-option ${i === active ? "is-active" : ""} ${p.id === value ? "is-selected" : ""}`}
                onPointerMove={() => i !== active && setActive(i)}
                onMouseDown={(e) => e.preventDefault()}  // keep focus in the search field
                onClick={() => choose(p)}>
                <span className="pp-current">
                  <span className="pp-name">{p.name}</span>
                  <span className="pp-sub">{describe(p)}</span>
                </span>
                <AttentionMarker attention={p.attention} />
              </li>
            ))}
          </ul>
          {shown.length === 0 && <p className="muted small pp-empty">Nobody matches “{query}”.</p>}
          <p className="muted small pp-count" aria-live="polite">
            {shown.length === profiles.length ? `${profiles.length} people` : `${shown.length} of ${profiles.length} people`}
            {hasAttention && " · flagged people first"}
          </p>
        </div>
      )}
    </div>
  );
}
