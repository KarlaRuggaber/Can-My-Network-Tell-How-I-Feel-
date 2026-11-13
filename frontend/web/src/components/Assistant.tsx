import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api, type AssistantStatus, type ChatTurn } from "../api";
import { Markdown } from "./Markdown";

type Props = {
  open: boolean;
  onToggle: (open: boolean) => void;
  profileId: string;
  person: boolean;               // the person themself: everyday language, no clinical terms
  focus: string | null;          // what the screen shows now (day / criterion), sent with the question
};

const SUGGEST_PERSON = [
  "What does this page show?",
  "Why is one of my areas marked as different?",
  "Which of my days were most unusual, and why?",
  "How is “usual” worked out?",
];
const SUGGEST_CLINICIAN = [
  "Which metrics drive the likelihoods in the recent period?",
  "Why is this criterion present or absent?",
  "Explain the selected day's scores.",
  "How does the recent period differ from the baseline?",
];

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
export function Assistant({ open, onToggle, profileId, person, focus }: Props) {
  const [status, setStatus] = useState<AssistantStatus | null>(null);
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
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
  useEffect(() => { setTurns([]); setError(null); }, [profileId]);
  useEffect(() => { endRef.current?.scrollIntoView({ block: "nearest" }); }, [turns, open]);
  useEffect(() => {   // Escape closes the panel
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onToggle(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onToggle]);

  const send = async (q: string) => {
    const question = q.trim();
    if (!question || busy) return;
    const history: ChatTurn[] = [...turns, { role: "user", content: question }];
    setTurns([...history, { role: "assistant", content: "" }]);
    setInput(""); setBusy(true); setError(null);
    try {
      await api.ask(profileId, history, focus, (t) =>
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

  if (person && status && !status.enabled) return null;   // nothing to offer the person

  // Panel and tab stay mounted so opening and closing can slide; the closed panel is inert.
  // Rendered into <body>: the page gets a transform while it glides, and a transformed ancestor
  // would make this fixed panel position itself against the page instead of the window.
  return createPortal(
    <>
      <button className={`assistant-tab ${open ? "is-hidden" : ""}`} onClick={() => onToggle(true)}
        aria-expanded={open} aria-controls="assistant-panel" tabIndex={open ? -1 : 0}>
        <span className="assistant-tab-icon" aria-hidden="true">?</span>
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
          <div className="suggestions">
            {(person ? SUGGEST_PERSON : SUGGEST_CLINICIAN).map((s) => (
              <button key={s} className="pill pill-outline suggestion" onClick={() => send(s)} disabled={busy}>{s}</button>
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
            <button className="btn btn-primary" type="submit" disabled={busy || !input.trim()}>{busy ? "…" : "Ask"}</button>
          </form>
          <div className="row-between">
            <p className="muted small">{status.notice}{focus && !person ? ` The current view (${focus}) is sent along.` : ""}</p>
            {turns.length > 0 && <button type="button" className="btn btn-quiet small" onClick={() => setTurns([])} disabled={busy}>New conversation</button>}
          </div>
        </div>
      )}
    </aside>
    </>,
    document.body,
  );
}
