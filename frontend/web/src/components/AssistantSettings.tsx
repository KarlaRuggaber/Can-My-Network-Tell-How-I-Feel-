import { useEffect, useState } from "react";
import { api, type AssistantCheck, type AssistantProviderId, type AssistantStatus } from "../api";

const PROVIDER_TEXT: Record<AssistantProviderId, { short: string; where: string }> = {
  anthropic: { short: "Anthropic (Claude)", where: "are sent to Anthropic's Claude (USA)" },
  local: { short: "Local model", where: "stay on the team's own computers: a model on a laptop or server answers" },
};

/** Multi-profile users: turn the explanation assistant on and choose who answers: Anthropic's Claude
 *  (model, API key) or a local model behind an OpenAI-compatible endpoint (Ollama, llama.cpp, LM Studio). */
export function AssistantSettings() {
  const [st, setSt] = useState<AssistantStatus | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [provider, setProvider] = useState<AssistantProviderId>("anthropic");
  const [model, setModel] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [key, setKey] = useState("");
  const [fallback, setFallback] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [check, setCheck] = useState<AssistantCheck | null>(null);
  const [checking, setChecking] = useState(false);

  const apply = (s: AssistantStatus) => {
    setSt(s); setEnabled(s.enabled || false); setModel(s.model ?? "");
    setProvider(s.provider ?? "anthropic"); setBaseUrl(s.base_url ?? ""); setFallback(!!s.fallback);
  };
  useEffect(() => { api.assistant().then(apply).catch(() => setSt(null)); }, []);

  const providers = st?.providers ?? [];
  const info = providers.find((p) => p.id === provider);
  const defaultModel = info?.default_model ?? st?.default_model ?? "";
  const local = provider === "local";

  const choose = (id: AssistantProviderId) => {
    if (id === provider) return;
    const p = providers.find((x) => x.id === id);
    setProvider(id); setCheck(null); setMsg(null);
    // the stored model belongs to the stored provider; another provider starts from its default
    setModel(id === st?.provider ? st.model ?? "" : p?.default_model ?? "");
    if (id === "local" && !baseUrl) setBaseUrl(p?.default_base_url ?? "");
  };

  const save = async (removeKey = false) => {
    try {
      const s = await api.saveAssistant({
        enabled, model, provider,
        api_key: local ? null : removeKey ? "" : key || null,
        base_url: local ? baseUrl : null,
        fallback: local ? fallback : null,
      });
      apply(s); setKey("");
      setMsg({ kind: "ok", text: removeKey ? "Key removed." : s.has_key ? "Saved." : "Saved, but there is no API key yet." });
    } catch (e) {
      setMsg({ kind: "error", text: String((e as Error).message) });
    }
  };

  const test = async () => {
    setChecking(true); setCheck(null);
    try {
      setCheck(await api.checkAssistant({ base_url: baseUrl, model }));
    } catch (e) {
      setCheck({ ok: false, message: String((e as Error).message), models: [] });
    } finally {
      setChecking(false);
    }
  };

  if (!st?.default_model) return null;
  return (
    <section className="card">
      <div className="card-head">
        <h2>Assistant</h2>
        <p className="sub">The assistant explains the results in natural language and helps fill in the onboarding and the
          care plan. Questions and the profile's daily results (no raw traffic, addresses or device names){" "}
          {local && fallback
            ? "stay on the team's own computers; only when that computer cannot be reached do they go to Anthropic's Claude (USA)"
            : PROVIDER_TEXT[provider].where}.</p>
      </div>
      {msg && <p className={msg.kind === "error" ? "error" : "notice"} role="status">{msg.text}</p>}
      <div className="editor">
        <label className="radio"><input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
          Turn the assistant on for everyone who can see a profile</label>

        {providers.length > 1 && (
          <div role="radiogroup" aria-label="Who answers">
            <h3>Who answers</h3>
            <div className="seg">
              {providers.map((p) => (
                <button key={p.id} type="button" role="radio" aria-checked={p.id === provider}
                  className={p.id === provider ? "active" : ""} onClick={() => choose(p.id)}
                  title={p.label}>
                  {PROVIDER_TEXT[p.id]?.short ?? p.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {local ? (
          <>
            <div className="form-grid">
              <label className="field">Endpoint (OpenAI-compatible URL)
                <input value={baseUrl} onChange={(e) => { setBaseUrl(e.target.value); setCheck(null); }}
                  placeholder={info?.default_base_url ?? "http://127.0.0.1:11434/v1"} inputMode="url" />
              </label>
              <label className="field">Model name on that endpoint
                <input value={model} onChange={(e) => { setModel(e.target.value); setCheck(null); }} placeholder={defaultModel} />
              </label>
            </div>
            <p className="muted small">Ollama: <code>http://&lt;laptop&gt;:11434/v1</code>, model as in <code>ollama list</code>.
              llama.cpp server: port 8080, LM Studio: port 1234, both with <code>/v1</code>. From the gateway, use the
              laptop's Tailscale name or address. Small models answer more slowly and less precisely than Claude.</p>
            {check && <p className={check.ok ? "notice" : "error"} role="status">{check.message}</p>}
            <label className="radio"><input type="checkbox" checked={fallback} onChange={(e) => setFallback(e.target.checked)} />
              If the local model cannot be reached (laptop closed or offline), let Anthropic's Claude answer instead</label>
            {fallback && (
              <p className={st.has_claude_key ? "muted small" : "error"}>
                {st.has_claude_key
                  ? "Uses the stored Claude key and Claude model. Such an answer starts with a note that Claude answered, and the notice for people says that this can happen."
                  : "No Claude key is stored yet: choose Anthropic (Claude), enter the key and save, then switch back to the local model."}
              </p>
            )}
          </>
        ) : (
          <>
            <div className="form-grid">
              <label className="field">Claude model
                <input value={model} onChange={(e) => setModel(e.target.value)} placeholder={defaultModel} />
              </label>
              <label className="field">Claude API key {st.has_claude_key ? <span className="pill pill-beige">stored</span> : null}
                <input type="password" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)}
                  placeholder={st.has_claude_key ? "leave empty to keep the stored key" : "sk-ant-…"} />
              </label>
            </div>
            <p className="muted small">The key is stored on this computer only (<code>~/cmn-data/frontend/assistant.json</code>, readable by
              your user account) and is never shown again in the browser.</p>
          </>
        )}

        <div className="row-actions">
          <button className="btn btn-primary" onClick={() => save()} disabled={!model.trim() || (local && !baseUrl.trim())}>Save</button>
          {local && <button className="btn" onClick={test} disabled={checking || !model.trim() || !baseUrl.trim()}>
            {checking ? "Checking…" : "Check connection"}</button>}
          {model !== defaultModel && <button className="btn btn-quiet" onClick={() => setModel(defaultModel)}>Use the default model</button>}
          {!local && st.has_claude_key &&
            <button className="btn btn-quiet" onClick={() => save(true)}>Remove key</button>}
        </div>
      </div>
    </section>
  );
}
