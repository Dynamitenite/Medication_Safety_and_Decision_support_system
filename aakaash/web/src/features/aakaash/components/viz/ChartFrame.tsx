import { useEffect, useId, useRef, useState, type ReactNode } from "react";

/** Width of an element in px, kept up to date. 0 until the first measure. */
export function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    setWidth(el.clientWidth);
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => setWidth(el.clientWidth));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}

export const reducedMotion = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/** A titled chart with a short description and a Chart / Table switch. The table holds the same data,
 *  so the chart is never the only way to read it. */
export function ChartFrame({
  title,
  description,
  chart,
  table,
  views = ["Chart", "Table"],
  headingLevel = 3,
  note,
}: {
  title: string;
  description: string;
  chart: ReactNode;
  table: ReactNode;
  views?: [string, string] | [string, string, ...string[]];
  headingLevel?: 3 | 4;
  note?: ReactNode;
}) {
  const [table_, setTable] = useState(false);
  const uid = useId();
  const H = `h${headingLevel}` as "h3" | "h4";
  return (
    <figure className="chart-frame" aria-labelledby={`${uid}-t`} aria-describedby={`${uid}-d`}>
      <div className="chart-frame-head">
        <H id={`${uid}-t`}>{title}</H>
        <div className="seg-toggle" role="group" aria-label={`${title}: view`}>
          <button type="button" className={table_ ? "" : "on"} aria-pressed={!table_} onClick={() => setTable(false)}>
            {views[0]}
          </button>
          <button type="button" className={table_ ? "on" : ""} aria-pressed={table_} onClick={() => setTable(true)}>
            {views[1]}
          </button>
        </div>
      </div>
      <p id={`${uid}-d`} className="small muted chart-desc">
        {description}
      </p>
      {table_ ? <div className="table-wrap">{table}</div> : chart}
      {note && <div className="chart-note small muted">{note}</div>}
    </figure>
  );
}
