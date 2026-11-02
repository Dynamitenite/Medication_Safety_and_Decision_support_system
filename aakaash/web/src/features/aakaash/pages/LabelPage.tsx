import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import type { AlternativesResponse } from "../api";
import { LabelTabs, Skeleton } from "../components/LabelTabs";
import { KeyValues, NotReadyBox, ErrorBox } from "../components/Panel";
import { Sticker } from "../components/Sticker";
import { useApi } from "../useApi";

function Alternatives({ data }: { data: AlternativesResponse }) {
  const [all, setAll] = useState(false);
  const shown = all ? data.alternatives : data.alternatives.slice(0, 20);
  if (!data.active_moieties.length)
    return <p className="muted">This label records no active ingredient, so no same-ingredient labels can be matched.</p>;
  return (
    <>
      <p className="small">{data.note}</p>
      <p className="small muted">
        Matched on: <strong>{data.active_moieties.join(" + ")}</strong>
        {data.active_moieties.length > 1 && " (combination: only labels with the same full set match)"}.{" "}
        {data.alternatives.length
          ? `${data.alternatives.length} product and manufacturer groups, ${data.total_labels} labels.`
          : "No other label has the same active ingredient in our database."}
      </p>
      {shown.length > 0 && (
        <ul className="alt-list">
          {shown.map((a) => (
            <li key={a.set_id}>
              <Link to={`/label/${a.set_id}`}>
                <span className="alt-name">{a.product}</span>
                <span className="small muted">
                  {a.form ?? "form not stated"} · {a.manufacturer ?? "manufacturer not stated"}
                  {a.label_count > 1 ? ` · ${a.label_count} labels` : ""}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
      {data.alternatives.length > 20 && (
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => setAll(!all)}>
          {all ? "Show fewer" : `Show all ${data.alternatives.length}`}
        </button>
      )}
    </>
  );
}

/** One US label (DailyMed) by set id: summary, section text and other labels with the same active moiety. */
export function LabelPage() {
  const { setId = "" } = useParams();
  const med = useApi(() => api.label(setId), [setId]);
  const alt = useApi(() => api.labelAlternatives(setId), [setId]);
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [setId]);

  let head: ReactNode;
  if (med.state === "error") head = <ErrorBox message={med.message} onRetry={med.reload} />;
  else if (!med.data) head = (
    <div className="card" aria-busy="true">
      <div className="skeleton skeleton-title" />
      <Skeleton lines={3} />
    </div>
  );
  else if (med.data.status === "not_ready") head = <NotReadyBox reason={med.data.reason} fix={med.data.fix} />;
  else {
    const m = med.data;
    head = (
      <>
        <h1>{m.products[0] ?? m.title}</h1>
        <section className="card" aria-label="Medicine summary">
          <KeyValues
            items={[
              ["Generic name", m.generic_names.join(", ") || "not stated on the label"],
              ["Manufacturer", m.manufacturer ?? "not stated on the label"],
              ["Dosage form and route", m.form ?? "not stated on the label"],
              ["Ingredients (as written on the label)", m.ingredients.join(", ") || "none recorded"],
              ["Active ingredient (used for matching)", m.active_moieties.join(", ") || "none recorded"],
              ...(m.products.length > 1 ? ([["Other product names", m.products.slice(1).join(", ")]] as [string, ReactNode][]) : []),
            ]}
          />
          <p className="small muted">
            <Sticker>Label id</Sticker> <code>{m.set_id}</code>
          </p>
        </section>
      </>
    );
  }

  return (
    <>
      <p className="small">
        <Link to="/">← Back to search</Link>
      </p>
      {head}
      <section className="card" aria-labelledby="label-h">
        <h2 id="label-h">Label text (US FDA)</h2>
        {med.data?.status === "ready" ? (
          <LabelTabs med={med.data} />
        ) : med.state !== "error" && !med.data ? (
          <Skeleton lines={8} />
        ) : null}
      </section>
      <section className="card" aria-labelledby="alt-h">
        <h2 id="alt-h">Other US labels with the same active ingredient</h2>
        {alt.state === "error" && <ErrorBox message={alt.message} onRetry={alt.reload} />}
        {!alt.data && alt.state !== "error" && <Skeleton lines={3} />}
        {alt.data?.status === "not_ready" && <NotReadyBox reason={alt.data.reason} fix={alt.data.fix} />}
        {alt.data?.status === "ready" && <Alternatives data={alt.data} />}
      </section>
    </>
  );
}
