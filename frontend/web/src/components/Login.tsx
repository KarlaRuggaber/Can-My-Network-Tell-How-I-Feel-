import { useState } from "react";
import { api, ApiError, type Me } from "../api";

/** Login card, as the Streamlit app's login dialog: username and password, nothing else. */
export function Login({ onLogin }: { onLogin: (me: Me) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      onLogin(await api.login(username, password));
    } catch (err) {
      setError(err instanceof ApiError && err.status === 401 ? "Invalid login data." : `Could not log in: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-page">
      <form className="login-card card" onSubmit={submit}>
        <span className="brand-squares" aria-hidden="true" />
        <h1>Can My Network Tell How I Feel?</h1>
        <p className="tagline">Explainable Depression Indicators from Network Traffic Metadata</p>
        <h2 className="login-title">Welcome – please log in</h2>
        <label className="field">Username
          <input autoFocus autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} />
        </label>
        <label className="field">Password
          <input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        <button className="btn btn-primary" type="submit" disabled={busy || !username || !password}>
          {busy ? "Logging in…" : "Log in"}
        </button>
        <p className="muted small">Research prototype, not a diagnostic tool. If you need access, ask the study team for a login.</p>
      </form>
    </div>
  );
}
