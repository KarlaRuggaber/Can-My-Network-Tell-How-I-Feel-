import { useEffect, useState } from "react";
import { api, type AssistantStatus } from "../api";

/** Multi-profile users: turn the explanation assistant on, choose provider and model, enter the API key. */
export function AssistantSettings() {
  const [st, setSt] = useState<AssistantStatus | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [provider, setProvider] = useState("openrouter");
  const [model, setModel] = useState("");
  const [key, setKey] = useState("");
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  const apply = (s: AssistantStatus) => {
    setSt(s); setEnabled(s.enabled || false); setProvider(s.provider ?? "openrouter"); setModel(s.model ?? "");
  };
  useEffect(() => { api.assistant().then(apply).catch(() => setSt(null)); }, []);

  const save = async (removeKey = false) => {
    try {
      const s = await api.saveAssistant({ enabled, provider, model, api_key: removeKey ? "" : key || null });
      apply(s); setKey("");
      setMsg({ kind: "ok", text: removeKey ? "Key removed." : s.has_key ? "Saved." : "Saved, but there is no API key yet." });
    } catch (e) {
      setMsg({ kind: "error", text: String((e as Error).message) });
    }
  };

  if (!st?.providers) return null;
  return (
    <section className="card">
      <div className="card-head">
        <h2>Assistant</h2>
        <p className="sub">The assistant explains the results in natural language. Questions and the profile's daily results
          (no raw traffic, addresses or device names) are sent to the chosen provider.</p>
      </div>
      {msg && <p className={msg.kind === "error" ? "error" : "notice"}>{msg.text}</p>}
      <div className="editor">
        <label className="radio"><input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
          Turn the assistant on for everyone who can see a profile</label>
        <div className="form-grid">
          <label className="field">Provider
            <select value={provider} onChange={(e) => { setProvider(e.target.value); setModel(st.providers![e.target.value].default_model); }}>
              {Object.entries(st.providers).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select>
          </label>
          <label className="field">Model
            <input value={model} onChange={(e) => setModel(e.target.value)} placeholder={st.providers[provider]?.default_model} />
          </label>
          <label className="field">API key {st.has_key && provider === st.provider ? <span className="pill pill-beige">stored</span> : null}
            <input type="password" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)}
              placeholder={st.has_key && provider === st.provider ? "leave empty to keep the stored key" : provider === "openrouter" ? "sk-or-…" : "sk-ant-…"} />
          </label>
        </div>
        <p className="muted small">The key is stored on this computer only (<code>~/cmn-data/frontend/assistant.json</code>, readable by
          your user account) and is never shown again in the browser.</p>
        <div className="row-actions">
          <button className="btn btn-primary" onClick={() => save()} disabled={!model.trim()}>Save</button>
          {st.has_key && provider === st.provider && <button className="btn btn-quiet" onClick={() => save(true)}>Remove key</button>}
        </div>
      </div>
    </section>
  );
}
