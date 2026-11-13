import { useEffect, useRef } from "react";
import * as echarts from "echarts";
import { FONT } from "../theme";

type Props = {
  option: echarts.EChartsCoreOption;
  height: number;
  onClick?: (p: echarts.ECElementEvent) => void;
  ariaLabel: string;
};

/** Thin ECharts wrapper: one instance per mount, resized with its container. */
export function Chart({ option, height, onClick, ariaLabel }: Props) {
  const el = useRef<HTMLDivElement>(null);
  const inst = useRef<echarts.ECharts | null>(null);
  const clickRef = useRef(onClick);
  clickRef.current = onClick;

  useEffect(() => {
    if (!el.current) return;
    const c = echarts.init(el.current, undefined, { renderer: "svg" });
    inst.current = c;
    c.on("click", (p) => clickRef.current?.(p as echarts.ECElementEvent));
    // When the panel opens or closes, the page takes its new width at once and fades in: redraw once.
    // While the panel edge or the window is dragged, the size changes every frame: the chart is
    // clipped meanwhile and morphs to the new size once the container has settled.
    let timer = 0;
    let first = true;
    const ro = new ResizeObserver(() => {
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

  useEffect(() => { inst.current?.setOption({ textStyle: { fontFamily: FONT.sans }, ...option }, { notMerge: true }); }, [option]);

  return <div ref={el} className="chart" style={{ height, width: "100%" }} role="img" aria-label={ariaLabel} />;
}
