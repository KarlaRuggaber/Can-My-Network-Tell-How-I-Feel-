import { useEffect, useRef, useState } from "react";
import * as echarts from "echarts";
import { FONT } from "../theme";

type Props = {
  option: echarts.EChartsCoreOption;
  height: number;
  onClick?: (p: echarts.ECElementEvent) => void;
  ariaLabel: string;
  group?: string;          // charts in one group share the hover line and tooltip
  /**
   * Phones: show only the last `visible` of `total` days and let the reader drag sideways for the
   * rest (x axis only; vertical page scrolling keeps working). `hint` adds the one-line hint below.
   */
  scroll?: { visible: number; total: number; hint?: boolean };
};

/** Below this chart width the scroll window applies. */
export const SCROLL_BELOW = 600;

/** The dataZoom that shows the last `visible` of `total` days, dragged with a finger or the mouse. */
export function scrollZoom(visible: number, total: number) {
  const start = Math.max(0, 100 - (100 * visible) / Math.max(total, 1));
  return [{ type: "inside", xAxisIndex: "all", start, end: 100, zoomLock: true,
    zoomOnMouseWheel: false, moveOnMouseWheel: false, moveOnMouseMove: true, preventDefaultMouseMove: false }];
}

/** Thin ECharts wrapper: one instance per mount, resized with its container. */
export function Chart({ option, height, onClick, ariaLabel, group, scroll }: Props) {
  const el = useRef<HTMLDivElement>(null);
  const inst = useRef<echarts.ECharts | null>(null);
  const clickRef = useRef(onClick);
  clickRef.current = onClick;
  const [narrow, setNarrow] = useState(false);

  useEffect(() => {
    if (!el.current) return;
    const c = echarts.init(el.current, undefined, { renderer: "svg" });
    inst.current = c;
    if (group) { c.group = group; echarts.connect(group); }
    c.on("click", (p) => clickRef.current?.(p as echarts.ECElementEvent));
    // When the panel opens or closes, the page takes its new width at once and fades in: redraw once.
    // While the panel edge or the window is dragged, the size changes every frame: the chart is
    // clipped meanwhile and morphs to the new size once the container has settled.
    let timer = 0;
    let first = true;
    setNarrow(el.current.clientWidth < SCROLL_BELOW);
    const ro = new ResizeObserver(() => {
      if (el.current) setNarrow(el.current.clientWidth < SCROLL_BELOW);
      if (first) { first = false; return; }          // initial observation: already sized by init
      window.clearTimeout(timer);
      if (document.documentElement.classList.contains("page-reflowing")) {
        c.resize();                                   // panel opened/closed: redraw once, under the fade
        return;
      }
      timer = window.setTimeout(() => {
        const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
        c.resize(reduce ? undefined : { animation: { duration: 260, easing: "cubicOut" } });
      }, 90);
    });
    ro.observe(el.current);
    return () => { window.clearTimeout(timer); ro.disconnect(); c.dispose(); inst.current = null; };
  }, []);

  const scrolls = !!scroll && narrow && scroll.total > scroll.visible;
  useEffect(() => {
    inst.current?.setOption({ textStyle: { fontFamily: FONT.sans }, ...option,
      ...(scrolls ? { dataZoom: scrollZoom(scroll!.visible, scroll!.total) } : {}) }, { notMerge: true });
  }, [option, scrolls, scroll?.visible, scroll?.total]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      <div ref={el} className={`chart${scrolls ? " chart-scroll" : ""}`} style={{ height, width: "100%" }} role="img" aria-label={ariaLabel} />
      {scrolls && scroll!.hint && <p className="chart-drag-hint">Showing the last {scroll!.visible} days. Drag the chart sideways for earlier days.</p>}
    </>
  );
}
