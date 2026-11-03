import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { Alternatives as AlternativesView, rupees } from "../components/AlternativesView";
import { Disclaimer } from "../components/Disclaimer";
import { Skeleton } from "../components/LabelTabs";
import { MedicineSearch } from "../components/MedicineSearch";
import { ErrorBox, NotReadyBox } from "../components/Panel";
import { SimilarUse } from "../components/SimilarUse";
import { Sticker } from "../components/Sticker";
import { useApi } from "../useApi";

function Selected({ id, showDisc, setShowDisc }: { id: string; showDisc: boolean; setShowDisc: (v: boolean) => void }) {
  const med = useApi(() => api.brand(id), [id]);
  const alt = useApi(() => api.brandAlternatives(id, showDisc), [id, showDisc]);
  if (med.state === "error") return <ErrorBox message={med.message} onRetry={med.reload} />;
  if (!med.data) return <Skeleton lines={4} />;
  if (med.data.status === "not_ready" || !med.data.brand) return <NotReadyBox reason={med.data.reason} fix={med.data.fix} />;
  const b = med.data.brand;
  return (
    <>
      <section className="card" aria-labelledby="sel-h">
        <div className="card-head">
          <h2 id="sel-h">{b.name}</h2>
          {b.discontinued && <Sticker>Discontinued</Sticker>}
        </div>
        <p className="small muted">
          {b.manufacturer ?? "manufacturer not stated"} · {b.pack_size || "pack size not stated"} · {rupees(b.price)} per pack · form:{" "}
          {b.form_family === "unknown" ? "not stated" : b.form_family} · <Link to={`/medicine/${b.id}`}>Medicine page</Link>
        </p>
        <ul className="ing-chips" aria-label="Ingredients and strength">
          {med.data.ingredient_details.map((x, i) => (
            <li key={i} className="ing-chip">
              <strong>{x.name}</strong>
              <span>{x.strength ?? "strength not stated"}</span>
            </li>
          ))}
        </ul>
      </section>
      <section className="card" aria-labelledby="alt-h" aria-busy={!alt.data}>
        <h2 id="alt-h">Other brands</h2>
        {alt.state === "error" && <ErrorBox message={alt.message} onRetry={alt.reload} />}
        {!alt.data && alt.state !== "error" && <Skeleton lines={3} />}
        {alt.data?.status === "not_ready" && <NotReadyBox reason={alt.data.reason} fix={alt.data.fix} />}
        {alt.data?.status === "ready" && <AlternativesView id={id} data={alt.data} showDisc={showDisc} setShowDisc={setShowDisc} selected={b} />}
        <Disclaimer />
      </section>
      <SimilarUse id={id} />
    </>
  );
}

/** Pick a medicine, then see other brands with the same ingredients, strength and form, by price. */
export function Alternatives() {
  const [params, setParams] = useSearchParams();
  const id = params.get("id") ?? "";
  const showDisc = params.get("disc") === "1";
  const [q, setQ] = useState("");
  const set = (patch: Record<string, string>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(patch)) v ? next.set(k, v) : next.delete(k);
    setParams(next);
  };
  return (
    <>
      <h1>Alternative medicines</h1>
      <p className="lead">Choose a medicine to see other brands with the same ingredients, and the price of each.</p>
      <section className="card">
        <MedicineSearch
          large
          autoFocus={!id}
          label="Find a medicine"
          placeholder="Try “Dolo 650” or an ingredient such as paracetamol"
          value={q}
          onValueChange={setQ}
          onSelect={(s) => set({ id: s.id, disc: "" })}
          clearOnSelect
        />
      </section>
      {id && <Selected key={id} id={id} showDisc={showDisc} setShowDisc={(v) => set({ disc: v ? "1" : "" })} />}
    </>
  );
}
