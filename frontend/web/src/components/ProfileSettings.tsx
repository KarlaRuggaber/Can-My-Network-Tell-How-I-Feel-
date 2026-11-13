import { useEffect, useMemo, useState } from "react";
import { api, type DeviceRef, type Profile, type ProfileBody, type Source, type SourceDevice } from "../api";
import { fmtNum } from "../lib/format";

type Props = { onChanged: (id?: string) => void; onClose: () => void };

const empty = (source: string): ProfileBody => ({
  name: "", source, all_devices: false, devices: [], baseline_first: null, baseline_last: null,
});

/** Multi-profile users: people, their traffic source, which devices belong to them, baseline period. */
export function ProfileSettings({ onChanged, onClose }: Props) {
  const [profiles, setProfiles] = useState<Profile[] | null>(null);
  const [sources, setSources] = useState<Source[]>([]);
  const [editing, setEditing] = useState<string | "new" | null>(null);
  const [form, setForm] = useState<ProfileBody | null>(null);
  const [devices, setDevices] = useState<SourceDevice[] | null>(null);
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [onlyFree, setOnlyFree] = useState(false);

  const load = async () => {
    const [list, srcs] = await Promise.all([api.profiles(), api.sources()]);
    setSources(srcs);
    setProfiles(list.map((p) => p.config));
  };
  useEffect(() => { load().catch((e) => setMsg({ kind: "error", text: String(e.message ?? e) })); }, []);

  useEffect(() => {
    if (!form?.source) return;
    setDevices(null);
    api.sourceDevices(form.source).then(setDevices).catch(() => setDevices([]));
  }, [form?.source]);

  const source = sources.find((s) => s.source === form?.source);
  const chosen = useMemo(() => new Set(form?.devices.map((d) => d.ip) ?? []), [form]);
  const editingName = profiles?.find((p) => p.id === editing)?.name;

  const startEdit = (p: Profile) => {
    setEditing(p.id); setMsg(null);
    setForm({ name: p.name, source: p.source, all_devices: p.all_devices, devices: p.devices,
      baseline_first: p.baseline_first, baseline_last: p.baseline_last });
  };
  const startNew = () => { setEditing("new"); setMsg(null); setForm(empty(sources[0]?.source ?? "")); };

  const toggleDevice = (d: SourceDevice) => {
    if (!form) return;
    const devs: DeviceRef[] = chosen.has(d.ip)
      ? form.devices.filter((x) => x.ip !== d.ip)
      : [...form.devices, { ip: d.ip, label: d.label }];
    setForm({ ...form, devices: devs });
  };
  const setLabel = (ip: string, label: string) =>
    form && setForm({ ...form, devices: form.devices.map((d) => (d.ip === ip ? { ...d, label } : d)) });

  const save = async () => {
    if (!form) return;
    try {
      const res = editing === "new" ? await api.createProfile(form) : await api.updateProfile(editing!, form);
      setMsg({ kind: "ok", text: res.pending
        ? `Saved. ${res.name}'s data is prepared by the next export run (python -m cmn_frontend.export); until then the overview is empty.`
        : `Saved.` });
      setEditing(null); setForm(null);
      await load();
      onChanged(res.id);
    } catch (e) {
      setMsg({ kind: "error", text: String((e as Error).message) });
    }
  };

  const remove = async (p: Profile) => {
    if (!window.confirm(`Delete the profile ${p.name}? Its computed data stays on disk.`)) return;
    await api.deleteProfile(p.id);
    await load();
    onChanged();
  };

  const shown = (devices ?? []).filter((d) => !onlyFree || chosen.has(d.ip) || d.assigned_to.filter((n) => n !== editingName).length === 0);

  return (
    <section className="card">
      <div className="card-head row-between">
        <div>
          <h2>People and devices</h2>
          <p className="sub">Who is monitored, from which traffic source, and which devices belong to whom.
            A person's metrics are computed on their own devices only.</p>
        </div>
        <button className="btn" onClick={onClose}>Back to overview</button>
      </div>

      {msg && <p className={msg.kind === "error" ? "error" : "notice"}>{msg.text}</p>}
      {!profiles && <p className="muted">Loading…</p>}

      {profiles && !form && (
        <>
          <div className="profile-list">
            {profiles.map((p) => (
              <div key={p.id} className="profile-row">
                <div>
                  <div className="p-name">{p.name}</div>
                  <div className="muted small">
                    <code>{p.source}</code> · {p.all_devices ? "all devices of the source" : `${p.devices.length} device${p.devices.length === 1 ? "" : "s"}: ${p.devices.map((d) => d.label || d.ip).join(", ")}`}
                  </div>
                </div>
                <div className="row-actions">
                  <button className="btn" onClick={() => startEdit(p)}>Edit</button>
                  <button className="btn btn-quiet" onClick={() => remove(p)}>Delete</button>
                </div>
              </div>
            ))}
          </div>
          <button className="btn btn-primary" onClick={startNew} disabled={!sources.length}>+ Add a person</button>
        </>
      )}

      {form && (
        <div className="editor">
          <h3>{editing === "new" ? "New person" : `Edit ${editingName}`}</h3>
          <div className="form-grid">
            <label className="field">Name
              <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Anna" />
            </label>
            <label className="field">Traffic source
              <select value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value, devices: [] })}>
                {sources.map((s) => (
                  <option key={s.source} value={s.source}>
                    {s.source} {s.has_plan ? "(scripted)" : "(live)"} · {s.n_days} days
                  </option>
                ))}
              </select>
            </label>
          </div>

          <fieldset className="fieldset">
            <legend>Devices</legend>
            <label className="radio"><input type="radio" checked={form.all_devices} onChange={() => setForm({ ...form, all_devices: true })} />
              All devices of this source <span className="muted small">(one person per router; for the scripted runs this keeps the evaluation's numbers)</span></label>
            <label className="radio"><input type="radio" checked={!form.all_devices} onChange={() => setForm({ ...form, all_devices: false })} />
              Only the devices selected below</label>
            {!form.all_devices && (
              <>
                <div className="row-between">
                  <span className="muted small">Local addresses seen in this source, most traffic first.</span>
                  <label className="toggle"><input type="checkbox" checked={onlyFree} onChange={(e) => setOnlyFree(e.target.checked)} /> hide devices of other people</label>
                </div>
                {!devices && <p className="muted">Loading devices…</p>}
                {devices && devices.length === 0 && <p className="muted">No devices found yet. They appear after the export has processed this source.</p>}
                {devices && devices.length > 0 && (
                  <div className="table-wrap scroll-y">
                    <table className="device-table">
                      <thead><tr><th /><th>Address</th><th>Name</th><th className="num">Packets</th><th className="num">Days</th><th>Belongs to</th></tr></thead>
                      <tbody>
                        {shown.map((d) => {
                          const on = chosen.has(d.ip);
                          const others = d.assigned_to.filter((n) => n !== editingName);
                          return (
                            <tr key={d.ip} className={on ? "selected" : ""}>
                              <td><input type="checkbox" checked={on} onChange={() => toggleDevice(d)} aria-label={`Use ${d.ip}`} /></td>
                              <td><code>{d.ip}</code></td>
                              <td>{on
                                ? <input className="inline-input" value={form.devices.find((x) => x.ip === d.ip)?.label ?? ""} placeholder="e.g. Anna's phone"
                                    onChange={(e) => setLabel(d.ip, e.target.value)} />
                                : <span className="muted">{d.label || "–"}</span>}</td>
                              <td className="num">{fmtNum(d.packets)}</td>
                              <td className="num">{d.days}</td>
                              <td>{others.length ? <span className="pill pill-beige">{others.join(", ")}</span> : <span className="muted small">nobody</span>}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )}
          </fieldset>

          <fieldset className="fieldset">
            <legend>Baseline period</legend>
            {source?.has_plan
              ? <p className="muted small">This is a scripted run: baseline and clinical phase come from its plan.</p>
              : (
                <>
                  <p className="muted small">The days that show this person's usual behaviour; later days are compared with them.
                    Leave empty to use the first 14 days with data.</p>
                  <div className="form-grid">
                    <label className="field">From <input type="date" value={form.baseline_first ?? ""} min={source?.first_day ?? undefined} max={source?.last_day ?? undefined}
                      onChange={(e) => setForm({ ...form, baseline_first: e.target.value || null })} /></label>
                    <label className="field">To <input type="date" value={form.baseline_last ?? ""} min={form.baseline_first ?? source?.first_day ?? undefined} max={source?.last_day ?? undefined}
                      onChange={(e) => setForm({ ...form, baseline_last: e.target.value || null })} /></label>
                  </div>
                </>
              )}
          </fieldset>

          <div className="row-actions">
            <button className="btn btn-primary" onClick={save} disabled={!form.name.trim() || (!form.all_devices && form.devices.length === 0)}>Save</button>
            <button className="btn btn-quiet" onClick={() => { setForm(null); setEditing(null); }}>Cancel</button>
          </div>
        </div>
      )}
    </section>
  );
}
