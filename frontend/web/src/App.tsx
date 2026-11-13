import { useEffect, useMemo, useState } from "react";
import type { Config, CritKey, PersonaListItem, Timeline } from "./api";
import { api, CRIT_KEYS } from "./api";
import { CriteriaSummary } from "./components/CriteriaSummary";
import { DayDetail } from "./components/DayDetail";
import { Heatmap } from "./components/Heatmap";
import { MetricTrends } from "./components/MetricTrends";
import { episodeFlags, gatePresentRolling, type GateParams } from "./lib/gate";

// URL state: #/<dataset>/<day>/<criterion>, so a view can be bookmarked for the video.
function readHash(): { ds?: string; day?: string; crit?: CritKey } {
  const [ds, day, crit] = window.location.hash.replace(/^#\/?/, "").split("/");
  return { ds: ds || undefined, day: day || undefined, crit: (crit as CritKey) || undefined };
}

export default function App() {
  const [cfg, setCfg] = useState<Config | null>(null);
  const [personas, setPersonas] = useState<PersonaListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const init = readHash();
  const [ds, setDs] = useState<string | undefined>(init.ds);
  const [tl, setTl] = useState<Timeline | null>(null);
  const [day, setDay] = useState<string | null>(init.day ?? null);
  const [crit, setCrit] = useState<CritKey | null>(init.crit ?? null);
  const [gate, setGate] = useState<GateParams | null>(null);

  useEffect(() => {
    Promise.all([api.config(), api.personas()])
      .then(([c, p]) => {
        setCfg(c); setPersonas(p);
        setGate({ theta: c.theta, N: c.N, M: c.M, core: c.core, minPresent: 5 });
        if (!ds && p.length) setDs(p[0].dataset);
      })
      .catch((e) => setError(String(e.message ?? e)));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!ds) return;
    setTl(null);
    api.timeline(ds).then((t) => {
      setTl(t);
      setDay((d) => (d && t.days.some((x) => x.date === d) ? d : t.days[t.days.length - 1]?.date ?? null));
    }).catch((e) => setError(String(e.message ?? e)));
  }, [ds]);

  useEffect(() => {
    if (ds) window.history.replaceState(null, "", `#/${ds}/${day ?? ""}/${crit ?? ""}`);
  }, [ds, day, crit]);

  // follow links / manual edits of the hash (replaceState above does not fire this event)
  useEffect(() => {
    const onHash = () => {
      const h = readHash();
      if (h.ds) setDs(h.ds);
      setDay(h.day ?? null);
      setCrit(h.crit ?? null);
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const configured = useMemo(
    () => (cfg ? CRIT_KEYS.filter((c) => Object.keys(cfg.criteria[c] ?? {}).length > 0) : []),
    [cfg]);

  const { present, episode } = useMemo(() => {
    if (!tl || !gate) return { present: {}, episode: [] as boolean[] };
    const p: Partial<Record<CritKey, boolean[]>> = {};
    for (const c of configured) p[c] = gatePresentRolling(tl.days.map((d) => d.L[c]), gate.theta, gate.N, gate.M);
    return { present: p, episode: episodeFlags(p as Record<string, boolean[]>, gate) };
  }, [tl, gate, configured]);

  if (error) return <div className="page"><p className="error">Could not load data: {error}. Is the API running and has the export been run?</p></div>;
  if (!cfg || !personas || !gate) return <div className="page"><p className="muted">Loading…</p></div>;

  const activeCrit: CritKey = crit && configured.includes(crit) ? crit : configured[0];
  const dayIndex = tl ? tl.days.findIndex((d) => d.date === day) : -1;
  const isDefault = gate.theta === cfg.theta && gate.N === cfg.N && gate.M === cfg.M;

  return (
    <div className="page">
      <header className="top">
        <div>
          <h1>Can My Network Tell How I Feel?</h1>
          <p className="sub">Router-level network metrics → DSM-5 criterion likelihoods, per simulated persona.
            Research prototype, not a diagnostic tool.</p>
        </div>
        <nav className="personas" aria-label="Personas">
          {personas.map((p) => (
            <button key={p.dataset} className={p.dataset === ds ? "active" : ""} onClick={() => { setDs(p.dataset); setDay(null); }}>
              <span className="p-name">{p.name}</span>
              <span className="p-cond">{p.condition || p.dataset}</span>
            </button>
          ))}
        </nav>
      </header>

      <div className="gatebar card">
        <span className="gate-title">DSM gate</span>
        <label>θ <input type="range" min={0} max={1} step={0.01} value={gate.theta}
          onChange={(e) => setGate({ ...gate, theta: Number(e.target.value) })} /> <b>{gate.theta.toFixed(2)}</b></label>
        <label>N <input type="number" min={1} max={60} value={gate.N}
          onChange={(e) => setGate({ ...gate, N: Math.max(1, Number(e.target.value)) })} /> days ≥ θ</label>
        <label>within M <input type="number" min={1} max={60} value={gate.M}
          onChange={(e) => setGate({ ...gate, M: Math.max(1, Number(e.target.value)) })} /> days</label>
        <button className="link" disabled={isDefault}
          onClick={() => setGate({ ...gate, theta: cfg.theta, N: cfg.N, M: cfg.M })}>reset to fasl_config.json</button>
        <span className="muted small">{isDefault ? "as configured" : "changed: not saved"} · weights and membership functions from <code>fasl_config.json</code></span>
      </div>

      {!tl && <p className="muted">Loading persona…</p>}
      {tl && (
        <>
          <section className="intro">
            <div>
              <h2>{tl.persona.name} · {tl.persona.condition}</h2>
              <p>{tl.persona.summary}</p>
            </div>
            <dl className="facts">
              <div><dt>Dataset</dt><dd><code>{tl.dataset}</code></dd></div>
              <div><dt>Baseline profile</dt><dd>{tl.persona.baseline_profile ?? "–"}</dd></div>
              <div><dt>Data</dt><dd>{tl.days[0]?.date} – {tl.days[tl.days.length - 1]?.date}</dd></div>
              <div><dt>Days</dt><dd>{tl.days.filter((d) => d.phase === "baseline").length} baseline · {tl.days.filter((d) => d.phase === "clinical").length} clinical</dd></div>
            </dl>
          </section>

          <CriteriaSummary tl={tl} cfg={cfg} present={present} episode={episode} theta={gate.theta}
            selected={activeCrit} onSelect={setCrit} />
          <Heatmap tl={tl} cfg={cfg} present={present} episode={episode} theta={gate.theta}
            selectedDay={day} onSelectDay={setDay} />
          {activeCrit && (
            <MetricTrends tl={tl} cfg={cfg} crit={activeCrit} theta={gate.theta}
              present={present[activeCrit] ?? []} selectedDay={day} onSelectDay={setDay} />
          )}
          {dayIndex >= 0 && (
            <DayDetail dataset={tl.dataset} day={tl.days[dayIndex]} cfg={cfg} present={present} dayIndex={dayIndex} />
          )}
        </>
      )}
      <footer className="muted small">
        Data: gateway Parquet partitions, metrics computed with the unchanged thesis metric code
        (<code>app_pcap_to_dsm5/app/metrics</code>). Expected outcomes: profile §9.
      </footer>
    </div>
  );
}
