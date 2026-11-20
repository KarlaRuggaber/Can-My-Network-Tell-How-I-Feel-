import type { ReactNode } from "react";
import type { Config, CritKey } from "../api";
import { Icon, type IconName } from "./Icon";
import { ObservabilityTable } from "./ObservabilityCard";

type Item = { icon: IconName; title: string; text: ReactNode };

/** What the home router records. Shown on the "About the data" tab (D8). */
export const SEES: Item[] = [
  { icon: "clock", title: "When devices are in use", text: "Time stamps and amount of traffic of each registered device, per 5 minutes." },
  { icon: "moon", title: "When devices go quiet at night", text: "The longest stretch at night without active use, and when use starts again." },
  { icon: "globe", title: "Which sites and services, by name", text: "Hostnames such as “youtube.com” from DNS look-ups: the site, not the page or the video." },
  { icon: "chat", title: "Chat sessions", text: "Connections to messaging services and how long they last, not who is written to." },
  { icon: "alert", title: "Visits to crisis and self-harm help sites", text: "By hostname only; shown to the care team as a flag, never switched off." },
];

/** What it cannot see, stated explicitly (reviewer and UZH team feedback). */
export const CANNOT_SEE: Item[] = [
  { icon: "lock", title: "No search terms", text: "What is typed into a search engine is encrypted (HTTPS) and never recorded." },
  { icon: "lock", title: "No page content", text: "No URLs or paths, no text, images or videos of a page; only the site's name." },
  { icon: "lock", title: "No message content", text: "Not what is written or said in chats, calls or e-mails, and not with whom." },
  { icon: "data", title: "Home Wi-Fi only", text: "Nothing on mobile data, at school, at friends' or on other networks." },
  { icon: "moon", title: "Quiet is not asleep", text: "A quiet device can mean asleep, away, reading, or the phone switched off; a phone used in bed shortens the quiet window." },
  { icon: "person", title: "Not who is using a device", text: "A shared laptop or tablet counts for the person it is registered to." },
];

function ItemList({ items }: { items: Item[] }) {
  return (
    <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 10 }}>
      {items.map((it) => (
        <li key={it.title} style={{ display: "grid", gridTemplateColumns: "22px 1fr", gap: 8, alignItems: "start" }}>
          <span aria-hidden="true" style={{ paddingTop: 2 }}><Icon name={it.icon} /></span>
          <span><b>{it.title}</b><br /><span className="small muted">{it.text}</span></span>
        </li>
      ))}
    </ul>
  );
}

type Props = {
  cfg: Config;
  /** Criteria in the care plan's focus (highlighted in the observability table). */
  focus?: CritKey[];
  onAsk?: (question: string, focus: string) => void;
};

/**
 * "About the data" tab: what the network sees and cannot see, and how well each DSM-5 criterion
 * C1–C9 can be observed from it. Mounted by App.tsx as its own tab (T3).
 */
export function AboutData({ cfg, focus = [], onAsk }: Props) {
  return (
    <>
      <section className="card">
        <div className="card-head">
          <h2><Icon name="data" label="About the data" /> About the data</h2>
          <p className="sub">The portal only uses metadata the home router sees: when devices are online, how much traffic they
            send, and the names of the sites they connect to. These are proxies for behaviour, not measurements of mood or sleep.</p>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 20 }}>
          <div>
            <h3 style={{ marginTop: 0 }}>What the network sees</h3>
            <ItemList items={SEES} />
          </div>
          <div>
            <h3 style={{ marginTop: 0 }}>What it cannot see</h3>
            <ItemList items={CANNOT_SEE} />
          </div>
        </div>
        <details className="howto">
          <summary>How the numbers are made</summary>
          <p>Every day, the traffic of the person's devices becomes a set of metrics (e.g. quiet window, number of different sites).
            Each metric is compared with the range where it starts to count and turned into a score between 0 and 1; the weighted
            scores add up to a likelihood per criterion. A criterion counts as present only when the likelihood stays high on
            several days of a period. Hostnames can be hidden by DNS-over-HTTPS or iCloud Private Relay; background traffic
            (updates, backups) is filtered out before the metrics are computed.</p>
        </details>
      </section>

      {cfg.observability && (
        <section className="card">
          <div className="card-head">
            <h2>How well each criterion can be seen</h2>
            <p className="sub">Per DSM-5 criterion C1–C9, from the project's symptom–network mapping: what the network can observe,
              what it cannot, and the known caveats. Criteria that are not scored have no likelihood.</p>
          </div>
          <ObservabilityTable cfg={cfg} focus={focus} onAsk={onAsk} />
        </section>
      )}
    </>
  );
}
