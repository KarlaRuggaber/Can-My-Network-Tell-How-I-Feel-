import type { Config, CritKey, SourceItem } from "../api";

export type Jump = { day?: string; crit?: CritKey; tab?: "details"; scrollId?: string };

const isCrit = (c: string | null | undefined): c is CritKey => !!c && /^C[1-9]$/.test(c);

/**
 * Where the page goes when a "Based on" chip is clicked. A day selects that day; a criterion selects it
 * (clinicians: on the Details tab); a scored metric opens its criterion and scrolls to the metric's
 * chart; everything else (an observed metric, a flag) selects the latest day the answer named. The
 * person's page only has days, so there it is always the day. Nothing outside `days` is ever selected.
 */
export function jumpTarget(item: SourceItem, opts: { multi: boolean; days: string[]; cfg?: Pick<Config, "metric_criterion"> | null }): Jump {
  const have = (d: string | undefined) => (d && opts.days.includes(d) ? d : undefined);
  const latest = have(item.kind === "day" ? item.id : [...item.days].reverse().find((d) => have(d)));
  const out: Jump = {};
  if (latest) out.day = latest;
  if (!opts.multi) return out;
  if (item.kind === "criterion" && isCrit(item.code)) {
    out.crit = item.code;
    out.tab = "details";
  } else if (item.kind === "metric" && item.code) {
    const crit = opts.cfg?.metric_criterion[item.code] ?? (item.code.match(/^(C\d)_/)?.[1] as CritKey | undefined);
    if (isCrit(crit)) {
      out.crit = crit;
      out.tab = "details";
      out.scrollId = `metric-${item.code}`;
    }
  }
  return out;
}
