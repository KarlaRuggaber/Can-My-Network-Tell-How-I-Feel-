import { useLayoutEffect, useRef, type TextareaHTMLAttributes } from "react";

/**
 * A textarea that grows with its text (typed, pasted or dictated) and shrinks back, never below
 * its `rows`. Also follows width changes, since narrower boxes need more lines.
 */
export function AutoTextarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const fit = () => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";                                   // back to `rows`, then measure
    const cs = window.getComputedStyle(el);
    const border = parseFloat(cs.borderTopWidth) + parseFloat(cs.borderBottomWidth);
    el.style.height = `${el.scrollHeight + (cs.boxSizing === "border-box" ? border : 0)}px`;
  };
  useLayoutEffect(fit, [props.value]);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    let width = el.clientWidth;
    const ro = new ResizeObserver(() => { if (el.clientWidth !== width) { width = el.clientWidth; fit(); } });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return <textarea {...props} ref={ref} className={`auto-textarea${props.className ? " " + props.className : ""}`} />;
}
