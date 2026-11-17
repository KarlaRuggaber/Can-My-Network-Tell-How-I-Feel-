import { useEffect, useState } from "react";
import { api, type AssistantStatus } from "../api";

/** Multi-profile users: turn the explanation assistant on, choose the Claude model, enter the Claude API key. */
export function AssistantSettings() {
  const [st, setSt] = useState<AssistantStatus | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [model, setModel] = useState("");
  const [key, setKey] = useState("");
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  const apply = (s: AssistantStatus) => {
    setSt(s); setEnabled(s.enabled || false); setModel(s.model ?? "");
  };
  useEffect(() => { api.assistant().then(apply).catch(() => setSt(null)); }, []);

  const save = async (removeKey = false) => {
    try {
      const s = await api.saveAssistant({ enabled, model, api_key: removeKey ? "" : key || null });
      apply(s); setKey("");
      setMsg({ kind: "ok", text: removeKey ? "Key removed." : s.has_key ? "Saved." : "Saved, but there is no API key yet." });
    } catch (e) {
      setMsg({ kind: "error", text: String((e as Error).message) });
    }
  };

  if (!st?.default_model) return null;
  return (
    <section className="card">
      <div className="card-head">
        <h2>Assistant</h2>
        <p className="sub">The assistant explains the results in natural language and helps fill in the onboarding and the
          care plan. Questions and the profile's daily results (no raw traffic, addresses or device names) are sent to
          Anthropic's Claude.</p>
      </div>
      {msg && <p className={msg.kind === "error" ? "error" : "notice"}>{msg.text}</p>}
      <div className="editor">
        <label className="radio"><input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
          Turn the assistant on for everyone who can see a profile</label>
        <div className="form-grid">
          <label className="field">Claude model
            <input value={model} onChange={(e) => setModel(e.target.value)} placeholder={st.default_model} />
          </label>
          <label className="field">Claude API key {st.has_key ? <span className="pill pill-beige">stored</span> : null}
            <input type="password" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)}
              placeholder={st.has_key ? "leave empty to keep the stored key" : "sk-ant-…"} />
          </label>
        </div>
        <p className="muted small">The key is stored on this computer only (<code>~/cmn-data/frontend/assistant.json</code>, readable by
          your user account) and is never shown again in the browser.</p>
        <div className="row-actions">
          <button className="btn btn-primary" onClick={() => save()} disabled={!model.trim()}>Save</button>
          {model !== st.default_model && <button className="btn btn-quiet" onClick={() => setModel(st.default_model!)}>Use the default model</button>}
          {st.has_key && <button className="btn btn-quiet" onClick={() => save(true)}>Remove key</button>}
        </div>
      </div>
    </section>
  );
}
