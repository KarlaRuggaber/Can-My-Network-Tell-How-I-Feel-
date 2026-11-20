import { useState } from "react";
import type { AnswerSources as Sources, SourceItem } from "../api";
import { fmtDay } from "../lib/format";
import { Badge, badgeVariants } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { Icon, ICON_NAMES, type IconName } from "./Icon";

type Props = {
  sources: Sources;
  /** Chip click: the page jumps to the day, criterion or metric. Without it the chips are plain labels. */
  onJump?: (item: SourceItem) => void;
};

const iconOf = (item: SourceItem): IconName | null =>
  item.icon && (ICON_NAMES as string[]).includes(item.icon) ? (item.icon as IconName) : null;

/** What a chip says: a day as 31/10, everything else by its name. */
const chipText = (item: SourceItem) => (item.kind === "day" ? fmtDay(item.id) : item.name);

const JUMP_HINT: Record<SourceItem["kind"], string> = {
  day: "Show this day", metric: "Show this metric", criterion: "Show this criterion", flag: "Show this flag",
};

/** One row of "Show values": "Quiet window; 5.2 h on 31/10; usual 6.8 to 7.6 h". The numbers come from the data. */
export function valueRow(item: SourceItem): string {
  const parts: string[] = [chipText(item)];
  const vals = item.values.filter((v) => v.text);
  if (vals.length) parts.push(vals.map((v) => `${v.text} on ${fmtDay(v.day)}`).join(", "));
  else if (item.kind === "flag" && item.days.length) parts.push(item.days.map(fmtDay).join(", "));
  if (item.usual) parts.push(`usual ${item.usual}`);
  if (item.detail) parts.push(item.detail);
  return parts.join("; ");
}

/** Under an answer: what it was built from, collapsed to one line of chips; one click shows the values. */
export function AnswerSources({ sources, onJump }: Props) {
  const [open, setOpen] = useState(false);
  const { items, fallback, no_data } = sources;

  if (no_data) {
    return <p className="answer-sources muted small" data-testid="answer-sources">Based on: how the portal works, no data of this person</p>;
  }
  if (!items.length) {
    return fallback ? <p className="answer-sources muted small" data-testid="answer-sources">Based on: the current view</p> : null;
  }

  const rows = items.map(valueRow);
  const hasValues = items.some((i) => i.values.some((v) => v.text) || i.usual || i.detail || (i.kind === "flag" && i.days.length));

  return (
    <TooltipProvider delayDuration={300}>
      <Collapsible open={open} onOpenChange={setOpen} className="answer-sources" data-testid="answer-sources">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="answer-sources-label">{fallback ? "Based on: the current view" : "Based on:"}</span>
          {items.map((item) => {
            const icon = iconOf(item);
            const jumpable = !!onJump && (item.kind === "day" || item.days.length > 0 || !!item.code);
            const tip = [item.detail, jumpable ? JUMP_HINT[item.kind] : null].filter(Boolean).join("; ");
            // The generated Badge and Button are plain function components (React 19 style) and cannot hold a
            // ref under React 18, which Tooltip needs: interactive chips use their variants on a native button.
            const chip = jumpable
              ? (
                <button type="button" onClick={() => onJump?.(item)} aria-label={`${chipText(item)}: ${JUMP_HINT[item.kind].toLowerCase()}`}
                  className={cn(badgeVariants({ variant: "secondary" }), "cursor-pointer hover:bg-accent")}>
                  {icon && <Icon name={icon} size={12} />}{chipText(item)}
                </button>
              )
              : <span className="inline-flex"><Badge variant="secondary">{icon && <Icon name={icon} size={12} />}{chipText(item)}</Badge></span>;
            return tip
              ? <Tooltip key={`${item.kind}:${item.id}`}><TooltipTrigger asChild>{chip}</TooltipTrigger><TooltipContent>{tip}</TooltipContent></Tooltip>
              : <span key={`${item.kind}:${item.id}`} className="inline-flex">{chip}</span>;
          })}
          {fallback && (
            <Tooltip>
              <TooltipTrigger asChild><span className="inline-flex" tabIndex={0}><Badge variant="outline">fallback</Badge></span></TooltipTrigger>
              <TooltipContent>The answer did not say which data it used, so this shows what the screen was focused on.</TooltipContent>
            </Tooltip>
          )}
          {hasValues && (
            <CollapsibleTrigger className={cn(buttonVariants({ variant: "ghost", size: "xs" }), "cursor-pointer bg-transparent text-muted-foreground")}>
              {open ? "Hide values" : "Show values"}
            </CollapsibleTrigger>
          )}
        </div>
        {hasValues && (
          <CollapsibleContent>
            <ul className="answer-sources-rows">
              {rows.map((r, i) => <li key={i}>{r}</li>)}
            </ul>
          </CollapsibleContent>
        )}
      </Collapsible>
    </TooltipProvider>
  );
}
