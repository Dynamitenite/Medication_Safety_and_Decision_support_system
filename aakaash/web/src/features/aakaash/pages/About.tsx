import { ErrorBox, LoadingBox } from "../components/Panel";
import { Sticker } from "../components/Sticker";
import { useStatus } from "../StatusContext";

const FROM_REVIEW = "FROM BASELINE REVIEW (ICMLAS 2025)";

const REQUIREMENTS: { id: string; text: string; where: string; use: string }[] = [
  {
    id: "R1",
    text: "Analyse a patient's medication profile and alert the clinician to interactions, contraindications, allergies and side effects.",
    where: "§IV-C; §III-E",
    use: "Personalized Alert (interaction evidence only for now; the allergy and contraindication checks are listed as coming soon).",
  },
  {
    id: "R2",
    text: "Explainability: show decision rationales and visual explanations, not a bare label.",
    where: "§V-C; §VI-E; §VII-A",
    use: "Evidence cards with label, section and score; highlighted words behind an interaction prediction.",
  },
  {
    id: "R3",
    text: "Privacy and security matter.",
    where: "§V-A",
    use: "This prototype stores no patient data on the server: the profile travels in the request body and there is no database. See Limitations.",
  },
  {
    id: "R4",
    text: "FHIR interoperability is a future direction.",
    where: "§VII-B names HL7 FHIR; §V-D discusses legacy-system integration and standard formats without naming it",
    use: "Not implemented. Listed under Future work.",
  },
  {
    id: "R5",
    text: "A user-friendly interface.",
    where: "Abstract; §VII-A (interactive visualizations)",
    use: "This web interface.",
  },
];

export function About() {
  const q = useStatus();
  return (
    <>
      <h1>About</h1>
      <p className="notice" role="note">
        <strong>Research prototype. Decision support only. Not medical advice.</strong> Nothing here replaces the judgement of a
        pharmacist or doctor.
      </p>

      <section className="card">
        <h2>What this is</h2>
        <p>
          A prototype for two subareas of the project “AI-Powered Personalized Medication Safety &amp; Decision Support System”
          (Group 4, course 24RM604, with Selvam Medicals):
        </p>
        <ul>
          <li><strong>A.</strong> Medicine information retrieval and generic alternative recommendation (cosine-similarity retrieval over drug-label text).</li>
          <li><strong>B.</strong> Medication safety risk detection and personalized alert generation (drug-pair interaction type from text, with explanation).</li>
        </ul>
        <p>The data are DailyMed prescription labels, the DDI Extraction 2013 corpus and TAC 2017 labels. The Dashboard shows what is actually loaded.</p>
      </section>

      <section className="card">
        <h2>Architecture</h2>
        <p>The team's six-stage design. This app covers the stages marked below; the patient profile travels in the request body.</p>
        {q.state === "loading" && !q.data && <LoadingBox what="stages" />}
        {q.state === "error" && <ErrorBox message={q.message} onRetry={q.reload} />}
        {q.data && (
          <ol className="stages">
            {q.data.stages.map((s) => (
              <li key={s.number} className={s.in_scope ? "in-scope" : ""}>
                <span className="stage-no">Stage {s.number}</span> <span className="stage-name">{s.name}</span>
                {s.in_scope ? <Sticker>Covered here</Sticker> : <span className="muted small">Not covered here</span>}
              </li>
            ))}
          </ol>
        )}
      </section>

      <section className="card">
        <h2>Baseline paper and the requirements taken from it</h2>
        <p>
          Yesankar, Puri and Gote, “AI-Powered Clinical Decision Support Systems (CDSS): Challenges, Benefits, Applications, and Future
          Directions,” ICMLAS 2025, DOI 10.1109/ICMLAS64557.2025.10969014. It is a <strong>review paper and contains no software
          architecture</strong>, so this app does not claim to follow one from it. Only five generic requirements are taken, labelled{" "}
          <Sticker>{FROM_REVIEW}</Sticker>:
        </p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th scope="col">No.</th><th scope="col">Requirement</th><th scope="col">Where in the paper</th><th scope="col">How this prototype uses it</th></tr>
            </thead>
            <tbody>
              {REQUIREMENTS.map((r) => (
                <tr key={r.id}>
                  <th scope="row">{r.id}</th>
                  <td>{r.text}</td>
                  <td className="small">{r.where}</td>
                  <td className="small">{r.use}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="small muted">No reference from that paper's own reference list is cited.</p>
      </section>

      <section className="card">
        <h2>Limitations</h2>
        <ul>
          <li><strong>No patient data is stored on the server.</strong> There is no database and no login; a profile exists only in the request that carries it (requirement R3).</li>
          <li>The first retrieval encoder and interaction classifier are <strong>classical baselines</strong> (TF-IDF cosine similarity; TF-IDF with a linear model). They are not deep learning and not Focal Loss. Where they are used, the screen says so.</li>
          <li>The interaction classifier is trained on sentences from DrugBank and MedLine. Label text is a different kind of text, so accuracy on labels may be lower. This has not been measured.</li>
          <li>Only the DailyMed zips present in <code>data/dailymed_rx</code> are used; the Dashboard shows exactly which and how many labels.</li>
          <li>Alternatives are matched on the active moiety of the active ingredient. That groups products that share a moiety but are not interchangeable. A professional confirms any substitution.</li>
          <li>Allergy, contraindication, duplicate-therapy and disease-precaution checks and the full patient profile are not built (see the coming-soon entries).</li>
        </ul>
      </section>

      <section className="card">
        <h2>Future work</h2>
        <ul>
          <li>HL7 FHIR interoperability (baseline review §VII-B).</li>
          <li>User accounts and login, a database, and deployment.</li>
          <li>A transformer encoder for retrieval, and a BioBERT-based interaction model trained with Focal Loss, with Integrated Gradients for explanation.</li>
        </ul>
      </section>
    </>
  );
}
