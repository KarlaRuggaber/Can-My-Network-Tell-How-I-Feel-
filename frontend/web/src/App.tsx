import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { Care, Config, CritKey, Me, Note, PhaseKey, ProfileListItem, SeenMarks, SourceItem, Timeline } from "./api";
import { api, CRIT_KEYS, setUnauthorizedHandler } from "./api";
import { CriteriaSummary, type PhaseView } from "./components/CriteriaSummary";
import { DayDetail } from "./components/DayDetail";
import { Heatmap } from "./components/Heatmap";
import { HourlyHeatmap } from "./components/HourlyHeatmap";
import { UnscoredMetrics } from "./components/UnscoredMetrics";
import { Assistant, resetConversations, type AskRequest } from "./components/Assistant";
import { CarePlan } from "./components/CarePlan";
import { MyWeek, Onboarding } from "./components/Onboarding";
import { AboutData } from "./components/AboutData";
import { DataLabel } from "./components/DataLabel";
import { AssistantSettings } from "./components/AssistantSettings";
import { Login } from "./components/Login";
import { Overview } from "./components/Overview";
import { Timeline as TimelineView } from "./components/Timeline";
import { MetricTrends } from "./components/MetricTrends";
import { ProfileSettings } from "./components/ProfileSettings";
import { ScrollRail } from "./components/ScrollRail";
import { AppBar } from "./components/AppBar";
import type { IconName } from "./components/Icon";
import { jumpTarget } from "./lib/jump";
import "./shell.css";
import { episodeFlags, gatePresentRolling, phaseGate, type GateParams } from "./lib/gate";

const PHASES: PhaseKey[] = ["baseline", "current"];

export type Tab = "overview" | "timeline" | "details" | "about" | "care";
const TABS: Tab[] = ["overview", "timeline", "details", "about", "care"];
const MULTI_ONLY: Tab[] = ["details", "care"];   // "about" exists for both roles, with role-specific content
const tabAllowed = (t: Tab, multi: boolean) => multi || !MULTI_ONLY.includes(t);

/** The thesis behind the prototype: shown only as a small "About" line, not as the product name. */
export const THESIS_TITLE = "Can My Network Tell How I Feel? Explainable depression indicators from network traffic metadata";

// Icons only where one of the fixed icon meanings (VISUAL.md) fits the tab.
type TabDef = { key: Tab; label: string; short?: string; icon?: IconName; sub: (multi: boolean) => string; multiOnly?: boolean };
const TAB_DEFS: TabDef[] = [
  { key: "overview", label: "Overview", icon: "person", sub: (m) => (m ? "what the network observed" : "your recent days") },
  { key: "timeline", label: "Timeline", icon: "days", sub: (m) => (m ? "day by day, with notes" : "day by day") },
  { key: "details", label: "Details", icon: "explain", sub: () => "DSM-5 model, metrics, days", multiOnly: true },
  // the person sees the same tab with "What this page is based on" (DataLabel)
  { key: "about", label: "About the data", short: "About", icon: "data", sub: (m) => (m ? "what the network can and cannot see" : "what this page is based on") },
  { key: "care", label: "Care plan", icon: "note", sub: () => "routine, devices, focus, normals", multiOnly: true },
];

