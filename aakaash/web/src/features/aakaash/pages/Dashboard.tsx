import { api } from "../api";
import { DdiExamplesPanel, DdiStatsPanel } from "../components/DdiPanels";
import { DailyMedPanel, TacPanel } from "../components/LabelStatsPanels";
import { ErrorBox, LoadingBox } from "../components/Panel";
import { StatusTable } from "../components/StatusTable";
import { useStatus } from "../StatusContext";
import { useApi } from "../useApi";

function SystemStatus() {
  const q = useStatus();
  return (
    <section className="card" aria-labelledby="system-status-h">
      <h2 id="system-status-h">System status</h2>
      <p className="panel-hint">A component is ready only when its files exist on disk.</p>
      {q.state === "loading" && !q.data && <LoadingBox what="system status" />}
      {q.state === "error" && <ErrorBox message={q.message} onRetry={q.reload} />}
      {q.data && (
        <>
          <StatusTable components={q.data.components} />
          <p className="small muted">
            Configured encoder: <strong>{q.data.active_encoder}</strong> · configured interaction classifier:{" "}
            <strong>{q.data.active_classifier}</strong> · data folder: <code>{q.data.data_dir}</code>
          </p>
        </>
      )}
    </section>
  );
}

export function Dashboard() {
  const ddi = useApi(api.ddiStats);
  return (
    <>
      <h1>Dashboard</h1>
      <p className="lead">Datasets and system status. Every figure on this page comes from an API response computed from real files.</p>
      <SystemStatus />
      <DdiStatsPanel query={ddi} />
      {ddi.data?.status === "ready" && <DdiExamplesPanel labels={ddi.data.labels} />}
      <DailyMedPanel />
      <TacPanel />
    </>
  );
}
