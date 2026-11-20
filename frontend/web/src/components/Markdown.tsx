import { Fragment, type ReactNode } from "react";

/**
 * A label whose opening ** is missing ("Mon 16/11:** quiet for 5 h") gets it back, so it renders
 * bold like the others. Only when the line has an odd number of ** markers.
 */
export function repairBold(text: string): string {
  if (((text.match(/\*\*/g) ?? []).length) % 2 === 0) return text;
  const m = text.match(/^([^*\n]{1,48}?):\*\*/);
  return m ? `**${m[1]}:**${text.slice(m[0].length)}` : text;
}

/** Inline **bold** and `code` as React elements (no HTML injection). Unpaired ** are never shown. */
function inline(raw: string): ReactNode[] {
  const text = repairBold(raw);
  const out: ReactNode[] = [];
  const plain = (s: string) => s.replace(/\*\*/g, "");
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0;
  for (const m of text.matchAll(re)) {
    if (m.index! > last) out.push(plain(text.slice(last, m.index)));
    const t = m[0];
    out.push(t.startsWith("**") ? <strong key={out.length}>{t.slice(2, -2)}</strong> : <code key={out.length}>{t.slice(1, -1)}</code>);
    last = m.index! + t.length;
  }
  if (last < text.length) out.push(plain(text.slice(last)));
  return out;
}

/** The small Markdown subset the assistant uses: paragraphs, bullet and numbered lists, bold, code. */
export function Markdown({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  let para: string[] = [];
  const flushPara = () => { if (para.length) { blocks.push(<p key={blocks.length}>{inline(para.join(" "))}</p>); para = []; } };
  const flushList = () => {
    if (!list) return;
    const items = list.items.map((it, i) => <li key={i}>{inline(it)}</li>);
    blocks.push(list.ordered ? <ol key={blocks.length}>{items}</ol> : <ul key={blocks.length}>{items}</ul>);
    list = null;
  };
  for (const raw of text.split("\n")) {
    const line = raw.trimEnd();
    const bullet = line.match(/^\s*[-*•]\s+(.*)$/);
    const num = line.match(/^\s*\d+[.)]\s+(.*)$/);
    if (bullet || num) {
      flushPara();
      const ordered = !!num;
      if (!list || list.ordered !== ordered) { flushList(); list = { ordered, items: [] }; }
      list.items.push((bullet ?? num)![1]);
    } else if (!line.trim()) {
      flushPara(); flushList();
    } else if (list && /^\s{2,}/.test(raw)) {
      list.items[list.items.length - 1] += " " + line.trim();
    } else {
      flushList();
      para.push(line.replace(/^#+\s*/, ""));
    }
  }
  flushPara(); flushList();
  return <>{blocks.map((b, i) => <Fragment key={i}>{b}</Fragment>)}</>;
}
