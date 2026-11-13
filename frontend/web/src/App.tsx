import { useCallback, useEffect, useMemo, useState } from "react";
import type { Config, CritKey, Me, PhaseKey, ProfileListItem, Timeline } from "./api";
import { api, CRIT_KEYS, setUnauthorizedHandler } from "./api";
import { CriteriaSummary, type PhaseView } from "./components/CriteriaSummary";
import { DayDetail } from "./components/DayDetail";
import { Heatmap } from "./components/Heatmap";
import { Assistant } from "./components/Assistant";
import { AssistantSettings } from "./components/AssistantSettings";
import { Login } from "./components/Login";
import { PersonView } from "./components/PersonView";
import { MetricTrends } from "./components/MetricTrends";
import { ProfileSettings } from "./components/ProfileSettings";
import { episodeFlags, gatePresentRolling, phaseGate, type GateParams } from "./lib/gate";

const PHASES: PhaseKey[] = ["baseline", "current"];

// URL state: #/<profile>/<day>/<criterion>, or #/settings, so a view can be bookmarked.
function readHash(): { pid?: string; day?: string; crit?: CritKey; settings: boolean } {
  const [pid, day, crit] = window.location.hash.replace(/^#\/?/, "").split("/");
  if (pid === "settings") return { settings: true };
  return { pid: pid || undefined, day: day || undefined, crit: (crit as CritKey) || undefined, settings: false };
}

/** Login gate: the portal looks the same for everyone; the role decides what it offers. */
export default function App() {
  const [me, setMe] = useState<Me | null | undefined>(undefined);   // undefined: checking

  useEffect(() => {
    setUnauthorizedHandler(() => setMe(null));
    api.me().then(setMe).catch(() => setMe(null));
  }, []);

  if (me === undefined) return <div className="page"><p className="muted">Loading…</p></div>;
  if (me === null) return <Login onLogin={setMe} />;
  return <Portal me={me} onLogout={() => { api.logout().finally(() => setMe(null)); }} />;
}

function Portal({ me, onLogout }: { me: Me; onLogout: () => void }) {
  const multi = me.role === "multi";
  const [cfg, setCfg] = useState<Config | null>(null);
  const [profiles, setProfiles] = useState<ProfileListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const init = readHash();
  const [pid, setPid] = useState<string | undefined>(init.pid);
  const [settings, setSettings] = useState(init.settings && multi);
  const [tl, setTl] = useState<Timeline | null>(null);
  const [day, setDay] = useState<string | null>(init.day ?? null);
  const [crit, setCrit] = useState<CritKey | null>(init.crit ?? null);
  const [gate, setGate] = useState<GateParams | null>(null);
  const [rolling, setRolling] = useState(false);   // optional extra view; mixes phases

  const loadProfiles = useCallback((select?: string) =>
    api.profiles().then((p) => {
      setProfiles(p);
      setPid((cur) => select ?? (cur && p.some((x) => x.id === cur) ? cur : p[0]?.id));
    }), []);

  useEffect(() => {
    Promise.all([api.config(), loadProfiles()])
      .then(([c]) => {
        setCfg(c);
        setGate({ theta: c.theta, N: c.N, M: c.M, core: c.core, minPresent: 5 });
      })
      .catch((e) => setError(String(e.message ?? e)));
  }, [loadProfiles]);

  useEffect(() => {
    if (!pid || settings) return;
    setTl(null);
    api.timeline(pid).then((t) => {
      setTl(t);
      setDay((d) => (d && t.days.some((x) => x.date === d) ? d : t.days[t.days.length - 1]?.date ?? null));
    }).catch((e) => setError(String(e.message ?? e)));
  }, [pid, settings]);

  useEffect(() => {
    const h = settings ? "#/settings" : pid ? `#/${pid}/${day ?? ""}/${crit ?? ""}` : "";
    if (h) window.history.replaceState(null, "", h);
  }, [pid, day, crit, settings]);

  // follow links / manual edits of the hash (replaceState above does not fire this event)
  useEffect(() => {
    const onHash = () => {
      const h = readHash();
      setSettings(h.settings && multi);
      if (h.pid) setPid(h.pid);
      if (h.day) setDay(h.day);   // a link without a day keeps the current one
      setCrit(h.crit ?? null);
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, [multi]);

  const configured = useMemo(
    () => (cfg ? CRIT_KEYS.filter((c) => Object.keys(cfg.criteria[c] ?? {}).length > 0) : []),
    [cfg]);

  // Default: the gate per phase, on each phase's complete days only (as the evaluation).
  const phases = useMemo(() => {
    if (!tl || !gate) return null;
    const out = {} as Record<PhaseKey, PhaseView>;
    for (const ph of PHASES) {
      const idx = tl.days.map((d, i) => (d.phase === ph && d.complete ? i : -1)).filter((i) => i >= 0);
      const L = Object.fromEntries(configured.map((c) => [c, idx.map((i) => tl.days[i].L[c])]));
      const info = tl.gate.phases[ph];
      out[ph] = {
        ...phaseGate(L, gate),
        counted: (gate.M > 0 ? idx.slice(-gate.M) : []).map((i) => tl.days[i].date),
        inProgress: tl.days.filter((d) => d.phase === ph && !d.complete).map((d) => d.date),
        plannedFirst: info?.planned_first ?? null,
        plannedLast: info?.planned_last ?? null,
        plannedDays: info?.planned_days ?? 0,
      };
    }
    return out;
  }, [tl, gate, configured]);

  // Per-day marks for the grid, trends and day detail: by default a day carries its phase's
  // gate result if it is counted in it; the rolling window (mixes phases) only on request.
  const { present, episode } = useMemo(() => {
    if (!tl || !gate || !phases) return { present: {}, episode: [] as boolean[] };
    const p: Partial<Record<CritKey, boolean[]>> = {};
    if (rolling) {
      for (const c of configured) p[c] = gatePresentRolling(tl.days.map((d) => d.L[c]), gate.theta, gate.N, gate.M);
      return { present: p, episode: episodeFlags(p as Record<string, boolean[]>, gate) };
    }
    const phaseOf = (d: Timeline["days"][number]) =>
      PHASES.find((ph) => ph === d.phase && phases[ph].counted.includes(d.date));
    for (const c of configured) {
      p[c] = tl.days.map((d) => { const ph = phaseOf(d); return !!ph && !!phases[ph].criteria[c]?.present; });
    }
    return { present: p, episode: tl.days.map((d) => { const ph = phaseOf(d); return !!ph && phases[ph].episode; }) };
  }, [tl, gate, configured, phases, rolling]);

  if (error) return <div className="page"><p className="error">Could not load data: {error}. Is the API running and has the export been run?</p></div>;
  if (!cfg || !profiles || !gate) return <div className="page"><p className="muted">Loading…</p></div>;

  const activeCrit: CritKey = crit && configured.includes(crit) ? crit : configured[0];
  const dayIndex = tl ? tl.days.findIndex((d) => d.date === day) : -1;
  const isDefault = gate.theta === cfg.theta && gate.N === cfg.N && gate.M === cfg.M;
  const labels = tl?.profile.phase_labels ?? { baseline: "Baseline", current: "Recent" };

  return (
    <div className="page">
      <header className="top">
        <span className="brand-squares" aria-hidden="true" />
        <div>
          <h1>Can My Network Tell How I Feel?</h1>
          <p className="tagline">Explainable Depression Indicators from Network Traffic Metadata</p>
          <p className="disclaimer">Router-level network metrics → DSM-5 criterion likelihoods.
            Research prototype, not a diagnostic tool.</p>
        </div>
        <div className="top-right">
          <div className="usermenu">
            <span className="muted small">Signed in as <b>{me.username}</b></span>
            {multi && (
              <button className={`btn ${settings ? "btn-active" : ""}`} onClick={() => setSettings(!settings)}>
                Settings
              </button>
            )}
            <button className="btn btn-quiet" onClick={onLogout}>Log out</button>
          </div>
          {multi && !settings && profiles.length > 0 && (
            <nav className="personas" aria-label="People">
              {profiles.map((p) => (
                <button key={p.id} className={p.id === pid ? "active" : ""} onClick={() => { setPid(p.id); setDay(null); }}>
                  <span className="p-name">{p.name}</span>
                  <span className="p-cond">{p.condition || `${p.source} · ${p.config.all_devices ? "all devices" : `${p.config.devices.length} device(s)`}`}</span>
                </button>
              ))}
            </nav>
          )}
        </div>
      </header>

      {settings && multi && (
        <>
          <ProfileSettings onClose={() => setSettings(false)}
            onChanged={(id) => { loadProfiles(id); if (id) { setPid(id); setTl(null); } }} />
          <AssistantSettings />
        </>
      )}

      {!settings && profiles.length === 0 && (
        <section className="card">
          <h2>No profile yet</h2>
          <p>{multi ? "Add a person under Settings → People and devices." : "Your login has no profile assigned. Please contact the study team."}</p>
        </section>
      )}

      {!settings && profiles.length > 0 && (
        <>
          {multi && (
            <details className="gatebar card">
              <summary>
                <span className="gate-title">Gate</span>
                <span>a criterion counts as <b>present</b> when L ≥ <b>{gate.theta.toFixed(2)}</b> on <b>{gate.N}</b> of a phase's
                  last <b>{gate.M}</b> days</span>
                {!isDefault && <span className="pill pill-beige">changed</span>}
                {rolling && <span className="pill pill-beige">day marks: rolling window</span>}
                <span className="gate-adjust">Adjust</span>
              </summary>
              <div className="gate-controls">
                <label>θ <input type="range" min={0} max={1} step={0.01} value={gate.theta}
                  onChange={(e) => setGate({ ...gate, theta: Number(e.target.value) })} /> <b>{gate.theta.toFixed(2)}</b></label>
                <label>N <input type="number" min={1} max={60} value={gate.N}
                  onChange={(e) => setGate({ ...gate, N: Math.max(1, Number(e.target.value)) })} /> days ≥ θ</label>
                <label>within M <input type="number" min={1} max={60} value={gate.M}
                  onChange={(e) => setGate({ ...gate, M: Math.max(1, Number(e.target.value)) })} /> days</label>
                <button className="btn" disabled={isDefault}
                  onClick={() => setGate({ ...gate, theta: cfg.theta, N: cfg.N, M: cfg.M })}>Reset</button>
                <label className="rolling-toggle" title="Right after the baseline, a rolling window is mostly baseline days.">
                  <input type="checkbox" checked={rolling} onChange={(e) => setRolling(e.target.checked)} />
                  mark days with a rolling {gate.M}-day window instead (mixes phases)
                </label>
                <p className="muted small gate-note">Changes apply in this browser only. Weights and membership functions come from <code>fasl_config.json</code>.</p>
              </div>
            </details>
          )}

          {!tl && <p className="muted">Loading…</p>}
          {tl && (
            <>
              {multi && <section className="intro">
                <div>
                  <h2>{tl.persona.name}{tl.persona.condition && <> · {tl.persona.condition}</>}</h2>
                  {tl.persona.summary && <p>{tl.persona.summary}</p>}
                </div>
                <dl className="facts">
                  <div><dt>Traffic</dt><dd>{tl.profile.has_plan ? "scripted run" : "live"} · {tl.profile.all_devices ? "all devices" : tl.profile.devices.map((d) => d.label || d.ip).join(", ")}</dd></div>
                  <div><dt>Recorded days</dt><dd>{tl.days.filter((d) => d.phase === "baseline").length} {labels.baseline.toLowerCase()} · {tl.days.filter((d) => d.phase === "current").length} {labels.current.toLowerCase()}</dd></div>
                </dl>
              </section>}

              {tl.status === "pending" && (
                <section className="card">
                  <h2>Data is being prepared</h2>
                  <p>No days have been computed for {tl.persona.name}'s devices yet. They appear after the next export run
                    (<code>python -m cmn_frontend.export</code>, or the running <code>--watch</code> loop).</p>
                </section>
              )}

              {tl.status === "ready" && phases && !multi && (
                <>
                  <PersonView tl={tl} cfg={cfg} recent={phases.current} gate={gate} />
                  <Assistant profileId={tl.profile.id} person focus={null} />
                </>
              )}

              {tl.status === "ready" && phases && multi && (
                <>
                  <CriteriaSummary tl={tl} cfg={cfg} phases={phases} gate={gate}
                    selected={activeCrit} onSelect={setCrit} />
                  <Heatmap tl={tl} cfg={cfg} present={present} episode={episode} theta={gate.theta}
                    rolling={rolling} M={gate.M} selectedDay={day} onSelectDay={setDay} />
                  {activeCrit && (
                    <MetricTrends tl={tl} cfg={cfg} crit={activeCrit} theta={gate.theta}
                      present={present[activeCrit] ?? []} presentLabel={rolling ? `present (rolling ${gate.M} days, mixes phases)` : "present in this phase"}
                      selectedDay={day} onSelectDay={setDay} />
                  )}
                  {dayIndex >= 0 && (
                    <DayDetail profileId={tl.profile.id} day={tl.days[dayIndex]} cfg={cfg} present={present}
                      dayIndex={dayIndex} phaseLabels={labels} />
                  )}
                  <Assistant profileId={tl.profile.id} person={false}
                    focus={[day && `day ${day}`, activeCrit && `${activeCrit} ${cfg.criterion_names[activeCrit]}`].filter(Boolean).join(", ") || null} />
                </>
              )}
            </>
          )}
        </>
      )}
      {multi && <footer className="muted small">
        Metrics computed with the unchanged thesis metric code (<code>app_pcap_to_dsm5/app/metrics</code>) on the
        person's devices.{tl?.profile.has_plan && " Expected outcomes: profile §9."}
      </footer>}
    </div>
  );
}