// URL state: #/<profile>/<day>/<criterion>/<tab>, or #/settings, so a view can be bookmarked.
function readHash(): { pid?: string; day?: string; crit?: CritKey; tab?: Tab; settings: boolean } {
  const [pid, day, crit, tab] = window.location.hash.replace(/^#\/?/, "").split("/");
  if (pid === "settings") return { settings: true };
  return { pid: pid || undefined, day: day || undefined, crit: (crit as CritKey) || undefined,
    tab: TABS.includes(tab as Tab) ? (tab as Tab) : undefined, settings: false };
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
  return <Portal me={me} onLogout={() => { resetConversations(); api.logout().finally(() => setMe(null)); }} />;
}

const ASSISTANT_KEY = "cmn.assistantOpen";
function readOpen(): boolean {
  try { return window.localStorage.getItem(ASSISTANT_KEY) === "1"; } catch { return false; }
}

function Portal({ me, onLogout }: { me: Me; onLogout: () => void }) {
  const multi = me.role === "multi";
  const [assistantOpen, setAssistantOpenState] = useState(readOpen);
  // Opening/closing the panel changes the page width. Animating that reflow frame by frame stutters
  // (text and tables re-wrap every frame), so the new layout applies at once and the content glides
  // and fades into it while the panel slides.
  const [reflow, setReflow] = useState<"" | "from-right" | "from-left">("");
  const prevOpen = useRef(assistantOpen);
  useLayoutEffect(() => {
    if (prevOpen.current === assistantOpen) return;
    prevOpen.current = assistantOpen;
    const root = document.documentElement;
    setReflow(assistantOpen ? "from-right" : "from-left");
    root.classList.add("page-reflowing");
    const t = window.setTimeout(() => { setReflow(""); root.classList.remove("page-reflowing"); }, 460);
    return () => { window.clearTimeout(t); root.classList.remove("page-reflowing"); };
  }, [assistantOpen]);
  const setAssistantOpen = useCallback((v: boolean) => {
    setAssistantOpenState(v);
    try { window.localStorage.setItem(ASSISTANT_KEY, v ? "1" : "0"); } catch { /* per-browser convenience only */ }
  }, []);
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
  const [tab, setTab] = useState<Tab>(init.tab && tabAllowed(init.tab, multi) ? init.tab : "overview");
  const [askReq, setAskReq] = useState<AskRequest | null>(null);
  const [myWeek, setMyWeek] = useState(false);                       // the person's "My week" page (account menu)
  const clearAsk = useCallback(() => setAskReq(null), []);
  const [assistantOn, setAssistantOn] = useState(false);
  const [skipOnboarding, setSkipOnboarding] = useState(() => {
    try { return window.sessionStorage.getItem("cmn.skipOnboarding") === "1"; } catch { return false; }
  });
  useEffect(() => { api.assistant().then((a) => setAssistantOn(a.enabled)).catch(() => setAssistantOn(false)); }, []);
  const [notes, setNotes] = useState<Note[]>([]);
  const [seen, setSeen] = useState<SeenMarks>({});
  // "Explain this" anywhere on the page: open the assistant with the question
  const ask = useCallback((question: string, focus: string) => {
    setAssistantOpen(true);
    setAskReq({ id: Date.now(), question, focus });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  // a "Based on" chip under an answer: select the day / criterion, or scroll to the metric's chart
  const jump = useCallback((item: SourceItem) => {
    const t = jumpTarget(item, { multi, days: tl?.days.map((d) => d.date) ?? [], cfg });
    if (t.day) setDay(t.day);
    if (t.crit) setCrit(t.crit);
    if (t.tab) setTab(t.tab);
    if (t.scrollId) {   // the chart exists once the Details tab shows that criterion
      const id = t.scrollId;
      window.setTimeout(() => document.getElementById(id)?.scrollIntoView({ block: "center", behavior: "smooth" }), 150);
    }
  }, [multi, tl, cfg]);
  // the care plan changes day types, flags and usual ranges: reload the timeline after saving
  const onCareSaved = useCallback((_care: Care) => {
    if (!pid) return;
    api.timeline(pid).then((t) => setTl(t)).catch(() => undefined);
  }, [pid]);
  const onSeen = useCallback((flag: string, lastDay: string | null) => {
    if (!pid) return;
    (lastDay ? api.markSeen(pid, flag, lastDay) : api.unmarkSeen(pid, flag)).then((r) => setSeen(r.seen)).catch(() => undefined);
  }, [pid]);

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
      setNotes(t.notes ?? []);
      setSeen(t.seen ?? {});
      setDay((d) => (d && t.days.some((x) => x.date === d) ? d : t.days[t.days.length - 1]?.date ?? null));
    }).catch((e) => setError(String(e.message ?? e)));
  }, [pid, settings]);

  useEffect(() => {
    const h = settings ? "#/settings" : pid ? `#/${pid}/${day ?? ""}/${crit ?? ""}/${tab}` : "";
    if (h) window.history.replaceState(null, "", h);
  }, [pid, day, crit, settings, tab, multi]);

  // follow links / manual edits of the hash (replaceState above does not fire this event)
  useEffect(() => {
    const onHash = () => {
      const h = readHash();
      setSettings(h.settings && multi);
      if (h.pid) setPid(h.pid);
      if (h.day) setDay(h.day);   // a link without a day keeps the current one
      setCrit(h.crit ?? null);
      if (h.tab && tabAllowed(h.tab, multi)) setTab(h.tab);
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

  const setupMissing = !tl?.care ? [] : [
    ...(!tl.care.routine ? ["the patient's routine"] : []),
    ...((tl.care.routine?.devices ?? []).some((d) => !d.ip) ? ["device links"] : []),
    ...(!tl.care.clinical ? ["history and focus"] : []),
  ];
  const activeCrit: CritKey = crit && configured.includes(crit) ? crit : configured[0];
  const dayIndex = tl ? tl.days.findIndex((d) => d.date === day) : -1;
  const isDefault = gate.theta === cfg.theta && gate.N === cfg.N && gate.M === cfg.M;
  const labels = tl?.profile.phase_labels ?? { baseline: "Baseline", current: "Recent" };

  const drawer = assistantOpen && !settings && tl?.status === "ready";
  return (
    <div className={`page ${drawer ? "page-with-drawer" : ""} ${reflow ? `reflow-${reflow}` : ""}`}>
      <ScrollRail watch={`${pid ?? ""}/${tab}/${settings ? "settings" : ""}`} />
      <AppBar username={me.username} multi={multi} onLogout={onLogout}
        tabs={!settings && profiles.length > 0 && tl?.status === "ready"
          ? TAB_DEFS.filter((t) => multi || !t.multiOnly).map((t) => ({
            key: t.key, label: t.label, short: t.short, icon: t.icon, sub: t.sub(multi),
            dot: t.key === "care" && setupMissing.length > 0 ? "Care plan incomplete" : undefined,
          }))
          : null}
        tab={tab} onTab={(k) => { setMyWeek(false); setTab(k as Tab); }}
        onHome={() => { setSettings(false); setMyWeek(false); setTab("overview"); }}
        profiles={profiles} pid={pid} showPicker={multi && profiles.length > 0}
        onPick={(id) => { if (id !== pid) { setPid(id); setDay(null); } }}
        settings={settings && multi} onToggleSettings={() => setSettings(!settings)}
        backLabel={`Back to ${profiles.find((x) => x.id === pid)?.name ?? "overview"}`}
        myWeek={myWeek} onToggleMyWeek={() => setMyWeek(!myWeek)}
        thesis={multi ? THESIS_TITLE : undefined} />

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
          {multi && tab === "details" && (
            <details className="gatebar card">
              <summary>
                <span className="gate-title">Rule for "present"</span>
                <span>a criterion counts as <b>present</b> in a period when its daily score is at least <b>{gate.theta.toFixed(2)}</b> on
                  {" "}<b>{gate.N}</b> or more of that period's last <b>{gate.M}</b> days. One unusual day is not enough; a pattern is.</span>
                {!isDefault && <span className="pill pill-beige">changed</span>}
                {rolling && <span className="pill pill-beige">day marks: rolling window</span>}
                <span className="gate-adjust">Adjust</span>
              </summary>
              <div className="gate-controls">
                <label>Daily score at least <input type="range" min={0} max={1} step={0.01} value={gate.theta}
                  onChange={(e) => setGate({ ...gate, theta: Number(e.target.value) })} /> <b>{gate.theta.toFixed(2)}</b></label>
                <label>on <input type="number" min={1} max={60} value={gate.N}
                  onChange={(e) => setGate({ ...gate, N: Math.max(1, Number(e.target.value)) })} /> days</label>
                <label>of the last <input type="number" min={1} max={60} value={gate.M}
                  onChange={(e) => setGate({ ...gate, M: Math.max(1, Number(e.target.value)) })} /> days</label>
                <button className="btn" disabled={isDefault}
                  onClick={() => setGate({ ...gate, theta: cfg.theta, N: cfg.N, M: cfg.M })}>Reset</button>
                <label className="rolling-toggle" title="Right after the baseline, a rolling window is mostly baseline days.">
                  <input type="checkbox" checked={rolling} onChange={(e) => setRolling(e.target.checked)} />
                  mark each day by its own last {gate.M} days (can mix baseline and recent days)
                </label>
                <p className="muted small gate-note">A stricter rule (higher score, more days) shows fewer criteria as present; a looser one shows more,
                  including chance patterns. Changes apply in this browser only and are not saved.</p>
              </div>
            </details>
          )}

          {!tl && <p className="muted">Loading…</p>}
          {tl && (
            <>
              {multi && <section className="intro">
                <div>
                  {/* the title names the person only: a condition here would frame what the reader sees */}
                  <h2>{tl.persona.name}</h2>
                </div>
                <dl className="facts">
                  <div><dt>Traffic</dt><dd>{tl.profile.has_plan ? "scripted run" : "live"}, {tl.profile.all_devices ? "all devices" : tl.profile.devices.map((d) => d.label || d.ip).join(", ")}</dd></div>
                  <div><dt>Recorded days</dt><dd>{tl.days.filter((d) => d.phase === "baseline").length} {labels.baseline.toLowerCase()}, {tl.days.filter((d) => d.phase === "current").length} {labels.current.toLowerCase()}</dd></div>
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
                  {/* My week (account menu) and About the data open at any time; onboarding only replaces Overview / Timeline */}
                  {myWeek ? (
                    <MyWeek profileId={tl.profile.id} care={tl.care} assistant={assistantOn} onSaved={onCareSaved} onClose={() => setMyWeek(false)} />
                  ) : tab === "about" ? (
                    <DataLabel tl={tl} />
                  ) : !tl.care?.routine && !skipOnboarding ? (
                    <Onboarding profileId={tl.profile.id} name={tl.persona.name} care={tl.care} assistant={assistantOn}
                      onDone={onCareSaved}
                      onSkip={() => { setSkipOnboarding(true); try { window.sessionStorage.setItem("cmn.skipOnboarding", "1"); } catch { /* ignore */ } }} />
                  ) : tab === "timeline"
                    ? <TimelineView tl={tl} person notes={[]} onNotes={() => undefined} selectedDay={day} onSelectDay={setDay} onAsk={ask} />
                    : <Overview tl={tl} person selectedDay={day} onSelectDay={setDay} onAsk={ask} />}
                  <Assistant request={askReq} open={assistantOpen} onToggle={setAssistantOpen} onRequestHandled={clearAsk} onJump={jump} profileId={tl.profile.id} person focus={null}
                    focusInfo={{ day }} />
                </>
              )}

              {tl.status === "ready" && multi && tab === "care" && (
                <>
                  <CarePlan tl={tl} cfg={cfg} assistant={assistantOn} onSaved={onCareSaved} onAsk={ask} />
                  <Assistant request={askReq} open={assistantOpen} onToggle={setAssistantOpen} onRequestHandled={clearAsk} onJump={jump} profileId={tl.profile.id} person={false} focus="care plan" />
                </>
              )}

              {tl.status === "ready" && phases && multi && (tab === "overview" || tab === "timeline") && (
                <>
                  {setupMissing.length > 0 && (
                    <p className="notice setup-notice">Care plan incomplete: {setupMissing.join(", ")}.{" "}
                      <button className="link" onClick={() => setTab("care")}>Open the care plan</button></p>
                  )}
                  {(tl.care?.clinical?.criteria.length ?? 0) > 0 && (
                    <p className="focus-line muted small">Focus: {tl.care!.clinical!.criteria.map((c) => <span key={c} className="tag">{c} {cfg.criterion_names[c]}</span>)}</p>
                  )}
                  {tab === "timeline"
                    ? <TimelineView tl={tl} person={false} notes={notes} onNotes={setNotes} selectedDay={day} onSelectDay={setDay}
                        onOpenDetails={(d) => { setDay(d); setTab("details"); }} onAsk={ask} />
                    : <Overview tl={tl} person={false} selectedDay={day} onSelectDay={setDay} seen={seen} onSeen={onSeen} onAsk={ask} />}
                  <Assistant request={askReq} open={assistantOpen} onToggle={setAssistantOpen} onRequestHandled={clearAsk} onJump={jump} profileId={tl.profile.id} person={false}
                    focus={`${tab}${day ? `, day ${day}` : ""}`} focusInfo={{ day }} />
                </>
              )}

              {tl.status === "ready" && phases && multi && tab === "details" && (
                <>
                  <CriteriaSummary tl={tl} cfg={cfg} phases={phases} gate={gate}
                    selected={activeCrit} onSelect={setCrit} />
                  <Heatmap tl={tl} cfg={cfg} present={present} episode={episode} theta={gate.theta}
                    rolling={rolling} M={gate.M} selectedDay={day} onSelectDay={setDay} onAsk={ask} />
                  <HourlyHeatmap tl={tl} selectedDay={day} onSelectDay={setDay} step={3} />
                  {activeCrit && (
                    <MetricTrends tl={tl} cfg={cfg} crit={activeCrit} theta={gate.theta}
                      present={present[activeCrit] ?? []} presentLabel={rolling ? `present (rolling ${gate.M} days, mixes phases)` : "present in this phase"}
                      selectedDay={day} onSelectDay={setDay} />
                  )}
                  <UnscoredMetrics tl={tl} cfg={cfg} selectedDay={day} onSelectDay={setDay} step={5} onAsk={ask} />
                  {dayIndex >= 0 && (
                    <DayDetail profileId={tl.profile.id} day={tl.days[dayIndex]} cfg={cfg} present={present}
                      dayIndex={dayIndex} phaseLabels={labels} onAsk={ask}
                      activePackets={tl.observed?.params.active_packets} />
                  )}
                  <Assistant request={askReq} open={assistantOpen} onToggle={setAssistantOpen} onRequestHandled={clearAsk} onJump={jump} profileId={tl.profile.id} person={false}
                    focus={[day && `day ${day}`, activeCrit && `${activeCrit} ${cfg.criterion_names[activeCrit]}`].filter(Boolean).join(", ") || null}
                    focusInfo={{ day, criterion: activeCrit ? { key: activeCrit, name: cfg.criterion_names[activeCrit] } : null }} />
                </>
              )}

              {tl.status === "ready" && multi && tab === "about" && (
                <>
                  <AboutData cfg={cfg} focus={tl.care?.clinical?.criteria ?? []} onAsk={ask} />
                  <Assistant request={askReq} open={assistantOpen} onToggle={setAssistantOpen} onRequestHandled={clearAsk} onJump={jump} profileId={tl.profile.id} person={false}
                    focus="about the data" focusInfo={{}} />
                </>
              )}
            </>
          )}
        </>
      )}
      {multi && <footer className="muted small">
        Metrics computed with the unchanged thesis metric code (<code>app_pcap_to_dsm5/app/metrics</code>) on the
        person's devices.{tl?.profile.has_plan && " Expected outcomes come from the test script."}
      </footer>}
    </div>
  );
}
