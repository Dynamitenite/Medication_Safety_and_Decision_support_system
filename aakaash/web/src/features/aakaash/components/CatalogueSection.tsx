import { api } from "../api";
import type { CatalogueSummaryResponse } from "../api";
import { ErrorBox, fmt, LoadingBox, NotReadyBox } from "./Panel";
import { useApi } from "../useApi";

const pct = (a: number, b: number) => (b ? `${((100 * a) / b).toFixed(1)}%` : "–");

function Body({ s }: { s: CatalogueSummaryResponse }) {
  const parts = s.dailymed_parts_loaded.join(", ") || "none";
  return (
    <>
      <dl className="kv">
        <div>
          <dt>Source</dt>
          <dd>
            {s.source}. Licence: {s.licence}. Original source of the data: {s.original_source}.
          </dd>
        </div>
        <div>
          <dt>Size</dt>
          <dd>
            {fmt(s.brands)} products, {fmt(s.distinct_ingredients)} distinct ingredients
          </dd>
        </div>
        <div>
          <dt>Age of the data</dt>
          <dd>
            The repository's data was about two years old when it was downloaded{s.file_date ? ` (${s.file_date})` : ""}. Prices,
            availability and discontinued status may be out of date.
          </dd>
        </div>
        <div>
          <dt>Discontinued products</dt>
          <dd>
            {fmt(s.discontinued)} products ({pct(s.discontinued, s.brands)}) are marked discontinued. They are listed last in search and
            marked; they are hidden from alternatives unless you choose “Show discontinued”.
          </dd>
        </div>
      </dl>

      <h3>Link to US labels (DailyMed)</h3>
      <p>
        <strong>
          {fmt(s.ingredients_linked)} of {fmt(s.distinct_ingredients)} ingredients ({pct(s.ingredients_linked, s.distinct_ingredients)})
        </strong>{" "}
        have at least one US label, with the labels currently loaded ({fmt(s.dailymed_labels_loaded)} labels from {parts}; DailyMed
        publishes six prescription release files). For {fmt(s.ingredients_linked_combination_only)} of them only a combination-product
        label exists. <strong>{fmt(s.brands_all_linked)} of {fmt(s.brands)} products ({pct(s.brands_all_linked, s.brands)})</strong>{" "}
        have a US label for every listed ingredient ({fmt(s.brands_complete_all_linked)} of {fmt(s.brands_complete)} among products whose
        composition is complete).
      </p>
      <ul>
        <li>
          Some ingredients sold in India have no US label because they are not approved in the US (for example aceclofenac, nimesulide
          or domperidone). Others are sold over the counter in the US and so are not among the prescription labels loaded. Others are
          in release files that are not loaded.
        </li>
        <li>
          Label text for an Indian brand is taken from a US label of the same ingredient. The brand itself is not in that source, and
          the US label may differ from the Indian brand in strength, formulation, approved uses and advice.
        </li>
        <li>
          An ingredient is linked when its name, after the equivalences listed below, equals a US label's ingredient name or active
          moiety, ignoring a trailing salt or hydrate word. A name is never reduced to a bare metal such as “sodium”, so sodium chloride
          and sodium citrate never link to each other. Nothing is matched by similar spelling.
        </li>
      </ul>

      <h3>Composition</h3>
      <ul>
        <li>
          For {fmt(s.from_full_composition)} products the full composition is listed. For the rest only two composition fields exist,
          each holding one ingredient.
        </li>
        <li>
          <strong>
            Composition may be incomplete for products with two listed ingredients: {fmt(s.composition_incomplete)} products (
            {pct(s.composition_incomplete, s.brands)}).
          </strong>{" "}
          Where the full composition is available, about three in ten such products have a third ingredient. These products carry a
          “composition may be incomplete” note, and an alternative is never shown as a complete match for them.
        </li>
        <li>For {fmt(s.composition_conflict)} products the two composition fields disagree; the fuller one is used and both are shown.</li>
        <li>
          <strong>Composition unclear: {fmt(s.composition_unclear)} products</strong> list the same ingredient more than once (for
          example paracetamol 300 mg and paracetamol 700 mg). The listed composition may be wrong. Strengths are shown as listed, never
          added up, and the data is not edited. Such a product is never offered as a match for another product and has no matches of its
          own; it appears only under “Composition unclear” for products with the same ingredient. The checker counts the ingredient once.
        </li>
        <li>Strengths are compared as written. A product whose strength is not stated is never offered as a same-strength alternative.</li>
        <li>Prices are per pack as listed{s.price_not_stated ? `; ${fmt(s.price_not_stated)} products list no price` : ""}. Prices may be out of date.</li>
      </ul>

      <h3>Interactions listed with a product</h3>
      <p>
        {fmt(s.secondary_interaction_rows)} products list other medicines they interact with. The origin of these lists is not stated.
        They are shown separately, marked “origin not stated”, and are never used to set a risk level or merged with the interaction
        rules or label text.
      </p>

      {s.top_unlinked.length > 0 && (
        <div className="table-wrap">
          <table>
            <caption>Most frequent ingredients with no US label in the labels loaded</caption>
            <thead>
              <tr>
                <th scope="col">Ingredient</th>
                <th scope="col" className="num">Products</th>
              </tr>
            </thead>
            <tbody>
              {s.top_unlinked.slice(0, 15).map((u) => (
                <tr key={u.name}>
                  <th scope="row">{u.name}</th>
                  <td className="num">{fmt(u.rows)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="table-wrap">
        <table>
          <caption>Name equivalences used (exact, never by similar spelling)</caption>
          <thead>
            <tr>
              <th scope="col">Name in the catalogue</th>
              <th scope="col">US name</th>
              <th scope="col">Kind</th>
              <th scope="col">Note</th>
            </tr>
          </thead>
          <tbody>
            {s.synonyms.map((r) => (
              <tr key={r.name}>
                <th scope="row">{r.name}</th>
                <td>{r.maps_to}</td>
                <td>{r.kind}</td>
                <td className="small">{r.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

/** The Indian medicine catalogue: source, size, link rates to US labels, caveats and the synonym list. */
export function CatalogueSection() {
  const q = useApi(api.catalogueSummary);
  return (
    <section className="card" aria-labelledby="cat-h">
      <h2 id="cat-h">Medicine catalogue (India)</h2>
      {q.state === "error" && <ErrorBox message={q.message} onRetry={q.reload} />}
      {!q.data && q.state !== "error" && <LoadingBox what="catalogue summary" />}
      {q.data?.status === "not_ready" && <NotReadyBox reason={q.data.reason} fix={q.data.fix} />}
      {q.data?.status === "ready" && <Body s={q.data} />}
    </section>
  );
}
