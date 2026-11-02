import { Link } from "react-router-dom";
import { api } from "../api";
import type { AppmsSummaryResponse } from "../api";
import { Background } from "../components/Background";
import { CatalogueSection } from "../components/CatalogueSection";
import { DdiExamplesPanel, DdiStatsPanel } from "../components/DdiPanels";
import { DailyMedPanel, TacPanel } from "../components/LabelStatsPanels";
import { ErrorBox, fmt, LoadingBox } from "../components/Panel";
import { PatientPicker } from "../components/PatientPicker";
import { RulesSection } from "../components/RulesSection";
import { StatusTable } from "../components/StatusTable";
import { useStatus } from "../StatusContext";
import { useApi } from "../useApi";

/** Release files DailyMed publishes for human prescription labels (part1 to part6). */
const DAILYMED_PARTS = 6;

function Sources() {
  const q = useApi(api.dailymedStats);
  const d = q.data?.status === "ready" ? q.data : null;
  return (
    <section className="card" aria-labelledby="src-h">
      <h2 id="src-h">Where the information comes from</h2>
      <dl className="kv">
        <div>
          <dt>Medicine list (search, medicine page, alternatives)</dt>
          <dd>
            An Indian medicine catalogue from a public GitHub dataset (details in the next section): brand names, manufacturers,
            composition, pack sizes and prices.
          </dd>
        </div>
        <div>
          <dt>US label text (per ingredient)</dt>
          <dd>
            Prescription drug labels from DailyMed (US National Library of Medicine), read from its release zip files. The text shown
            is the label text as published; nothing is generated or rewritten. Indian brands are linked to these labels by ingredient.
            {d && (
              <>
                {" "}
                <strong>Coverage: {d.parts_loaded.length} of {DAILYMED_PARTS} release files are loaded</strong> ({fmt(d.labels_parsed)}{" "}
                labels{d.is_sample ? ", a sample run" : ""}). A medicine whose label is in a release file that is not loaded cannot be
                found, and the app then says it is not in its database.
              </>
            )}
          </dd>
        </div>
        <div>
          <dt>Interaction rules</dt>
          <dd>
            Taken from the APPMS dataset (IEEE DataPort, DOI 10.21227/9er6-w543, “Tamil Nadu &amp; Kerala Synthetic Medication Safety
            Dataset”). <strong>That dataset is synthetic</strong>: its patients and medication records are fictional, and its interaction
            labels come from nine starter rules, each citing a drug-label or FDA source category. It is not clinically validated.
          </dd>
        </div>
        <div>
          <dt>Interaction-type sentences</dt>
          <dd>The DDI Extraction 2013 corpus (DrugBank and MedLine sentences), kept to train and test a drug-pair classifier. No screen uses a classifier yet.</dd>
        </div>
        <div>
          <dt>Adverse-reaction labels</dt>
          <dd>TAC 2017 annotated labels, used only to check that section parsing works.</dd>
        </div>
      </dl>
    </section>
  );
}

function DoesNot() {
  return (
    <section className="card" aria-labelledby="not-h">
      <h2 id="not-h">What the app does not do</h2>
      <ul>
        <li>It does not diagnose, prescribe or give dosing advice, and it is not a medical device.</li>
        <li>It does not check allergies, contraindications, duplicate therapy, disease precautions, dose, kidney or liver function.</li>
        <li>It does not store patient data: a medicine list is sent with the request only, and there is no database or login.</li>
        <li>It does not merge its two checks into one score. The interaction rules and the label text are shown separately.</li>
        <li>It does not use a trained model for any result you see. The search is name matching; the checker is rules plus sentences found in label text.</li>
      </ul>
      <h2>Limitations</h2>
      <ul>
        <li>
          <strong>No known interaction in the rules does not mean a combination is safe.</strong> The rule list is small (nine rules), so
          most real combinations are simply unknown to it.
        </li>
        <li>Severity is a simplified label. Real risk depends on dose, duration, kidney and liver function, age and clinical context.</li>
        <li>Label text matching finds sentences that name the other medicine. It misses class-level mentions (for example “anticoagulants”) and cannot judge clinical importance.</li>
        <li>Alternatives are other brands with the same full set of ingredients, the same strengths as written and the same dosage form family (worked out from the pack label and name: oral solid, oral liquid, injectable and so on). Products in another form are listed apart, and products whose form could not be determined are listed as “Form not stated”. They are not necessarily interchangeable (release form, inactive ingredients and quality can differ). A pharmacist confirms any substitution.</li>
        <li>The checker treats a medicine as its set of ingredients. The label-text check reads the Drug Interactions section of one US label per ingredient (the one with the most label sections), not every US label.</li>
        <li>Matching a sample patient's drug name to labels uses the active-ingredient name, ignoring a trailing salt or hydrate word, plus the exact name equivalences listed below (for example Salbutamol and albuterol). Nothing is matched by similar spelling.</li>
        <li>The interaction rules were not trained or scored against; the synthetic labels are a pure function of nine rules.</li>
      </ul>
    </section>
  );
}

