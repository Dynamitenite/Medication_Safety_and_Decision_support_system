import { useStatus } from "../StatusContext";
import { ErrorBox, LoadingBox } from "./Panel";
import { Sticker } from "./Sticker";

const FROM_REVIEW = "FROM BASELINE REVIEW (ICMLAS 2025)";

const REQUIREMENTS: { id: string; text: string; where: string; use: string }[] = [
  {
    id: "R1",
    text: "Analyse a patient's medication profile and alert the clinician to interactions, contraindications, allergies and side effects.",
    where: "§IV-C; §III-E",
    use: "Interaction evidence in the checker only for now; allergy and contraindication checks are not built.",
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
    use: "Accounts are kept in a local SQLite database file on the server (aakaash/artifacts/app.db, never committed). Passwords are stored only as argon2id hashes. A sign-in is a random token in an httpOnly, SameSite=Lax cookie, signed with SESSION_SECRET; the server keeps only a hash of the token. Sign-in attempts are rate-limited inside the server process (5 failures in 15 minutes per email and address; this resets on restart). Every personal endpoint reads and writes only the signed-in person's rows, and Delete my data removes the account and all of its rows. The checker does not save the medicines sent to it. This is a prototype-grade store: no encryption at rest, no email verification and no password reset.",
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

/** Project background for the Data & methods page: what the project is, its design stages, the review paper it draws on. */
export function Background() {
  const q = useStatus();
  return (
    <>
      <section className="card">
        <h2>The project</h2>
        <p>
          This app is a research prototype for two subareas of the project “AI-Powered Personalized Medication Safety &amp; Decision
          Support System” (Group 4, course 24RM604, with Selvam Medicals):
        </p>
        <ul>
          <li><strong>A.</strong> Medicine information retrieval and generic alternative recommendation (planned: cosine-similarity retrieval over drug-label text; today the search is by name).</li>
          <li><strong>B.</strong> Medication safety risk detection and personalized alert generation (planned: drug-pair interaction type from text, with explanation; today the checker uses interaction rules and label text).</li>
        </ul>
        <p>The data are DailyMed prescription labels, the DDI Extraction 2013 corpus, TAC 2017 labels and an interaction-rule dataset. The sections above show what is actually loaded.</p>
      </section>

      <section className="card">
        <h2>Architecture</h2>
        <p>The team's six-stage design. This app covers the stages marked below; signed-in people keep a profile and medical history in the local database (see requirement R3 above); the checker itself receives its medicine list in the request body.</p>
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
              <tr><th scope="col">No.</th><th scope="col">Requirement</th><th scope="col">Where in the paper</th><th scope="col">How this app uses it</th></tr>
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
        <h2>Future work</h2>
        <ul>
          <li>HL7 FHIR interoperability (baseline review §VII-B).</li>
          <li>Deployment, a production database, encryption at rest, email verification and password reset for the accounts.</li>
          <li>A transformer encoder for retrieval, and a BioBERT-based interaction model trained with Focal Loss, with Integrated Gradients for explanation.</li>
        </ul>
      </section>
    </>
  );
}
