import { useState } from "react";
import { Link } from "react-router-dom";
import type { AlternativeBrand, BrandAlternativesResponse } from "../api";
import { Sticker } from "./Sticker";

const SHOW = 10;

export const rupees = (n: number | null | undefined) =>
  n == null ? "price not stated" : `₹${n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

function priceDiff(d: number | null) {
  if (d == null) return null;
  if (d === 0) return "same price";
  return d < 0 ? `${rupees(-d)} less` : `${rupees(d)} more`;
}

function AltRow({ a, showForm }: { a: AlternativeBrand; showForm?: boolean }) {
  const diff = priceDiff(a.price_difference);
  return (
    <li>
      <span>
        <Link to={`/medicine/${a.id}`}>{a.name}</Link>
        <span className="small muted"> · {a.manufacturer ?? "manufacturer not stated"} · {a.pack_size}</span>
      </span>
      <span className="alt-price">
        {rupees(a.price)}
        {diff && <span className="small muted"> · {diff}</span>}
      </span>
      <span className="alt-tags">
        {showForm && <Sticker>Form: {a.form_family}</Sticker>}
        {a.discontinued && <Sticker>Discontinued</Sticker>}
        {a.different_pack_size && <Sticker>Different pack size</Sticker>}
        {a.composition_unclear && <Sticker wrap>Composition unclear</Sticker>}
        {!a.composition_unclear && (a.composition_incomplete || a.composition_conflict) && <Sticker wrap>Composition may be incomplete</Sticker>}
      </span>
    </li>
  );
}

/** A list of alternative brands, cheapest first, with a Show-all toggle. */
function AltList({ rows, total, showForm }: { rows: AlternativeBrand[]; total: number; showForm?: boolean }) {
  const [all, setAll] = useState(false);
  const shown = all ? rows : rows.slice(0, SHOW);
  return (
    <>
      <p className="small muted">
        {total} {total === 1 ? "brand" : "brands"}, cheapest first.{total > rows.length && ` Showing the ${rows.length} cheapest.`}
      </p>
      <ul className="alt-rows">
        {shown.map((a) => (
          <AltRow key={a.id} a={a} showForm={showForm} />
        ))}
      </ul>
      {rows.length > SHOW && (
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => setAll(!all)}>
          {all ? "Show fewer" : `Show ${rows.length}`}
        </button>
      )}
    </>
  );
}

export function Alternatives({ id, data, showDisc, setShowDisc }: { id: string; data: BrandAlternativesResponse; showDisc: boolean; setShowDisc: (v: boolean) => void }) {
  const unknownForm = data.form_family === "unknown";
  return (
    <>
      <p>
        <strong>{data.note}</strong>
      </p>
      <p className="small muted">{data.price_note} Prices are per pack as listed; compare pack sizes.</p>
      {data.caveats.map((c) => (
        <p key={c} className="small">
          <Sticker wrap>Check</Sticker> {c}
        </p>
      ))}
      <label className="toggle">
        <input type="checkbox" checked={showDisc} onChange={(e) => setShowDisc(e.target.checked)} />
        Show discontinued
      </label>
      <h3>
        Same ingredients, strength and form {!unknownForm && <span className="small muted">({data.form_family})</span>}
      </h3>
      {data.same_total === 0 ? (
        <p className="muted">
          {data.composition_unclear
            ? "Not available: the listed composition of this product repeats an ingredient and may be wrong."
            : !data.strength_stated
            ? "Not available: the strength is not stated."
            : unknownForm
              ? "Not available: the dosage form of this product could not be determined."
              : "No other brand in our database has the same ingredients, strength and form."}
        </p>
      ) : (
        <AltList key={`${id}-${showDisc}-same`} rows={data.same} total={data.same_total} />
      )}
      {data.different_form_total > 0 && (
        <div className="alt-other-form">
          <h3>Same ingredients, different form</h3>
          <p className="small muted">Same ingredients and strength, but not the same dosage form. Ask a pharmacist before using one in place of the selected product.</p>
          <AltList key={`${id}-${showDisc}-diff`} rows={data.different_form} total={data.different_form_total} showForm />
        </div>
      )}
      {data.form_not_stated_total > 0 && (
        <div className="alt-other-form">
          <h3>Form not stated</h3>
          <p className="small muted">Same ingredients and strength, but the dosage form could not be determined from the name or pack label.</p>
          <AltList key={`${id}-${showDisc}-unk`} rows={data.form_not_stated} total={data.form_not_stated_total} />
        </div>
      )}
      {data.unclear_total > 0 && (
        <div className="alt-other-form">
          <h3>Composition unclear</h3>
          <p className="small muted">
            These products have the same ingredient but their listed composition repeats an ingredient and may be wrong. They are not
            offered as matches. Confirm with a pharmacist.
          </p>
          <AltList key={`${id}-${showDisc}-unclear`} rows={data.unclear} total={data.unclear_total} />
        </div>
      )}
      <h3>Same ingredients, different strength</h3>
      {data.composition_unclear ? (
        <p className="muted">Not available: the listed composition of this product repeats an ingredient and may be wrong.</p>
      ) : data.other_strength.length === 0 ? (
        <p className="muted">None in our database.</p>
      ) : (
        <ul className="groups">
          {data.other_strength.map((g) => (
            <li key={g.composition}>
              <details>
                <summary>
                  <span>{g.composition}</span>
                  <span className="small muted">
                    {g.brands_total} {g.brands_total === 1 ? "brand" : "brands"} · from {rupees(g.lowest_price)}
                  </span>
                </summary>
                <ul className="alt-rows">
                  {g.brands.map((a) => (
                    <AltRow key={a.id} a={a} />
                  ))}
                </ul>
                {g.brands_total > g.brands.length && <p className="small muted">The {g.brands.length} cheapest are shown.</p>}
              </details>
            </li>
          ))}
        </ul>
      )}
      {data.other_strength_groups_total > data.other_strength.length && (
        <p className="small muted">Showing {data.other_strength.length} of {data.other_strength_groups_total} strengths.</p>
      )}
    </>
  );
}
