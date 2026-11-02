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
        <li>It checks allergies by name only (see “Adding medicines” below). It does not check contraindications, duplicate therapy, disease precautions, dose, kidney or liver function.</li>
        <li>It does not read handwriting, and it never uploads or stores a prescription picture.</li>
        <li>It does not store anything for the interaction checker: the medicine list is sent with the request only. It does store what a signed-in person enters in their profile and medical history, in a local SQLite database with hashed passwords, and deleting the account removes it all.</li>
        <li>It does not merge its two checks into one score. The interaction rules and the label text are shown separately.</li>
        <li>Apart from reading a scanned prescription (the tesseract.js text-recognition model, run in the browser), it does not use a trained model for any result you see. The search is name matching; the checker and the risk analysis are rules plus sentences found in label text.</li>
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

/** Label sections used by the medicine details card. Shares were printed by scripts/build_names.py
 *  on 2026-11-02 over the 4,293 labels of dm_spl_release_human_rx_part6.zip (the only release file loaded). */
const DETAIL_SECTIONS: [string, string, string][] = [
  ["Indications and usage", "34067-9", "98.4%"],
  ["Boxed warning", "34066-1", "36.7%"],
  ["Dosage and administration", "34068-7", "98.4%"],
  ["Patient counselling information", "34076-0, 88436-1", "84.9%"],
  ["Patient information (Medication Guide, patient package insert, Patient Medication Information)", "42231-1, 42230-3, 68498-5", "50.3%"],
  ["Instructions for use", "59845-8", "5.9%"],
];

function AddingMedicines() {
  return (
    <section className="card" aria-labelledby="add-h">
      <h2 id="add-h">Adding medicines: scan, details and risk levels</h2>
      <h3>Scanning a prescription</h3>
      <ul>
        <li>Printed or typed prescriptions only. Handwriting is not supported.</li>
        <li>
          Text is read in the browser with tesseract.js 7.0.0 (English, LSTM engine). Its worker, engine and English model are served by
          this app from <code>/ocr/</code> (copied from the npm packages by <code>scripts/copy-ocr.mjs</code>), so reading makes no request
          to any other site. <strong>The picture never leaves the device and is not stored</strong>; no endpoint accepts an image.
        </li>
        <li>
          Each line is parsed on the device by fixed patterns (own rules, not from the papers): leading numbering and Tab./Cap./Syr./Inj.
          are removed; a strength needs a unit (mg, mcg, g, IU, %); frequency is read from OD, BD, BID, TDS, TID, QID, HS, SOS and 1-0-1
          style patterns; duration from “x 5 days”, “for 7 days” or “1 week” (a month is not turned into days); food timing from
          before or after food or meals, AC and PC. Anything else is left empty.
        </li>
        <li>
          Only the medicine name read from a line is sent to the medicine search, the same request as typing it. Up to three matches are
          shown, never a similar spelling, and none is pre-selected. Nothing is added until the person confirms each line.
        </li>
      </ul>
      <h3>Medicine details</h3>
      <p>
        The text is US label text for the same ingredient, quoted as published: the first few sentences, with the full text one click
        away. Nothing is summarised. The label is the one chosen by the dosage-form rule (same form first). Dosage and administration and
        the patient sections are <strong>not shown</strong> when the label is for another dosage form or route, for a combination
        product with different ingredients, for one ingredient alone when the medicine is a combination, or when the medicine&apos;s own
        form is unknown. The app then says no label in the same form is loaded and to ask a pharmacist. Indications and a boxed warning
        may still be shown, titled with the label&apos;s form and route.
      </p>
      <div className="table-wrap">
        <table>
          <caption>Label sections used, their LOINC codes, and the share of loaded labels that have each one</caption>
          <thead><tr><th scope="col">Section</th><th scope="col">LOINC code</th><th scope="col" className="num">Labels with it</th></tr></thead>
          <tbody>
            {DETAIL_SECTIONS.map(([name, code, share]) => (
              <tr key={code}><th scope="row">{name}</th><td>{code}</td><td className="num">{share}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
      <h3>Risk levels (app rule, not from the papers)</h3>
      <p>
        The new medicines are compared with every current medicine (taken now, or with no dates entered) and with each other, by
        ingredient, with the same interaction rules and label-text search as the checker. Levels shown are Medium, High and Critical. The
        names Critical and High follow the tier labels of P10 (Shakarbaev); how a level is assigned is our own rule:
      </p>
      <div className="table-wrap">
        <table>
          <caption>How each finding gets its level</caption>
          <thead><tr><th scope="col">Finding</th><th scope="col">Level shown</th></tr></thead>
          <tbody>
            <tr><th scope="row">Interaction rule tier Moderate</th><td>Medium</td></tr>
            <tr><th scope="row">Interaction rule tier High</th><td>High</td></tr>
            <tr><th scope="row">Interaction rule tier Critical</th><td>Critical</td></tr>
            <tr><th scope="row">Allergy match, severity recorded as mild</th><td>Medium</td></tr>
            <tr><th scope="row">Allergy match, severity moderate</th><td>High</td></tr>
            <tr><th scope="row">Allergy match, severity severe</th><td>Critical</td></tr>
            <tr><th scope="row">Allergy match, severity not known</th><td>High</td></tr>
          </tbody>
        </table>
      </div>
      <ul>
        <li>The overall level is the highest level found. There is no score. With no finding the app says: “No known interaction found in our rules. This does not mean the combination is safe.” It never says Safe or Low.</li>
        <li>Label-text sentences are shown as supporting evidence and never change the level. A shared ingredient is shown as a note without a level.</li>
        <li>
          Allergy matching is by name only: the allergen must equal an ingredient after normalisation and the approved synonyms (for
          example amoxycillin and amoxicillin), or appear as whole words in the ingredient name (penicillin matches penicillin G). Related
          medicines in the same class are not checked, so a penicillin allergy does not match amoxicillin.
        </li>
        <li>A Critical result needs “I have read this warning” before adding; the server checks this again. Nothing else blocks adding.</li>
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

function PendingModules() {
  const q = useStatus();
  const modules = q.data?.modules ?? [];
  if (modules.length === 0) return null;
  return (
    <section className="card" aria-labelledby="mods-h">
      <h2 id="mods-h">Modules not built yet</h2>
      <p className="panel-hint">
        Planned modules by their project names and design stages. They are not in the app menu; each opens by its address and says it is not built.
      </p>
      <ul>
        {modules.map((m) => (
          <li key={m.id}>
            <Link to={`/modules/${m.id}`}>{m.label}</Link>{" "}
            <span className="muted small">
              stage {m.stages.join(", ")} · id {m.id}
            </span>
          </li>
        ))}
      </ul>
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
      <AddingMedicines />
      <DailyMedPanel />
      <Rules />
      <Classifier />
      <DdiStatsPanel query={ddi} />
      {ddi.data?.status === "ready" && <DdiExamplesPanel labels={ddi.data.labels} />}
      <TacPanel />
      <SystemStatus />
      <PendingModules />

      <section className="card" aria-labelledby="pp-h">
        <h2 id="pp-h">Sample patients</h2>
        <p className="panel-hint">Fictional patients from the synthetic dataset. Pick one to see the profile and medicine list.</p>
        <PatientPicker />
      </section>

      <Background />
    </>
  );
}
