import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api, type AssistantStatus, type ChatTurn } from "../api";
import { Markdown } from "./Markdown";
import { appendText, Dictate } from "./Dictate";
import { Icon } from "./Icon";
import { fmtDay } from "../lib/format";

/** A question asked from elsewhere on the page ("explain this value"), sent once per id. */
export type AskRequest = { id: number; question: string; focus?: string | null };

type Props = {
  request?: AskRequest | null;
  open: boolean;
  onToggle: (open: boolean) => void;
  profileId: string;
  person: boolean;               // the person themself: everyday language, no clinical terms
  focus: string | null;          // what the screen shows now (day / criterion), sent with the question
  focusInfo?: FocusInfo;         // the same, structured: drives the follow-up suggestions
};

/** What the screen is focused on, for follow-up suggestions under an answer. */
export type FocusInfo = { day?: string | null; criterion?: { key: string; name: string } | null; flag?: string | null };

/** The follow-up messages of the controls under an answer; the backend prompt handles exactly these. */
export const SHORTER = "Shorter";
export const MORE_DETAIL = "More detail";

const SUGGEST_PERSON = [
  "What does this page show?",
  "Which days stood out?",
  "How is “usual” worked out?",
];
const SUGGEST_CLINICIAN = [
  "What drives the recent likelihoods?",
  "Recent period vs. baseline?",
  "Why is this criterion present or absent?",
];

/** 2–3 short follow-up questions from the current focus: flag first, then day, then criterion. */
export function followUps(person: boolean, f: FocusInfo = {}): string[] {
  const out: string[] = [];
  const day = f.day ? fmtDay(f.day) : null;
  if (f.flag) out.push(person ? "Has this happened before?" : "Has this flag come up before?");
  if (day) out.push(person ? `How did ${day} compare with my usual days?` : `What else stood out on ${day}?`);
  if (f.criterion && !person) {
    out.push(`Which metric drives ${f.criterion.key} most?`);
    out.push(`How reliable is ${f.criterion.key} from network data?`);
  }
  out.push(person ? "What changed compared with my usual weeks?" : "Recent period vs. baseline?");
  if (!f.flag && !day) out.push(person ? "Which days stood out?" : "Which flags need a look first?");
  return [...new Set(out)].slice(0, 3);
}

/** The flag an "Explain" button asked about (its focus is "flag <id>"), if any. */
const flagOf = (focus: string | null | undefined) => focus?.match(/^flag (\S+)/)?.[1] ?? null;

const DEFAULT_W = 420;
const MIN_W = 320;
const WIDTH_KEY = "cmn.assistantWidth";
const maxW = () => Math.max(MIN_W, Math.min(900, Math.round(window.innerWidth * 0.7)));
const clampW = (w: number) => Math.round(Math.min(maxW(), Math.max(MIN_W, w)));

/** Panel width lives in a CSS variable, so the page margin and the panel follow it together. */
function applyWidth(w: number) {
  document.documentElement.style.setProperty("--drawer-user-w", `${w}px`);
}
function storedWidth(): number {
  try { const v = Number(window.localStorage.getItem(WIDTH_KEY)); return v ? clampW(v) : DEFAULT_W; } catch { return DEFAULT_W; }
}

