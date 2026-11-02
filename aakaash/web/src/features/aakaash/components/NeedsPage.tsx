import type { ReactNode } from "react";
import { useStatus } from "../StatusContext";
import { ErrorBox, LoadingBox, NotReadyBox } from "./Panel";
import { StatusTable } from "./StatusTable";

/** A screen whose interface is not built yet. It lists what it depends on, as the API reports it. */
export function NeedsPage({ title, intro, needs }: { title: string; intro: ReactNode; needs: string[] }) {
  const q = useStatus();
  const comps = (q.data?.components ?? []).filter((c) => needs.includes(c.id));
  const blocking = comps.filter((c) => c.status !== "ready");
  return (
    <>
      <h1>{title}</h1>
      <div className="lead">{intro}</div>
      <section className="card">
        <h2>What this screen needs</h2>
        {q.state === "loading" && !q.data && <LoadingBox what="component status" />}
        {q.state === "error" && <ErrorBox message={q.message} onRetry={q.reload} />}
        {q.data && blocking.length > 0 && (
          <NotReadyBox
            title="No results are shown."
            reason={`${blocking.length} of ${comps.length} required components are not ready, so this screen has nothing real to show yet.`}
          />
        )}
        {q.data && blocking.length === 0 && (
          <div className="notice" role="status">
            The data and models listed below are ready, but this screen's interface is not built yet.
          </div>
        )}
        {q.data && <StatusTable components={comps} />}
      </section>
    </>
  );
}
