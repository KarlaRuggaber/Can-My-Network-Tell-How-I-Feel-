import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

/**
 * Where am I on this page: a thin rail on the left edge with one dot per block (the page's cards
 * with a heading, or any element with data-rail="<title>"), placed at the block's real position in
 * the page, plus a marker for the part of the page on screen. Hover or focus a dot for its title;
 * click to jump there. Hidden on phones and when a page has fewer than two blocks.
 */
type Block = { el: HTMLElement; title: string; at: number };   // at: 0..1, top of the block in the page

const RAIL_SELECTOR = ".page section.card, .page [data-rail]";
const MIN_GAP = 0.035;   // dots never closer than this share of the rail

/** The block's title: data-rail, else its first heading without step numbers ("1DSM-5" -> "DSM-5"). */
export function blockTitle(el: HTMLElement): string | null {
  if (el.dataset.rail) return el.dataset.rail;
  const h = el.querySelector<HTMLElement>("h2, h3");
  if (!h) return null;
  const clone = h.cloneNode(true) as HTMLElement;
  clone.querySelectorAll(".sr-only, .step, .num, svg, [aria-hidden='true']").forEach((n) => n.remove());
  const text = (clone.textContent ?? "").replace(/\s+/g, " ").trim().replace(/^\d+\s*/, "");
  return text || null;
}

/** Positions 0..1 of the block tops, pushed apart so dots never overlap. */
export function spread(at: number[], gap = MIN_GAP): number[] {
  const out = at.slice();
  for (let i = 1; i < out.length; i++) out[i] = Math.max(out[i], out[i - 1] + gap);
  const over = out.length ? out[out.length - 1] - 1 : 0;
  if (over > 0) for (let i = out.length - 1; i >= 0; i--) out[i] = Math.min(out[i], 1 - gap * (out.length - 1 - i));
  return out.map((v) => Math.max(0, v));
}

function collect(): Block[] {
  const doc = document.documentElement.scrollHeight || 1;
  const seen = new Set<HTMLElement>();
  const blocks: Block[] = [];
  document.querySelectorAll<HTMLElement>(RAIL_SELECTOR).forEach((el) => {
    if (seen.has(el) || el.parentElement?.closest(".card")) return;   // top-level blocks only
    seen.add(el);
    const title = blockTitle(el);
    if (!title || !el.offsetHeight) return;
    blocks.push({ el, title, at: Math.min(1, (el.getBoundingClientRect().top + window.scrollY) / doc) });
  });
  return blocks.sort((a, b) => a.at - b.at);
}

export function ScrollRail({ watch }: { watch: string }) {
  const [blocks, setBlocks] = useState<Block[]>([]);
  const [view, setView] = useState({ top: 0, size: 1 });   // the screen's share of the page, 0..1
  const [active, setActive] = useState(-1);
  const frame = useRef(0);

  const measure = useCallback(() => {
    const doc = document.documentElement.scrollHeight || 1;
    const b = collect();
    setBlocks((old) => (old.length === b.length && old.every((o, i) => o.el === b[i].el && o.title === b[i].title && Math.abs(o.at - b[i].at) < 0.002) ? old : b));
    setView({ top: window.scrollY / doc, size: Math.min(1, window.innerHeight / doc) });
    // the active block: the last one whose top is above a third of the screen
    const line = window.innerHeight / 3;
    let a = -1;
    b.forEach((x, i) => { if (x.el.getBoundingClientRect().top <= line) a = i; });
    if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2) a = b.length - 1;   // at the bottom
    setActive(a < 0 && b.length ? 0 : a);
  }, []);

  useEffect(() => {
    const schedule = () => { cancelAnimationFrame(frame.current); frame.current = requestAnimationFrame(measure); };
    schedule();
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    const ro = new ResizeObserver(schedule);           // charts and lists change the page height after load
    ro.observe(document.body);
    const mo = new MutationObserver(schedule);
    const page = document.querySelector(".page");
    if (page) mo.observe(page, { childList: true, subtree: true });
    return () => {
      cancelAnimationFrame(frame.current);
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
      ro.disconnect(); mo.disconnect();
    };
  }, [measure, watch]);

  if (blocks.length < 2) return null;
  const pos = spread(blocks.map((b) => b.at));
  const go = (el: HTMLElement) => {
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    el.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
  };
  return createPortal(
    <nav className="scroll-rail" aria-label="Sections on this page">
      <span className="scroll-rail-line" aria-hidden="true" />
      <span className="scroll-rail-view" aria-hidden="true"
        style={{ top: `${view.top * 100}%`, height: `${Math.max(view.size * 100, 4)}%` }} />
      <ol>
        {blocks.map((b, i) => (
          <li key={i} style={{ top: `${pos[i] * 100}%` }}>
            <button type="button" className={`scroll-rail-dot${i === active ? " active" : ""}${i < active ? " passed" : ""}`}
              aria-current={i === active ? "location" : undefined} aria-label={`Go to ${b.title}`} onClick={() => go(b.el)}>
              <span className="scroll-rail-label" aria-hidden="true">{b.title}</span>
            </button>
          </li>
        ))}
      </ol>
    </nav>,
    document.body,
  );
}
