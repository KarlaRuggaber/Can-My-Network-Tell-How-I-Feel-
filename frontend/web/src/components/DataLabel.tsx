import type { Timeline } from "../api";
import { Icon, type IconName } from "./Icon";
import "./overview.css";

type Item = { icon: IconName; text: string; detail?: string };

const COLLECTED: Item[] = [
  { icon: "clock", text: "When your devices are online", detail: "minute by minute, from your home Wi-Fi only" },
  { icon: "data", text: "How much they are used", detail: "the amount of traffic per hour, not what it contains" },
  { icon: "globe", text: "Which sites, by name", detail: "e.g. youtube.com, not the pages or videos on it" },
];

const NOT_COLLECTED: string[] = [
  "What you read, watch or write",
  "Messages and their content",
  "Search terms",
  "Who you talk to",
  "Where you are",
];

const deviceIcon = (kind: string): IconName => (/laptop|computer|pc|mac/i.test(kind) ? "laptop" : "phone");

/** App-Store-style privacy label at the top of the person's own page (A2). */
export function DataLabel({ tl }: { tl: Timeline }) {
  const named = tl.care?.routine?.devices ?? [];
  const devices = named.length
    ? named.map((d) => ({ name: d.name, kind: d.kind }))
    : tl.profile.devices.map((d) => ({ name: d.label || d.ip, kind: d.label }));
  return (
    <section className="card data-label" aria-labelledby="data-label-title">
      <div className="t1-head">
        <h2 id="data-label-title">What this page is based on</h2>
        <p className="sub">Your home network, {tl.profile.all_devices ? "all devices in it" : "only your devices"}. A research prototype, not a diagnosis.</p>
      </div>
      <div className="dl-grid">
        <div className="dl-col">
          <h3 className="dl-head"><Icon name="data" /> Collected</h3>
          <ul className="dl-list">
            {COLLECTED.map((c) => (
              <li key={c.text}><span className="dl-icon"><Icon name={c.icon} size={16} /></span>
                <span><b>{c.text}</b>{c.detail && <span className="muted small"> · {c.detail}</span>}</span></li>
            ))}
          </ul>
          {devices.length > 0 && (
            <p className="dl-devices small">
              <span className="muted">Devices: </span>
              {devices.map((d) => (
                <span key={d.name} className="dl-device"><Icon name={deviceIcon(d.kind)} size={15} /> {d.name}</span>
              ))}
            </p>
          )}
        </div>
        <div className="dl-col dl-not">
          <h3 className="dl-head"><Icon name="lock" /> Not collected</h3>
          <ul className="dl-list">
            {NOT_COLLECTED.map((t) => <li key={t}><span className="dl-icon dl-cross" aria-hidden="true">×</span><span>{t}</span></li>)}
          </ul>
        </div>
      </div>
      <p className="dl-care small"><Icon name="person" size={15} /> <b>Your care team also sees:</b> the same days and times, how they compare with
        typical ranges, the notes they write, and visits to crisis or self-harm sites (so they can support you quickly).</p>
    </section>
  );
}
