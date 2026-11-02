import { BMI_AXIS, BMI_BANDS, BMI_SOURCE, bmiScale, type BmiBand } from "../../viz/bmi";
import { useWidth } from "./ChartFrame";

const TONE: Record<BmiBand["id"], string> = { underweight: "--c-amber", normal: "--c-mint", overweight: "--c-amber", obese: "--c-rose" };
const frac = (v: number) => (v - BMI_AXIS.min) / (BMI_AXIS.max - BMI_AXIS.min);

/** WHO adult BMI ranges as a scale with a marker. Shown only from age 18 with a BMI; otherwise says why not. */
export function BmiScaleCard({ age, bmi }: { age: number | null | undefined; bmi: number | null | undefined }) {
  const [wrap, width] = useWidth<HTMLDivElement>();
  const s = bmiScale(age, bmi);
  if (!s.show)
    return (
      <section className="card" aria-labelledby="bmi-h">
        <h2 id="bmi-h">BMI scale</h2>
        <p className="muted">{s.reason}</p>
      </section>
    );
  const W = Math.max(width, 260);
  const padX = 14;
  const inner = W - 2 * padX;
  const x = (v: number) => padX + frac(v) * inner;
  const barY = 34;
  const edges = [BMI_AXIS.min, 18.5, 25, 30, BMI_AXIS.max];
  return (
    <section className="card" aria-labelledby="bmi-h">
      <h2 id="bmi-h">BMI scale</h2>
      <p className="small muted" id="bmi-d">
        Your BMI is {s.bmi.toFixed(1)} and falls in the “{s.band.label}” category. Source of the ranges: {BMI_SOURCE}. BMI does not show how much of the weight is muscle or fat, so it is a rough guide only.
      </p>
      <div ref={wrap} className="bmi-wrap">
        <svg width={W} height={78} role="img" aria-label={`BMI ${s.bmi.toFixed(1)}: ${s.band.label}. Scale from ${BMI_AXIS.min} to ${BMI_AXIS.max}.`} aria-describedby="bmi-d" focusable="false">
          {BMI_BANDS.map((b, i) => {
            const a = edges[i];
            const z = edges[i + 1];
            const on = b.id === s.band.id;
            return (
              <rect key={b.id} className="bmi-seg" x={x(a) + 1} y={barY} width={x(z) - x(a) - 2} height={18} rx={3} style={{ fill: `rgb(var(${TONE[b.id]}) / ${on ? 0.5 : 0.16})`, stroke: `rgb(var(${TONE[b.id]}))`, strokeWidth: on ? 2 : 1 }} />
            );
          })}
          {[18.5, 25, 30].map((v) => (
            <text key={v} className="bmi-tick" x={x(v)} y={70} textAnchor="middle">
              {v}
            </text>
          ))}
          <g className="bmi-marker" transform={`translate(${x(BMI_AXIS.min + s.position * (BMI_AXIS.max - BMI_AXIS.min))} 0)`}>
            <path d="M0 31 L-6 21 L6 21 Z" />
            <text y={14} textAnchor={s.position > 0.85 ? "end" : s.position < 0.15 ? "start" : "middle"}>
              BMI {s.bmi.toFixed(1)}
            </text>
          </g>
        </svg>
      </div>
      <ul className="bmi-key small">
        {BMI_BANDS.map((b) => (
          <li key={b.id} className={b.id === s.band.id ? "on" : ""}>
            <span className="bmi-swatch" style={{ background: `rgb(var(${TONE[b.id]}) / 0.4)`, borderColor: `rgb(var(${TONE[b.id]}))` }} aria-hidden="true" />
            <span>
              {b.label} <span className="muted">({b.range})</span>
              {b.id === s.band.id && <strong> · yours</strong>}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
