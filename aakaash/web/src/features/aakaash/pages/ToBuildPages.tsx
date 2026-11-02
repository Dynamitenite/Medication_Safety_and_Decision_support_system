import { NeedsPage } from "../components/NeedsPage";
import { useStatus } from "../StatusContext";

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
