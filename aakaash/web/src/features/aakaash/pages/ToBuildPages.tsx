import { BaselineLabel } from "../components/BaselineLabel";
import { NeedsPage } from "../components/NeedsPage";
import { useStatus } from "../StatusContext";

export function MedicineInfo() {
  const enc = useStatus().data?.active_encoder;
  return (
    <NeedsPage
      title="Medicine Info"
      needs={["dailymed_data", "encoder", "index"]}
      intro={
        <>
          <p>
            Search for a medicine and see label text with the evidence it came from (label, section and similarity score), and
            the other medicines that have the same active ingredient. Information only.
          </p>
          <ul>
            <li>
              Retrieval uses cosine similarity over label chunks{enc ? <> (configured encoder: <strong>{enc}</strong>)</> : null}. The
              encoder in use will be shown beside every result.
            </li>
            <li>
              Alternatives are matched on the <strong>active moiety</strong>: “same active ingredient, matched on its active moiety”,
              not “same drug”. Alternatives are informational; a professional confirms any substitution.
            </li>
          </ul>
          {enc === "tfidf" && <BaselineLabel text="Baseline encoder: TF-IDF (cosine similarity, not deep learning)" />}
        </>
      }
    />
  );
}

export function InteractionRisk() {
  const clf = useStatus().data?.active_classifier;
  return (
    <NeedsPage
      title="Interaction Risk"
      needs={["ddi_data", "ddi_model"]}
      intro={
        <>
          <p>
            Paste a sentence, mark the two drugs, and see the predicted interaction type (effect, mechanism, advise, int, or no
            interaction) with the probabilities and the words that drove the prediction.
          </p>
          <p>
            Configured classifier: {clf ? <strong>{clf}</strong> : "…"}. The model card (per-class precision, recall and F1 on the
            test split, from a metrics file) will appear on this page.
          </p>
        </>
      }
    />
  );
}

export function PersonalizedAlert() {
  return (
    <NeedsPage
      title="Personalized Alert"
      needs={["dailymed_data", "index", "ddi_model"]}
      intro={
        <>
          <p>
            Enter a medicine and the patient's current medicines to get a template-based alert. Every sentence of the alert will point
            to a retrieved label passage or to a model output shown next to it. No language model writes the text.
          </p>
          <p>The profile travels in the request only. This prototype stores no patient data on the server.</p>
        </>
      }
    />
  );
}
