import { api } from "../../api";
import { useApi } from "../../useApi";
import { FormTag } from "./icons";

/** Add a catalogue dosage-form label when a history record links to a catalogue brand. */
export function RecordFormTag({ catalogueId }: { catalogueId: string | null }) {
  const query = useApi(() => catalogueId ? api.brand(catalogueId) : Promise.resolve(undefined), [catalogueId]);
  const family = query.data?.status === "ready" ? query.data.brand?.form_family : null;
  return family ? <FormTag family={family} /> : null;
}
