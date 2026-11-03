import { Link } from "react-router-dom";
import { api } from "../api";
import type { SimilarUseSuggestion } from "../api";
import { useApi } from "../useApi";
import { rupees } from "./AlternativesView";
import { Disclosure } from "./Disclosure";
import { Sticker } from "./Sticker";

const formLine = (l: SimilarUseSuggestion["supporting_label"]) => (l.form ? (l.route ? `${l.form} · ${l.route}` : l.form) : "form not stated");

function Suggestion({ s }: { s: SimilarUseSuggestion }) {
  return (
    <li className="similar-item">
      <div className="card-head">
        <h4>{s.ingredient}</h4>
        <span className="evidence-score" title="Best cosine similarity between the uses listed on the two US labels">
          similarity {s.similarity.toFixed(2)}
          {s.supporting_chunks != null && ` · ${s.supporting_chunks} supporting passages`}
        </span>
      </div>
      {s.flags.map((f) => (
        <p key={f} className="small">
          <Sticker wrap>Check</Sticker> {f}
        </p>
      ))}
      <blockquote className="similar-quote">
        “{s.supporting_sentence}”
        <footer className="small muted">
          US label: {s.supporting_label.name} · {s.supporting_label.manufacturer ?? "manufacturer not stated"} · Form: {formLine(s.supporting_label)}
        </footer>
      </blockquote>
      <p className="small muted">Compared with: “{s.matched_query_sentence}”</p>
      {s.brands.length > 0 ? (
        <div className="table-wrap">
          <table>
            <caption className="small muted">
              Brands in the same dosage form, cheapest first (showing {s.brands.length} of {s.brands_total})
            </caption>
            <thead>
              <tr>
                <th scope="col">Brand</th>
                <th scope="col">Price</th>
                <th scope="col">Pack</th>
                <th scope="col">Manufacturer</th>
              </tr>
            </thead>
            <tbody>
              {s.brands.map((b) => (
                <tr key={b.id}>
                  <th scope="row">
                    <Link to={`/medicine/${b.id}`}>{b.name}</Link>
                    {b.ingredient_count > 1 && <span className="small muted"> · {b.ingredient_count} ingredients</span>}
                  </th>
                  <td>{rupees(b.price)}</td>
                  <td>{b.pack_size || "not stated"}</td>
                  <td>{b.manufacturer ?? "not stated"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="small muted">{s.brands_note}</p>
      )}
    </li>
  );
}

/** Other ingredients whose US-label uses read like this medicine's. Hidden entirely unless the API is ready
 *  (no index, an error or a slow reply shows nothing, and no "coming soon" text). */
export function SimilarUse({ id }: { id: string }) {
  const q = useApi(() => api.similarUse(id), [id]);
  const d = q.data;
  if (q.state === "error" || !d || d.status !== "ready") return null;
  return (
    <section className="card" aria-labelledby="su-h">
      <h2 id="su-h">{d.heading}</h2>
      <Disclosure title="Show suggestions">
      <p className="small">{d.note}</p>
      {d.combination_note && <p className="small muted">{d.combination_note}</p>}
      {d.groups.map((g) => (
        <div key={g.ingredient} className="similar-group">
          <h3>Compared on: {g.ingredient}</h3>
          <p className="small muted">
            {g.query_passages} Indications {g.query_passages === 1 ? "passage" : "passages"} from {g.query_labels} US{" "}
            {g.query_labels === 1 ? "label" : "labels"}
          </p>
          {g.note && <p className="small">{g.note}</p>}
          {g.suggestions.length > 0 && (
            <ol className="similar-list">
              {g.suggestions.map((s) => (
                <Suggestion key={s.ingredient} s={s} />
              ))}
            </ol>
          )}
        </div>
      ))}
      </Disclosure>
    </section>
  );
}
