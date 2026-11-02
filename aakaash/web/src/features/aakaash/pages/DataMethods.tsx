import { PatientPicker } from "../components/PatientPicker";
import { RulesSection } from "../components/RulesSection";

export function DataMethods() {
  return (
    <>
      <h1>Data &amp; methods</h1>
      <p className="lead">Where the information in this app comes from, and what it can and cannot tell you.</p>

      <RulesSection />

      <section className="card" aria-labelledby="prov-h">
        <h2 id="prov-h">APPMS interaction-rule dataset</h2>
        <p>
          The interaction rules come from APPMS (IEEE DataPort, DOI 10.21227/9er6-w543, “Tamil Nadu &amp; Kerala Synthetic Medication
          Safety Dataset”). It is a <strong>synthetic dataset</strong>: every patient and medication record is fictional, and the
          interaction labels are produced by nine starter rules, each citing a drug-label or FDA source category. It is not clinically
          validated.
        </p>
        <ul>
          <li>The labels are a pure function of those nine rules, so no model is trained or scored on this data.</li>
          <li>It is used only as a source of interaction rules and severity, as sample patients for testing, and to check coverage of later features.</li>
          <li><strong>“No rule matched” is not proof of safety.</strong> The rule list is small, so most real combinations are simply unknown to it.</li>
          <li>Severity is a simplified educational label. Real risk depends on dose, duration, kidney and liver function, age and clinical context.</li>
          <li>The counts above are computed by the server from the files each time the page loads.</li>
        </ul>
      </section>

      <section className="card" aria-labelledby="pp-h">
        <h2 id="pp-h">Sample patients</h2>
        <p className="panel-hint">Fictional patients for trying the app. Pick one to see the profile and medicine list.</p>
        <PatientPicker />
      </section>
    </>
  );
}
