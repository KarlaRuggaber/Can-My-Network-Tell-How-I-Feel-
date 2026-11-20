import type { Day, Timeline } from "../api";
import { fmtDay } from "../lib/format";
import { fmtClock, fmtHours, lastDays } from "../lib/observed";
import { Icon } from "./Icon";
import "./overview.css";

type Props = {
  tl: Timeline;
  person: boolean;
  selectedDay: string | null;
  onSelectDay: (d: string) => void;
  n?: number;
  /** Rows can be picked (and show the pick) only when something uses the selected day, e.g. open charts. */
  selectable?: boolean;
};

/** Layer 1 for the person (A4): the last week as a table, three facts per day, no judgement. */
export function WeekTable({ tl, person, selectedDay, onSelectDay, n = 7, selectable = true }: Props) {
  const days = lastDays(tl.days, n);
  const usual = tl.observed?.usual ?? {};
  const whose = person ? "Your" : `${tl.persona.name}'s`;
  return (
    <section className="card week-summary" aria-labelledby="week-title">
      <div className="t1-head">
        <h2 id="week-title">{person ? "Your last 7 days" : "Last 7 days"}</h2>
        <p className="sub">Per day, from the home network: how long devices were in use, when they went quiet the night before,
          and when they were back online. Asleep, away or switched off look the same here.</p>
      </div>
      <table className="wt">
        <thead>
          <tr>
            <th scope="col">Day</th>
            <th scope="col"><span className="wt-th"><Icon name="clock" size={16} /> Time in use</span></th>
            <th scope="col"><span className="wt-th"><Icon name="moon" size={16} /> Went quiet</span><span className="wt-sub">the night before</span></th>
            <th scope="col"><span className="wt-th"><Icon name="sunrise" size={16} /> Back online</span><span className="wt-sub">in the morning</span></th>
          </tr>
        </thead>
        <tbody>
          {days.map((d) => <Row key={d.date} d={d} selected={d.date === selectedDay} onSelect={() => onSelectDay(d.date)} selectable={selectable} />)}
        </tbody>
        {(usual.online_hours || usual.quiet_start || usual.quiet_end) && (
          <tfoot>
            <tr className="wt-usual">
              <th scope="row">{whose} usual weeks</th>
              <td>{usual.online_hours ? fmtHours(usual.online_hours.mean) : "–"}</td>
              <td>{usual.quiet_start ? fmtClock(usual.quiet_start.mean) : "–"}</td>
              <td>{usual.quiet_end ? fmtClock(usual.quiet_end.mean) : "–"}</td>
            </tr>
          </tfoot>
        )}
      </table>
      {days.length === 0 && <p className="muted">No days recorded yet.</p>}
    </section>
  );
}

function Row({ d, selected, onSelect, selectable }: { d: Day; selected: boolean; onSelect: () => void; selectable: boolean }) {
  const o = d.observed;
  const has = !!o?.has_data;
  return (
    <tr className={selectable ? `clickable ${selected ? "selected" : ""}` : undefined} onClick={selectable ? onSelect : undefined}>
      <th scope="row">
        {selectable
          ? <button className="wt-day" onClick={(e) => { e.stopPropagation(); onSelect(); }}>{d.weekday} {fmtDay(d.date)}</button>
          : <span className="wt-day">{d.weekday} {fmtDay(d.date)}</span>}
        {!d.complete && <span className="muted small">still being recorded</span>}
      </th>
      {has ? (
        <>
          <td>{fmtHours(o!.online_hours)}</td>
          <td>{fmtClock(o!.quiet_start)}</td>
          <td>{fmtClock(o!.quiet_end)}</td>
        </>
      ) : <td colSpan={3} className="muted">No data on this day</td>}
    </tr>
  );
}
