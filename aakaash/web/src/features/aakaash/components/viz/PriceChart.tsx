import { useMemo } from "react";
import { Bar, BarChart, CartesianGrid, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { selectPrices, PRICE_LIMIT, type PriceInput } from "../../viz/priceChart";
import { ChartFrame, useWidth } from "./ChartFrame";

const rupees = (n: number) => `₹${n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const clip = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

/** Horizontal bars of the pack price of the cheapest same-form alternatives, with the selected brand marked.
 *  Loaded on demand (it carries the chart library). */
export default function PriceChart({ alts, selected, total }: { alts: PriceInput[]; selected: PriceInput | null; total: number }) {
  const sel = useMemo(() => selectPrices(alts, selected), [alts, selected]);
  const [wrap, width] = useWidth<HTMLDivElement>();
  if (sel.bars.length === 0) return null;
  const narrow = width > 0 && width < 520;
  const yw = narrow ? 104 : 168;
  const chars = narrow ? 14 : 24;
  const rows = sel.bars.map((b) => ({ ...b, tick: (b.selected ? "Selected: " : "") + clip(b.name, chars) }));
  const hidden = [
    sel.notShown > 0 ? `${sel.notShown} more with a price are not drawn` : "",
    sel.noPrice > 0 ? `${sel.noPrice} list no price` : "",
  ].filter(Boolean);

  const chart = (
    <div ref={wrap} className="price-chart">
      <ResponsiveContainer width="100%" height={rows.length * 30 + 44}>
        <BarChart data={rows} layout="vertical" margin={{ top: 4, right: narrow ? 64 : 76, left: 4, bottom: 4 }} accessibilityLayer>
          <CartesianGrid horizontal={false} stroke="rgb(var(--c-line))" />
          <XAxis type="number" tickLine={false} axisLine={{ stroke: "rgb(var(--c-line))" }} tick={{ fill: "rgb(var(--c-muted))", fontSize: 12 }} tickFormatter={(v: number) => `₹${v}`} />
          <YAxis type="category" dataKey="tick" width={yw} tickLine={false} axisLine={false} interval={0} tick={{ fill: "rgb(var(--c-soft))", fontSize: 12 }} />
          <Tooltip
            cursor={{ fill: "rgb(var(--c-text) / 0.06)" }}
            content={({ active, payload }) => {
              const p = active && payload?.length ? (payload[0].payload as (typeof rows)[number]) : null;
              return p ? (
                <div className="chart-tooltip">
                  <strong>{p.name}</strong>
                  {p.selected && <div>Selected brand</div>}
                  <div>{rupees(p.price)} per pack</div>
                  <div>Pack: {p.pack_size || "not stated"}</div>
                  <div>{p.manufacturer ?? "Manufacturer not stated"}</div>
                </div>
              ) : null;
            }}
          />
          <Bar dataKey="price" maxBarSize={18} radius={[0, 3, 3, 0]} isAnimationActive={false} stroke="var(--chart-edge)" strokeWidth={1}>
            {rows.map((r) => (
              <Cell key={r.id} fill={r.selected ? "rgb(var(--c-text))" : "rgb(var(--c-subtle))"} />
            ))}
            <LabelList dataKey="price" position="right" formatter={(v: number) => rupees(v)} fill="rgb(var(--c-text))" fontSize={12} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );

  const table = (
    <table>
      <caption className="sr-only">Pack price of same-form alternatives, cheapest first</caption>
      <thead>
        <tr>
          <th scope="col">Brand</th>
          <th scope="col">Maker</th>
          <th scope="col">Pack</th>
          <th scope="col" className="num">Price per pack</th>
        </tr>
      </thead>
      <tbody>
        {sel.bars.map((b) => (
          <tr key={b.id}>
            <th scope="row">
              {b.name}
              {b.selected && " (selected)"}
            </th>
            <td>{b.manufacturer ?? "not stated"}</td>
            <td>{b.pack_size || "not stated"}</td>
            <td className="num">{rupees(b.price)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );

  return (
    <ChartFrame
      title="Price per pack"
      description={`The ${Math.min(PRICE_LIMIT, total)} cheapest same-form brands of ${total}, shortest bar cheapest. The selected brand is the dark bar and is named. Packs differ in size, so compare the pack column.`}
      chart={chart}
      table={table}
      note={hidden.length ? `${hidden.join("; ")}.` : undefined}
    />
  );
}
