import { useEffect, useRef, useState } from "react";
import { api } from "../api";

const MAX_SECONDS = 180;
const TYPES = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/mp4"];

const canRecord = () =>
  typeof window !== "undefined" && typeof window.MediaRecorder !== "undefined" && !!navigator.mediaDevices?.getUserMedia;

let status: Promise<number | null> | null = null;   // one check per page load: max seconds, or null if off
/** Whether dictation is available: the browser can record and the local Whisper service runs. */
export function useSpeech(): number | null {
  const [max, setMax] = useState<number | null>(null);
  useEffect(() => {
    if (!canRecord()) return;
    status ??= api.speechStatus()
      .then((s) => (s.available ? Math.min(s.max_seconds ?? MAX_SECONDS, MAX_SECONDS) : null))
      .catch(() => { status = null; return null; });
    let live = true;
    status.then((m) => { if (live) setMax(m); });
    return () => { live = false; };
  }, []);
  return max;
}

/** Add dictated words to what is already in a field. */
export const appendText = (old: string, t: string) => (old.trim() ? `${old.trimEnd()} ${t}` : t);

type Props = { onText: (text: string) => void; disabled?: boolean; inField?: boolean };

/**
 * A microphone button: records in the browser and adds the spoken words to a text field. Speech is
 * turned into text by Whisper on the study's own computer; the recording is not stored and not sent
 * to any other service. Hidden when the browser cannot record or the service is not running.
 */
export function Dictate({ onText, disabled, inField }: Props) {
  const max = useSpeech();
  const [state, setState] = useState<"idle" | "recording" | "working">("idle");
  const [secs, setSecs] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const rec = useRef<MediaRecorder | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const onTextRef = useRef(onText);
  onTextRef.current = onText;

  useEffect(() => () => {               // leaving the page stops the microphone
    window.clearInterval(timer.current);
    const r = rec.current;
    if (r && r.state !== "inactive") { r.onstop = null; r.stop(); r.stream.getTracks().forEach((t) => t.stop()); }
  }, []);
  useEffect(() => {
    if (!error) return;
    const t = window.setTimeout(() => setError(null), 8000);
    return () => window.clearTimeout(t);
  }, [error]);

  if (max === null) return null;

  const stop = () => {
    window.clearInterval(timer.current);
    if (rec.current && rec.current.state !== "inactive") rec.current.stop();
  };

  const start = async () => {
    setError(null);
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    } catch {
      setError("No access to the microphone. Allow it in the browser and try again.");
      return;
    }
    const type = TYPES.find((m) => MediaRecorder.isTypeSupported(m));
    const r = new MediaRecorder(stream, type ? { mimeType: type } : undefined);
    const chunks: Blob[] = [];
    r.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
    r.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      setState("working");
      try {
        const out = await api.transcribe(new Blob(chunks, { type: r.mimeType || type || "audio/webm" }));
        if (out.text) onTextRef.current(out.text);
        else setError("No speech was recognised. Try again a little closer to the microphone.");
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setState("idle");
      }
    };
    rec.current = r;
    r.start();
    setSecs(0);
    setState("recording");
    const t0 = Date.now();
    timer.current = window.setInterval(() => {
      const s = Math.floor((Date.now() - t0) / 1000);
      setSecs(s);
      if (s >= max) stop();
    }, 250);
  };

  const clock = `${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, "0")}`;
  return (
    <span className={`dictate${inField ? " in-field" : ""}`}>
      {error && <span className="dictate-msg" role="alert">{error}</span>}
      {state === "idle" && (
        <button type="button" className="dictate-btn" onClick={start} disabled={disabled}
          aria-label="Dictate: speak instead of typing"
          title="Speak instead of typing. The recording is turned into text on the study's own computer and is not stored.">
          <MicIcon />
        </button>
      )}
      {state === "recording" && (
        <button type="button" className="dictate-btn recording" onClick={stop} aria-label="Stop recording">
          <span className="rec-dot" aria-hidden /> {clock} <b>Stop</b>
        </button>
      )}
      {state === "working" && <span className="dictate-btn working" aria-live="polite">Writing it down…</span>}
    </span>
  );
}

function MicIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
    </svg>
  );
}
