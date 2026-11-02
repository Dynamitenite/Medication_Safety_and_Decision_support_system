import { useParams } from "react-router-dom";
import { ErrorBox, LoadingBox } from "../components/Panel";
import { Sticker } from "../components/Sticker";
import { useStatus } from "../StatusContext";

/** Name, stage, "Coming soon", owner. Nothing else: no sample data, no mock output. */
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
        <h1>Unknown module</h1>
        <p>The API does not list a module with id “{id}”.</p>
      </>
    );
  return (
    <>
      <h1>{m.label}</h1>
      <p>
        <Sticker>Coming soon</Sticker>
      </p>
      <p>This module is not built yet. Owner: {m.owner}.</p>
      <div className="table-wrap coming-table">
        <table>
          <thead>
            <tr>
              <th scope="col">Stage</th>
              <th scope="col">Owner</th>
            </tr>
          </thead>
          <tbody>
            {m.stages.map((n, i) => (
              <tr key={n}>
                <td>Stage {n}: {m.stage_names[i]}</td>
                <td>{m.owner}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
