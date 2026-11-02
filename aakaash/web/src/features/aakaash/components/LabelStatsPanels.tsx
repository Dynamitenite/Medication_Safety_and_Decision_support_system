import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import { useApi } from "../useApi";
import { fmt, KeyValues, Panel } from "./Panel";
import { Sticker } from "./Sticker";

export function DailyMedPanel() {
  const q = useApi(api.dailymedStats);
  return (
    <Panel
      id="dailymed"
      title="DailyMed prescription labels"
      hint="Counts come from a real run of the project's label parser, written to a statistics file. The scope label is the file's own."
      query={q}
    >
      {(d) => {
        const secRows = Object.keys(d.labels_per_section).map((s) => ({
          section: s.replace(/_/g, " "),
          labels: d.labels_per_section[s],
          chunks: d.chunks_per_section[s] ?? 0,
        }));
        return (
          <>
            <p>
              <Sticker tone={d.is_sample ? "neutral" : "good"} wrap>{d.scope}</Sticker>
            </p>
            <KeyValues
              items={[
                ["Labels parsed", fmt(d.labels_parsed)],
                ["Zip entries available", fmt(Object.values(d.zip_entries).reduce((a, b) => a + b, 0))],
                ["Parse failures", fmt(d.parse_failures)],
                ["Chunks", `${fmt(d.chunks)} (size ${d.chunk_size}, overlap ${d.chunk_overlap}, words)`],
                ["Distinct ingredient strings", fmt(d.distinct_ingredients)],
                ["Distinct active moieties", fmt(d.distinct_active_moieties)],
                ["Distinct manufacturers", fmt(d.distinct_manufacturers)],
                ["Labels with no section found", fmt(d.labels_without_any_section)],
                ["Parser run", `${d.elapsed_seconds ?? "–"} s, peak RAM ${d.peak_working_set_mb ?? "–"} MB`],
                ["Parts", d.parts_loaded.join(", ")],
                ["Generated", d.generated_at ?? "–"],
              ]}
            />
            <figure className="chart" aria-label="Labels containing each section">
              <figcaption className="small muted">Labels containing each section</figcaption>
              <ResponsiveContainer width="100%" height={secRows.length * 34 + 24}>
                <BarChart data={secRows} layout="vertical" margin={{ top: 4, right: 56, left: 8, bottom: 4 }}>
                  <CartesianGrid horizontal={false} stroke="rgb(var(--c-line))" />
                  <XAxis type="number" hide domain={[0, "dataMax"]} />
                  <YAxis type="category" dataKey="section" width={150} tickLine={false} axisLine={false} tick={{ fill: "rgb(var(--c-muted))", fontSize: 13 }} />
                  <Tooltip formatter={(v: number) => v.toLocaleString("en-US")} cursor={{ fill: "rgb(var(--c-text) / 0.06)" }} />
                  <Bar dataKey="labels" fill="var(--chart-mechanism)" maxBarSize={18} radius={[0, 4, 4, 0]} isAnimationActive={false}>
                    <LabelList dataKey="labels" position="right" formatter={(v: number) => v.toLocaleString("en-US")} fill="rgb(var(--c-text))" fontSize={12} />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </figure>
            <div className="table-wrap">
              <table>
                <caption>Section counts (table view of the chart)</caption>
                <thead>
                  <tr><th scope="col">Section</th><th scope="col" className="num">Labels with section</th><th scope="col" className="num">Chunks</th></tr>
                </thead>
                <tbody>
                  {secRows.map((r) => (
                    <tr key={r.section}><th scope="row">{r.section}</th><td className="num">{fmt(r.labels)}</td><td className="num">{fmt(r.chunks)}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="small muted">
              Ingredient classes used: {Object.entries(d.ingredient_source).map(([k, v]) => `${k} ${v.toLocaleString("en-US")}`).join(", ")}.
            </p>
          </>
        );
      }}
    </Panel>
  );
}

export function TacPanel() {
  const q = useApi(api.tacStats);
  return (
    <Panel id="tac" title="TAC 2017 adverse-reaction labels" hint="Used to sanity-check section parsing." query={q}>
      {(d) => (
        <KeyValues
          items={[
            ["Labels per split", Object.entries(d.labels_per_split).map(([k, v]) => `${k} ${v}`).join(", ")],
            ["Mentions", fmt(d.mentions)],
            ["Relations", fmt(d.relations)],
            ["Reactions", fmt(d.reactions)],
            ["Labels without text", fmt(d.labels_without_text)],
            ["Parse failures", fmt(d.parse_failures)],
          ]}
        />
      )}
    </Panel>
  );
}
