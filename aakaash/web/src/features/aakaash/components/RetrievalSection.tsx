import { api } from "../api";
import { useApi } from "../useApi";
import { ErrorBox, fmt, KeyValues, LoadingBox, NotReadyBox } from "./Panel";

const mb = (n: number | null | undefined) => (n == null ? "–" : `${(n / 1e6).toFixed(1)} MB`);

/** How label search and "Medicines with similar uses" work. Every count comes from the index manifest. */
export function RetrievalSection() {
  const q = useApi(api.indexSummary);
  const d = q.data?.status === "ready" ? q.data : null;
  return (
    <section className="card" aria-labelledby="ret-h">
      <h2 id="ret-h">Label search and similar uses</h2>
      {q.state === "loading" && !q.data && <LoadingBox what="index summary" />}
      {q.state === "error" && <ErrorBox message={q.message} onRetry={q.reload} />}
      {q.data?.status === "not_ready" && <NotReadyBox reason={q.data.reason} fix={q.data.fix} />}
      <h3>How retrieval works</h3>
      <ol>
        <li>
          <strong>Chunking.</strong> Each section of each US label is cut on its own, never across sections, into windows of
          {d ? ` ${d.chunk_size}` : " 512"} {d?.chunk_unit ?? "whitespace words"} that overlap by {d ? d.chunk_overlap : 64}. Section order and
          names come from the label's own LOINC section codes.
        </li>
        <li>
          <strong>Encoder.</strong> Each chunk becomes a vector. The working encoder is TF-IDF (word overlap, <em>not deep learning</em>). A
          sentence-transformers option (BAAI/bge-small-en-v1.5, set ENCODER=sbert) is written but <strong>not built</strong>: a CPU build takes
          about 6 hours, so no sbert index exists and nothing has been measured for it. A chunk longer than that model's limit would be cut into
          overlapping windows and score as its best window.
        </li>
        <li>
          <strong>Cosine similarity.</strong> Vectors are length-normalised, so the dot product between a query and a chunk is their cosine
          similarity. Results are ranked by that score only. There are no hand-set boosts and no re-ranking.
        </li>
        <li>
          <strong>Evidence, not answers.</strong> Search shows the passage, its section, its US label, form and route, and the score. Nothing is
          generated. Dosage text from a label of another form or route is not shown.
        </li>
      </ol>
      {d && (
        <>
          <h3>Label text coverage</h3>
          <KeyValues
            items={[
              ["Labels indexed", fmt(d.labels)],
              ["Chunks", fmt(d.chunks)],
              ["Release files loaded", d.parts_loaded.join(", ") || "none"],
              ["Active encoder", `${d.active_encoder_label}${d.is_deep_learning ? "" : " — baseline"}`],
              ["Encoders built", d.encoders_built.join(", ")],
              ["Vectors", `${fmt(d.vectors)}${d.dimension ? ` × ${d.dimension} dimensions` : " non-zero values"} · ${mb(d.vector_bytes)}`],
              ["Encoder build time", d.build_seconds == null ? "–" : `${d.build_seconds.toLocaleString("en-US")} s`],
            ]}
          />
          <div className="table-wrap">
            <table>
              <caption className="small muted">Chunks per section</caption>
              <thead>
                <tr>
                  <th scope="col">Section</th>
                  <th scope="col">Chunks</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(d.chunks_per_section).map(([k, v]) => (
                  <tr key={k}>
                    <th scope="row">{k.replace(/_/g, " ")}</th>
                    <td>{fmt(v)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="small muted">
            All text is US label text from DailyMed (US FDA). Only the release files listed above are indexed; a later release file needs a
            rebuild (scripts/build_index.py).
          </p>
        </>
      )}
      <h3>Medicines with similar uses</h3>
      <p>
        For each ingredient of the selected medicine, its Indications passages are compared with the Indications passages of every other
        ingredient that has a US label. An ingredient's score is the highest cosine similarity over all passage pairs. The same ingredient,
        ingredients sharing an active moiety, and the medicine's own ingredients are left out. Brands shown are in the same dosage-form family,
        not discontinued and without an unclear composition; single-ingredient brands come first, then the cheapest.
      </p>
      <p>Limits:</p>
      <ul>
        <li>Similar uses do not mean the medicines are interchangeable. The screen says so and never calls one a substitute.</li>
        <li>
          A very generic or boilerplate indication (for example the blood-pressure paragraph shared by many antihypertensive labels) can match many
          medicines, so a high score can reflect shared wording rather than a shared use. When the supporting sentence is carried by 5 or more
          ingredients the result is marked "Generic wording"; it is flagged, not hidden. No minimum similarity is set.
        </li>
        <li>Only the loaded release files are searched, so a medicine whose US label is not loaded cannot be suggested.</li>
        <li>Line breaks are lost when a section is chunked, so a "sentence" can run on; it is cut at 60 words with an ellipsis.</li>
      </ul>
      <h3>Evaluation status</h3>
      <p>
        There are no labelled relevance judgements. Only a <strong>proxy check</strong> exists for label search (does a label of the right
        ingredient, in the right section, appear in the top 5?), and it is not a relevance judgement. For similar uses, the top suggestions for
        well-known ingredients are printed for a pharmacist to read; none is marked right or wrong. Recall@10 and MRR are reported only when
        pharmacist-judged pairs are added. No accuracy is claimed. Scripts: scripts/eval_retrieval.py, scripts/eval_similar_use.py.
      </p>
    </section>
  );
}