/** Explanation layer: natural-language questions about the results shown, answered from the data. */
export function Assistant({ request, open, onToggle, profileId, person, focus, focusInfo }: Props) {
  const [status, setStatus] = useState<AssistantStatus | null>(null);
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [askedFlag, setAskedFlag] = useState<string | null>(null);   // flag of the last "Explain"
  const endRef = useRef<HTMLDivElement>(null);
  const widthRef = useRef(storedWidth());

  const setWidth = useCallback((w: number, save = true) => {
    widthRef.current = clampW(w);
    applyWidth(widthRef.current);
    if (save) { try { window.localStorage.setItem(WIDTH_KEY, String(widthRef.current)); } catch { /* convenience only */ } }
  }, []);
  useEffect(() => { applyWidth(widthRef.current); }, []);

  // Drag the left edge: no transitions while dragging, width follows the pointer.
  const startResize = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    e.preventDefault();
    const handle = e.currentTarget;
    handle.setPointerCapture(e.pointerId);
    document.documentElement.classList.add("drawer-resizing");
    const move = (ev: PointerEvent) => setWidth(window.innerWidth - ev.clientX, false);
    const up = () => {
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", up);
      handle.removeEventListener("pointercancel", up);
      document.documentElement.classList.remove("drawer-resizing");
      setWidth(widthRef.current);
      window.dispatchEvent(new Event("resize"));
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", up);
    handle.addEventListener("pointercancel", up);
  };
  const keyResize = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowLeft") { e.preventDefault(); setWidth(widthRef.current + 24); }
    if (e.key === "ArrowRight") { e.preventDefault(); setWidth(widthRef.current - 24); }
  };

  useEffect(() => { api.assistant().then(setStatus).catch(() => setStatus(null)); }, []);
  useEffect(() => { setTurns([]); setError(null); setAskedFlag(null); }, [profileId]);
  useEffect(() => { endRef.current?.scrollIntoView?.({ block: "nearest" }); }, [turns, open]);
  useEffect(() => {   // Escape closes the panel
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onToggle(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onToggle]);

  const send = async (q: string, f: string | null = focus) => {
    const question = q.trim();
    if (!question || busy) return;
    const history: ChatTurn[] = [...turns, { role: "user", content: question }];
    setTurns([...history, { role: "assistant", content: "" }]);
    setInput(""); setBusy(true); setError(null);
    try {
      await api.ask(profileId, history, f, (t) =>
        setTurns((cur) => {
          const next = cur.slice();
          const last = next[next.length - 1];
          next[next.length - 1] = { ...last, content: last.content + t };
          return next;
        }));
    } catch (e) {
      setError(String((e as Error).message));
      setTurns(history.slice(0, -1));
      setInput(question);
    } finally {
      setBusy(false);
    }
  };

  // "Explain this" from elsewhere: open the panel and send the question once
  const lastRequest = useRef<number | null>(null);
  useEffect(() => {
    if (!request || request.id === lastRequest.current || status === null) return;
    lastRequest.current = request.id;
    setAskedFlag(flagOf(request.focus));
    onToggle(true);
    if (status.enabled) send(request.question, request.focus ?? focus);
  }, [request, status]); // eslint-disable-line react-hooks/exhaustive-deps

  if (person && status && !status.enabled) return null;   // nothing to offer the person (after all hooks)

  // Panel and tab stay mounted so opening and closing can slide; the closed panel is inert.
  // Rendered into <body>: the page gets a transform while it glides, and a transformed ancestor
  // would make this fixed panel position itself against the page instead of the window.
  return createPortal(
    <>
      <button className={`assistant-tab ${open ? "is-hidden" : ""}`} onClick={() => onToggle(true)}
        aria-expanded={open} aria-controls="assistant-panel" tabIndex={open ? -1 : 0}>
        <span className="assistant-tab-icon" aria-hidden="true"><Icon name="explain" /></span>
        <span>{person ? "Questions" : "Assistant"}</span>
      </button>
    <aside id="assistant-panel" className={`assistant-drawer ${open ? "is-open" : ""}`} aria-label="Assistant"
      aria-hidden={!open} {...(!open ? { inert: "" } : {})}>
      <div className="drawer-resize" role="separator" aria-orientation="vertical" aria-label="Resize the assistant panel"
        tabIndex={open ? 0 : -1} onPointerDown={startResize} onKeyDown={keyResize}
        onDoubleClick={() => setWidth(DEFAULT_W)} title="Drag to resize · double-click to reset" />
      <div className="drawer-head">
        <div>
          <h2>{person ? "Questions about your results" : "Ask about these results"}</h2>
          <p className="sub">
            {person
              ? "Ask in your own words where a result comes from. The assistant only explains what is shown; it does not diagnose."
              : "Explanations of the computed results (metrics, μ, weights, gate) from this profile's data only. No diagnosis."}
          </p>
        </div>
        <button className="drawer-close" onClick={() => onToggle(false)} aria-label="Close the assistant" title="Close">×</button>
      </div>

      <div className="drawer-body">
        {status && !status.enabled && (
          <p className="muted">The assistant is turned off. Turn it on and enter an API key under <b>Settings → Assistant</b>.</p>
        )}
        {status?.enabled && turns.length === 0 && (
          <div className="suggestions" role="group" aria-label="Suggested questions">
            {(person ? SUGGEST_PERSON : SUGGEST_CLINICIAN).map((s) => (
              <button key={s} type="button" className="suggestion" onClick={() => send(s)} disabled={busy}>{s}</button>
            ))}
          </div>
        )}
        {turns.length > 0 && (
          <div className="chat" aria-live="polite">
            {turns.map((t, i) => (
              <div key={i} className={`bubble bubble-${t.role}`}>
                {t.content
                  ? (t.role === "assistant" ? <Markdown text={t.content} /> : t.content)
                  : (busy && i === turns.length - 1 ? <span className="muted">Thinking… (this can take up to half a minute)</span> : null)}
              </div>
            ))}
            {/* controls under the latest answer: "Shorter" / "More detail" refer to the answer just given */}
            {!busy && turns[turns.length - 1]?.role === "assistant" && turns[turns.length - 1].content && (
              <div className="answer-controls">
                <div className="answer-length" role="group" aria-label="Answer length">
                  <button type="button" className="btn btn-quiet small" onClick={() => send(SHORTER)}
                    aria-label="Make this answer shorter" title="Make this answer shorter">
                    <span aria-hidden="true">−</span> Shorter
                  </button>
                  <button type="button" className="btn btn-quiet small" onClick={() => send(MORE_DETAIL)}
                    aria-label="Explain this answer in more detail" title="Explain this answer in more detail">
                    <span aria-hidden="true">+</span> More detail
                  </button>
                </div>
                <div className="suggestions" role="group" aria-label="Follow-up questions">
                  {followUps(person, { ...focusInfo, flag: askedFlag ?? focusInfo?.flag }).map((s) => (
                    <button key={s} type="button" className="suggestion" onClick={() => send(s)}>{s}</button>
                  ))}
                </div>
              </div>
            )}
            <div ref={endRef} />
          </div>
        )}
        {error && <p className="error">{error}</p>}
      </div>

      {status?.enabled && (
        <div className="drawer-foot">
          <form className="ask" onSubmit={(e) => { e.preventDefault(); send(input); }}>
            <input value={input} onChange={(e) => setInput(e.target.value)} disabled={busy}
              placeholder={person ? "e.g. Why was last Tuesday different?" : "e.g. Which metric made C4 reach θ on 31/10?"}
              aria-label="Your question" />
            <Dictate disabled={busy} onText={(t) => setInput((old) => appendText(old, t))} />
            <button className="btn btn-primary" type="submit" disabled={busy || !input.trim()}>{busy ? "…" : "Ask"}</button>
          </form>
          <div className="row-between">
            <p className="muted small">{status.notice}{focus && !person ? ` The current view (${focus}) is sent along.` : ""}</p>
            {turns.length > 0 && <button type="button" className="btn btn-quiet small" onClick={() => { setTurns([]); setAskedFlag(null); }} disabled={busy}>New conversation</button>}
          </div>
        </div>
      )}
    </aside>
    </>,
    document.body,
  );
}
