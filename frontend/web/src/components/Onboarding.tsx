import { useState } from "react";
import { api, type AwayPeriod, type Care, type Routine } from "../api";
import { AwayEditor, defaultRoutine, RoutineForm } from "./RoutineForm";
import { Icon } from "./Icon";

type Props = {
  profileId: string;
  name: string;
  care: Care | undefined;
  assistant: boolean;
  onDone: (care: Care) => void;
  onSkip?: () => void;
};

const STEPS = ["Welcome", "Your week", "Your devices", "Anything else"];

/** First visit of a patient: what is measured, their week, their devices. Changeable later in "My week". */
export function Onboarding({ profileId, name, care, assistant, onDone, onSkip }: Props) {
  const [step, setStep] = useState(0);
  const [routine, setRoutine] = useState<Routine>(care?.routine ?? defaultRoutine());
  const [away, setAway] = useState<AwayPeriod[]>(care?.away_periods ?? []);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const finish = async () => {
    setSaving(true); setError(null);
    try {
      await api.putRoutine(profileId, { ...routine, devices: routine.devices.filter((d) => d.name.trim()) });
      onDone(await api.putAway(profileId, away));
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="card onboarding">
      <ol className="steps" aria-label="Steps">
        {STEPS.map((s, i) => <li key={s} className={i === step ? "active" : i < step ? "done" : ""}>{s}</li>)}
      </ol>

      {step === 0 && (
        <div className="ob-body">
          <h2>Welcome, {name}</h2>
          <p>This research prototype looks at <b>when and how much</b> your devices use your home Wi-Fi, and which
            sites they contact by name. It does <b>not</b> see what you read, write or search: pages and messages are encrypted.</p>
          <p>It compares your recent days with your usual weeks. To do that well, it helps to know what your usual week
            looks like: when you are away for school or work, when you usually go to bed, and which devices are yours.
            This takes about three minutes, and you can change everything later under <b>My week</b>.</p>
          <p className="muted small">It is not a diagnosis. If you are worried about how you feel, talk to someone you trust or your doctor.</p>
        </div>
      )}
      {step === 1 && (
        <div className="ob-body">
          <h2>Your week</h2>
          {assistant && <p className="muted">Describe your week in your own words, typed or spoken. Afterwards a few short
            questions ask for what is still open, one at a time; you can skip any of them and change everything by hand.</p>}
          <RoutineForm profileId={profileId} value={routine} onChange={setRoutine} person assistant={assistant}
            sections={["describe", "week", "times"]} />
        </div>
      )}
      {step === 2 && (
        <div className="ob-body">
          <h2>Your devices</h2>
          <RoutineForm profileId={profileId} value={routine} onChange={setRoutine} person assistant={false} sections={["devices"]} />
        </div>
      )}
      {step === 3 && (
        <div className="ob-body">
          <h2>Anything else</h2>
          <RoutineForm profileId={profileId} value={routine} onChange={setRoutine} person assistant={false} sections={["note"]} />
          <AwayEditor value={away} onChange={setAway} person />
        </div>
      )}

      {error && <p className="error">{error}</p>}
      <div className="row-actions ob-actions">
        {step > 0 && <button className="btn btn-quiet" onClick={() => setStep(step - 1)}>Back</button>}
        {step === 0 && onSkip && <button className="btn btn-quiet" onClick={onSkip}>Later</button>}
        {step < STEPS.length - 1
          ? <button className="btn btn-primary" onClick={() => setStep(step + 1)}>{step === 0 ? "Start" : "Next"}</button>
          : <button className="btn btn-primary" onClick={finish} disabled={saving}>{saving ? "Saving…" : "Save and finish"}</button>}
      </div>
    </section>
  );
}

/** The patient's own page to change their week, devices and away periods at any time. */
export function MyWeek({ profileId, care, assistant, onSaved, onClose }: {
  profileId: string; care: Care | undefined; assistant: boolean; onSaved: (c: Care) => void; onClose: () => void;
}) {
  const [routine, setRoutine] = useState<Routine>(care?.routine ?? defaultRoutine());
  const [away, setAway] = useState<AwayPeriod[]>(care?.away_periods ?? []);
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  const save = async () => {
    try {
      await api.putRoutine(profileId, { ...routine, devices: routine.devices.filter((d) => d.name.trim()) });
      onSaved(await api.putAway(profileId, away));
      setMsg({ kind: "ok", text: "Saved. Your days are now compared with this routine." });
    } catch (e) {
      setMsg({ kind: "error", text: String((e as Error).message) });
    }
  };

  return (
    <section className="card">
      <div className="card-head row-between">
        <div>
          <h2>My week</h2>
          <p className="sub">Your usual week, your devices and the times you are away. Change it whenever something changes.</p>
        </div>
        <button className="btn btn-icon" onClick={onClose} aria-label="Back to my overview" title="Back to my overview">
          <Icon name="home" size={22} />
        </button>
      </div>
      {msg && <p className={msg.kind === "error" ? "error" : "notice"}>{msg.text}</p>}
      <RoutineForm profileId={profileId} value={routine} onChange={setRoutine} person assistant={assistant} />
      <AwayEditor value={away} onChange={setAway} person />
      <div className="row-actions"><button className="btn btn-primary" onClick={save}>Save</button></div>
    </section>
  );
}
