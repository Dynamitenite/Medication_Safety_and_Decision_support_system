import { useParams } from "react-router-dom";
import { ErrorBox, LoadingBox } from "../components/Panel";
import { Sticker } from "../components/Sticker";
import { useStatus } from "../StatusContext";

/** Name and "Coming soon". Nothing else: no sample data, no mock output. */
export function ComingSoon({ id: idProp }: { id?: string }) {
  const params = useParams();
  const id = idProp ?? params.id;
  const q = useStatus();
  if (q.state === "loading" && !q.data) return <LoadingBox what="module" />;
  if (q.state === "error") return <ErrorBox message={q.message} onRetry={q.reload} />;
  const m = q.data?.modules.find((x) => x.id === id);
  if (!m)
    return (
      <>
        <h1>Page not found</h1>
        <p>There is no feature with that address.</p>
      </>
    );
  return (
    <>
      <h1>{m.label}</h1>
      <p>
        <Sticker>Coming soon</Sticker>
      </p>
      <p>This feature is not available yet.</p>
    </>
  );
}
