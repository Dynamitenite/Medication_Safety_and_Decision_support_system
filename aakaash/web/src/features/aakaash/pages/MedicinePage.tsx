import { useEffect, useState } from "react";
import { Link, Navigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api";
import type { AlternativeBrand, BrandAlternativesResponse, BrandResponse, IngredientDetail } from "../api";
import { Disclaimer } from "../components/Disclaimer";
import { LabelTabs, Skeleton } from "../components/LabelTabs";
import { ErrorBox, KeyValues, NotReadyBox } from "../components/Panel";
import { Sticker } from "../components/Sticker";
import { useApi } from "../useApi";

const SHOW = 10;

/** "Tablet, film coated · Oral", or the family inferred from the title when the label states no form. */
const labelForm = (l: { form: string | null; route: string | null; form_family: string; form_inferred: boolean }) => {
  if (l.form_inferred) return `${l.form_family} (inferred from title)`;
  return l.form ? (l.route ? `${l.form} · ${l.route}` : l.form) : "form not stated";
};
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export const rupees = (n: number | null | undefined) =>
  n == null ? "price not stated" : `₹${n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

function priceDiff(d: number | null) {
  if (d == null) return null;
  if (d === 0) return "same price";
  return d < 0 ? `${rupees(-d)} less` : `${rupees(d)} more`;
}

function IngredientChips({ items }: { items: IngredientDetail[] }) {
  return (
    <ul className="ing-chips" aria-label="Ingredients">
      {items.map((x, i) => (
        <li key={i} className="ing-chip">
          <strong>{x.name}</strong>
          <span>{x.strength ?? "strength not stated"}</span>
          {x.us_name && <span className="small">US name: {x.us_name}</span>}
        </li>
      ))}
    </ul>
  );
}

/** US label text for one ingredient, with a picker when several US labels carry it. */
function LabelSection({ ing, choice, onChoose, rule, note, formNote, formUnknownNote }: { ing: IngredientDetail; choice: string | null; onChoose: (id: string) => void; rule: string; note: string; formNote: string; formUnknownNote: string }) {
  const chosen = ing.labels.find((l) => l.set_id === choice) ?? ing.labels[0];
  const lab = useApi(() => (chosen ? api.label(chosen.set_id) : Promise.resolve(null)), [chosen?.set_id]);
  const selectId = `label-pick-${ing.key}`;
  return (
    <section className="card" aria-labelledby="label-h">
      <h2 id="label-h">Label text (US FDA) for {ing.name}</h2>
      <p className="small">{note}</p>
      {!chosen ? (
        <p>
          No US label is linked for <strong>{ing.name}</strong> in the labels currently loaded. Some ingredients sold in India are
          not approved in the US, so they have no US label.
        </p>
      ) : (
        <>
          {ing.combination_only && (
            <p className="small">
              <Sticker>Combination label</Sticker> Only labels of combination products carry this ingredient, so the text below also
              covers other ingredients.
            </p>
          )}
          <div className="label-pick">
            <label htmlFor={selectId} className="small muted">
              US label shown ({ing.labels.length} {ing.labels.length === 1 ? "label" : "labels"} for {ing.us_name ?? ing.name})
            </label>
            <select id={selectId} value={chosen.set_id} onChange={(e) => onChoose(e.target.value)} disabled={ing.labels.length < 2}>
              {ing.labels.map((l) => (
                <option key={l.set_id} value={l.set_id}>
                  {labelForm(l)} · {l.product || l.title} · {l.manufacturer ?? "manufacturer not stated"} · {l.sections} sections{l.default ? " (default)" : ""}
                </option>
              ))}
            </select>
          </div>
          <p className="small muted">{rule}</p>
          <p className="small">
            <Sticker>Form</Sticker> {labelForm(chosen)}
          </p>
          {ing.form_match === "none" && (
            <p className="small">
              <Sticker wrap>Different form</Sticker> {formNote}.
            </p>
          )}
          {ing.form_match === "brand_form_unknown" && (
            <p className="small">
              <Sticker wrap>Form unknown</Sticker> {formUnknownNote}
            </p>
          )}
          {lab.state === "error" && <ErrorBox message={lab.message} onRetry={lab.reload} />}
          {lab.state !== "error" && !lab.data && <Skeleton lines={8} />}
          {lab.data?.status === "not_ready" && <NotReadyBox reason={lab.data.reason} fix={lab.data.fix} />}
          {lab.data?.status === "ready" && (
            <>
              <p className="small muted">
                <Link to={`/label/${lab.data.set_id}`}>Open this US label on its own page</Link>
              </p>
              <LabelTabs med={lab.data} />
            </>
          )}
        </>
      )}
    </section>
  );
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

function Alternatives({ id, data, showDisc, setShowDisc }: { id: string; data: BrandAlternativesResponse; showDisc: boolean; setShowDisc: (v: boolean) => void }) {
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

function Secondary({ data }: { data: BrandResponse }) {
  if (!data.secondary_interactions.length) return null;
  return (
    <section className="card" aria-labelledby="sec-h">
      <h2 id="sec-h">Interactions listed with this product</h2>
      <p className="small muted">{data.secondary_source_label} Shown as listed.</p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">Other medicine</th>
              <th scope="col">Listed effect</th>
            </tr>
          </thead>
          <tbody>
            {data.secondary_interactions.map((x, i) => (
              <tr key={i}>
                <th scope="row">{x.drug}</th>
                <td>{x.effect || "not stated"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/** A brand from the catalogue: details, ingredients, US label text per ingredient, alternatives. */
export function MedicinePage() {
  const { id = "" } = useParams();
  if (UUID.test(id)) return <Navigate to={`/label/${id}`} replace />; // links from before the catalogue
  return <BrandPage id={id} />;
}

function BrandPage({ id }: { id: string }) {
  const [params, setParams] = useSearchParams();
  const showDisc = params.get("disc") === "1";
  const med = useApi(() => api.brand(id), [id]);
  const alt = useApi(() => api.brandAlternatives(id, showDisc), [id, showDisc]);
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [id]);
  const set = (patch: Record<string, string>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(patch)) v ? next.set(k, v) : next.delete(k);
    setParams(next, { replace: true });
  };

  if (med.state === "error") return <ErrorBox message={med.message} onRetry={med.reload} />;
  if (!med.data)
    return (
      <div className="card" aria-busy="true">
        <div className="skeleton skeleton-title" />
        <Skeleton lines={3} />
      </div>
    );
  if (med.data.status === "not_ready" || !med.data.brand) return <NotReadyBox reason={med.data.reason} fix={med.data.fix} />;
  const d = med.data;
  const b = d.brand!;
  const ingIx = Math.min(Number(params.get("ing") ?? 0) || 0, Math.max(d.ingredient_details.length - 1, 0));
  const ing = d.ingredient_details[ingIx];

  return (
    <>
      <p className="small">
        <Link to="/search">← Back to search</Link>
      </p>
      <div className="brand-head">
        <h1>{b.name}</h1>
        {b.discontinued && <Sticker>Discontinued</Sticker>}
      </div>
      <section className="card" aria-label="Medicine summary">
        <KeyValues
          items={[
            ["Manufacturer", b.manufacturer ?? "not stated"],
            ["Pack size", b.pack_size || "not stated"],
            ["Dosage form", b.form_family === "unknown" ? "not stated" : b.form_family],
            ["Price", <>{rupees(b.price)} per pack <span className="small muted">· {d.price_note}</span></>],
            ["Type", b.type || "not stated"],
          ]}
        />
        <h2 className="small muted">Composition</h2>
        <IngredientChips items={d.ingredient_details} />
        {b.composition_incomplete && !b.composition_unclear && (
          <p className="small">
            <Sticker wrap>Composition may be incomplete</Sticker> Only two ingredients are listed for this product. It may contain more.
          </p>
        )}
        {b.composition_unclear && (
          <p className="small">
            <Sticker wrap>Composition unclear</Sticker> The listed composition repeats an ingredient and may be wrong. Confirm with a
            pharmacist. Strengths are shown as listed and are not added up.
          </p>
        )}
        {b.composition_conflict && (
          <p className="small">
            <Sticker wrap>Check composition</Sticker> Our sources list two different compositions. Shown: {b.composition}. The other:{" "}
            {d.short_composition}.
          </p>
        )}
      </section>

      {ing ? (
        <>
          {new Set(d.ingredient_details.map((x) => x.key)).size > 1 && (
            <div className="seg" role="group" aria-label="Show US label text for">
              {d.ingredient_details.map((x, i) => d.ingredient_details.findIndex((y) => y.key === x.key) !== i ? null : (
                <button key={i} type="button" className="btn btn-secondary btn-sm" aria-pressed={i === ingIx}
                  onClick={() => set({ ing: i ? String(i) : "", label: "", tab: "", find: "" })}>
                  {x.name}
                </button>
              ))}
            </div>
          )}
          <LabelSection ing={ing} choice={params.get("label")} onChoose={(v) => set({ label: v, tab: "" })}
            rule={d.default_label_rule} note={d.label_note} formNote={d.form_note} formUnknownNote={d.form_unknown_note} />
        </>
      ) : (
        <section className="card">
          <p>No ingredient is recorded for this product, so no US label text can be shown.</p>
        </section>
      )}

      <section className="card" aria-labelledby="alt-h" aria-busy={!alt.data}>
        <h2 id="alt-h">Alternatives</h2>
        {alt.state === "error" && <ErrorBox message={alt.message} onRetry={alt.reload} />}
        {!alt.data && alt.state !== "error" && <Skeleton lines={3} />}
        {alt.data?.status === "not_ready" && <NotReadyBox reason={alt.data.reason} fix={alt.data.fix} />}
        {alt.data?.status === "ready" && (
          <Alternatives id={id} data={alt.data} showDisc={showDisc} setShowDisc={(v) => set({ disc: v ? "1" : "" })} />
        )}
        <Disclaimer />
      </section>

      <Secondary data={d} />
    </>
  );
}
