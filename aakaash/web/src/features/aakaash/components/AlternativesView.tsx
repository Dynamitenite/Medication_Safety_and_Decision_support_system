import { lazy, Suspense, useState } from "react";
import { Link } from "react-router-dom";
import type { AlternativeBrand, BrandAlternativesResponse, BrandRow } from "../api";
import { Disclosure } from "./Disclosure";
import { Sticker } from "./Sticker";
import { FormTag } from "./viz/icons";

const PriceChart = lazy(() => import("./viz/PriceChart"));

const SHOW = 5;

export const rupees = (n: number | null | undefined) =>
  n == null ? "price not stated" : `₹${n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

function priceDiff(d: number | null) {
  if (d == null) return null;
  if (d === 0) return "same price";
  return d < 0 ? `${rupees(-d)} less` : `${rupees(d)} more`;
}

function AltRow({ a, showForm }: { a: AlternativeBrand; showForm?: boolean }) {
  const diff = priceDiff(a.price_difference);
  // one status badge per row, the most important one; the pack size is already in the text
  const status = a.discontinued
    ? "Discontinued"
    : a.composition_unclear
      ? "Composition unclear"
      : a.composition_incomplete || a.composition_conflict
        ? "Composition may be incomplete"
        : showForm
          ? `Form: ${a.form_family}`
          : null;
  return (
    <li>
      <span>
        <Link to={`/medicine/${a.id}`}>{a.name}</Link>
        <FormTag family={a.form_family} />
        <span className="small muted"> · {a.manufacturer ?? "manufacturer not stated"} · {a.pack_size}</span>
      </span>
      <span className="alt-price">
        {rupees(a.price)}
        {diff && <span className="small muted"> · {diff}</span>}
      </span>
      {status && (
        <span className="alt-tags">
          <Sticker wrap={status !== "Discontinued"}>{status}</Sticker>
        </span>
      )}
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
          {all ? "Show fewer" : `Show all ${rows.length}`}
        </button>
      )}
    </>
  );
}

export function Alternatives({ id, data, showDisc, setShowDisc, selected }: { id: string; data: BrandAlternativesResponse; showDisc: boolean; setShowDisc: (v: boolean) => void; selected?: BrandRow }) {
  const unknownForm = data.form_family === "unknown";
  const chart = (
    <Suspense fallback={<p className="muted" role="status">Loading price chart…</p>}>
      <PriceChart alts={data.same.map(a => ({id:a.id,name:a.name,manufacturer:a.manufacturer,pack_size:a.pack_size,price:a.price,discontinued:a.discontinued,different_pack_size:a.different_pack_size}))} selected={selected ? {id: selected.id,name: selected.name,manufacturer: selected.manufacturer,pack_size: selected.pack_size,price: selected.price} : null} total={data.same_total} />
    </Suspense>
  );
  return (
    <>
      <p>
        <strong>{data.note}</strong>
      </p>
      <h3>
        Cheapest with the same ingredients, strength and form {!unknownForm && <span className="small muted">({data.form_family})</span>}
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
      <Disclosure title="More options and details" className="alt-more">
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
        <div className="alt-counts" aria-label="Alternative group counts">
          <span>Same form <strong>{data.same_total}</strong></span><span>Different form <strong>{data.different_form_total}</strong></span>
          <span>Form not stated <strong>{data.form_not_stated_total}</strong></span><span>Composition unclear <strong>{data.unclear_total}</strong></span>
        </div>
        {data.same_total > 0 && chart}
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
      </Disclosure>
    </>
  );
}