function MatchNumbers({ s }: { s: AppmsSummaryResponse }) {
  const m = s.match;
  if (!m) return <p className="small muted">Name matching needs the medicine index, which is not available.</p>;
  return (
    <>
      <h3>Matching sample-patient medicines to labels</h3>
      <p>
        <strong>{fmt(m.rows_matched)} of {fmt(m.medication_rows)}</strong> medication rows match at least one label by active ingredient (
        {m.names_matched} of {m.drug_names} distinct drug names).
      </p>
      {m.unmatched.length > 0 ? (
        <div className="table-wrap">
          <table>
            <caption>Drug names with no matching label (not guessed)</caption>
            <thead><tr><th scope="col">Drug name</th><th scope="col" className="num">Rows</th></tr></thead>
            <tbody>
              {m.unmatched.map((u) => (
                <tr key={u.drug_name}><th scope="row">{u.drug_name}</th><td className="num">{fmt(u.rows)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="small muted">Every drug name matched.</p>
      )}
    </>
  );
}

function Rules() {
  const q = useApi(() => api.appmsSummary());
  return (
    <>
      <RulesSection />
      {q.data?.status === "ready" && (
        <section className="card" aria-labelledby="match-h">
          <h2 id="match-h">Sample patients and labels</h2>
          <MatchNumbers s={q.data} />
        </section>
      )}
    </>
  );
}

function Classifier() {
  const q = useStatus();
  const c = q.data?.components.find((x) => x.id === "ddi_model");
  return (
    <section className="card" aria-labelledby="clf-h">
      <h2 id="clf-h">Interaction-type classifier</h2>
      {q.state === "loading" && !q.data && <LoadingBox what="classifier status" />}
      {q.state === "error" && <ErrorBox message={q.message} onRetry={q.reload} />}
      {c &&
        (c.status === "ready" ? (
          <p>A trained classifier file is present. Its measured metrics are in its metrics file; they are not shown on any screen yet, and no result in the app comes from it.</p>
        ) : (
          <p>
            <strong>No classifier has been trained, so there are no accuracy figures.</strong> Precision, recall and F1 per class will be
            shown here when a training run has produced them. Any figure from a paper is quoted only as that paper's result, never as ours.
          </p>
        ))}
    </section>
  );
}

function SystemStatus() {
  const q = useStatus();
  return (
    <section className="card" aria-labelledby="system-status-h">
      <h2 id="system-status-h">System components</h2>
      <p className="panel-hint">A component is ready only when its files exist on disk.</p>
      {q.state === "loading" && !q.data && <LoadingBox what="system status" />}
      {q.state === "error" && <ErrorBox message={q.message} onRetry={q.reload} />}
      {q.data && <StatusTable components={q.data.components} />}
    </section>
  );
}

export function DataMethods() {
  const ddi = useApi(api.ddiStats);
  return (
    <>
      <h1>Data &amp; methods</h1>
      <p className="lead">
        Where the information in this app comes from, how far it reaches, and what it cannot tell you. This page uses the project's
        research wording; the rest of the app does not. The component-by-component record of what is taken from papers is on the{" "}
        <Link to="/about/trace">paper trace</Link> page.
      </p>

      <Sources />
      <CatalogueSection />
      <DoesNot />
      <DailyMedPanel />
      <Rules />
      <Classifier />
      <DdiStatsPanel query={ddi} />
      {ddi.data?.status === "ready" && <DdiExamplesPanel labels={ddi.data.labels} />}
      <TacPanel />
      <SystemStatus />

      <section className="card" aria-labelledby="pp-h">
        <h2 id="pp-h">Sample patients</h2>
        <p className="panel-hint">Fictional patients from the synthetic dataset. Pick one to see the profile and medicine list.</p>
        <PatientPicker />
      </section>

      <Background />
    </>
  );
}
