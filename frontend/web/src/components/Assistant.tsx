import { useEffect, useRef, useState } from "react";
import { api, type AssistantStatus, type ChatTurn } from "../api";
import { Markdown } from "./Markdown";

type Props = {
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

/** Explanation layer: natural-language questions about the results shown, answered from the data. */
export function Assistant({ profileId, person, focus }: Props) {
  const [status, setStatus] = useState<AssistantStatus | null>(null);
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { api.assistant().then(setStatus).catch(() => setStatus(null)); }, []);
  useEffect(() => { setTurns([]); setError(null); }, [profileId]);
  useEffect(() => { endRef.current?.scrollIntoView({ block: "nearest" }); }, [turns]);

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

  return (
    <section className="card assistant">
      <div className="card-head">
        <h2>{person ? "Questions about your results" : <><span className="step">?</span>Ask about these results</>}</h2>
        <p className="sub">
          {person
            ? "Ask in your own words where a result comes from. The assistant only explains the numbers shown here; it does not diagnose."
            : "Natural-language explanations of the computed results (metrics, μ, weights, gate). It only uses this profile's data; no diagnosis."}
        </p>
      </div>

      {status && !status.enabled && (
        <p className="muted">
          {person ? "The assistant is not available at the moment."
            : <>The assistant is turned off. Turn it on and enter an API key under <b>Settings → Assistant</b>.</>}
        </p>
      )}

      {status?.enabled && (
        <>
          {turns.length === 0 && (
            <div className="chips suggestions">
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
          <form className="ask" onSubmit={(e) => { e.preventDefault(); send(input); }}>
            <input value={input} onChange={(e) => setInput(e.target.value)} disabled={busy}
              placeholder={person ? "e.g. Why was last Tuesday different?" : "e.g. Which metric made C4 reach θ on 31/10?"}
              aria-label="Your question" />
            <button className="btn btn-primary" type="submit" disabled={busy || !input.trim()}>{busy ? "…" : "Ask"}</button>
            {turns.length > 0 && <button type="button" className="btn btn-quiet" onClick={() => setTurns([])} disabled={busy}>New conversation</button>}
          </form>
          <p className="muted small">{status.notice}{focus && !person ? ` The current view (${focus}) is sent along.` : ""}</p>
        </>
      )}
    </section>
  );
}
