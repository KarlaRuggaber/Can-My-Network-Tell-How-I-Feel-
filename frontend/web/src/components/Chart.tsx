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
    const ro = new ResizeObserver(() => c.resize());
    ro.observe(el.current);
    return () => { ro.disconnect(); c.dispose(); inst.current = null; };
  }, []);

  useEffect(() => { inst.current?.setOption({ textStyle: { fontFamily: FONT.sans }, ...option }, { notMerge: true }); }, [option]);

  return <div ref={el} style={{ height, width: "100%" }} role="img" aria-label={ariaLabel} />;
}
