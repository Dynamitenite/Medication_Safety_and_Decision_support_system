import { useEffect, useId, useState } from "react";
import { MagnifyingGlass } from "@phosphor-icons/react";
import { api } from "../api";
import type { AppmsMedication, AppmsPatient, AppmsPatientsResponse } from "../api";
import { ErrorBox, LoadingBox, NotReadyBox, fmt } from "./Panel";

const DEBOUNCE_MS = 200;
const PAGE = 8;

export type PickedPatient = { patient: AppmsPatient; medications: AppmsMedication[] };

type ListState = { state: "loading" | "error" | "ok"; data?: AppmsPatientsResponse; message?: string };
type PickState = {
  state: "idle" | "loading" | "error" | "ok";
  data?: PickedPatient;
  message?: string;
  notReady?: { reason?: string | null; fix?: string | null };
};

const conditions = (p: AppmsPatient) => [p.primary_condition, p.secondary_condition].filter(Boolean).join(", ") || "none listed";

/** Searchable sample-patient list. Choosing one loads its profile and medication list and shows
 *  both below. `onPick` hands the same data to the page that embeds this, so other pages can reuse it. */
export function PatientPicker({ onPick, label = "Find a sample patient", showCard = true }: { onPick?: (p: PickedPatient) => void; label?: string; showCard?: boolean }) {
  const inputId = useId();
  const [text, setText] = useState("");
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const [tick, setTick] = useState(0);
  const [list, setList] = useState<ListState>({ state: "loading" });
  const [picked, setPicked] = useState<PickState>({ state: "idle" });

  useEffect(() => {
    const t = setTimeout(() => {
      setQ(text);
      setOffset(0);
    }, DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [text]);

  useEffect(() => {
    const ctl = new AbortController();
    setList((l) => ({ state: "loading", data: l.data }));
    api
      .appmsPatients({ q, limit: PAGE, offset }, ctl.signal)
      .then((data) => setList({ state: "ok", data }))
      .catch((e: unknown) => {
        if (!ctl.signal.aborted) setList({ state: "error", message: e instanceof Error ? e.message : String(e) });
      });
    return () => ctl.abort();
  }, [q, offset, tick]);

  const choose = (id: string) => {
    setPicked({ state: "loading" });
    api
      .appmsPatient(id)
      .then((r) => {
        if (r.status !== "ready" || !r.patient) return setPicked({ state: "idle", notReady: { reason: r.reason, fix: r.fix } });
        const data = { patient: r.patient, medications: r.medications };
        setPicked({ state: "ok", data });
        onPick?.(data);
      })
      .catch((e: unknown) => setPicked({ state: "error", message: e instanceof Error ? e.message : String(e) }));
  };

  const d = list.data;
  const selectedId = picked.data?.patient.patient_id;
  return (
    <div className="picker">
      <label htmlFor={inputId} className="combo-label">{label}</label>
      <div className="picker-search">
        <MagnifyingGlass size={16} aria-hidden="true" />
        <input id={inputId} type="search" value={text} onChange={(e) => setText(e.target.value)} placeholder="Id, district, condition or medicine" autoComplete="off" />
      </div>
      {list.state === "error" && <ErrorBox message={list.message} onRetry={() => setTick((n) => n + 1)} />}
      {list.state === "loading" && !d && <LoadingBox what="patients" />}
      {d?.status === "not_ready" && <NotReadyBox reason={d.reason} fix={d.fix} />}
      {d?.status === "ready" && (
        <>
          <p className="small muted" role="status" aria-live="polite">
            {d.total === 0 ? "No patient matches." : `${fmt(offset + 1)}–${fmt(offset + d.patients.length)} of ${fmt(d.total)}`}
          </p>
          <ul className="picker-list" aria-label="Patients">
            {d.patients.map((p) => (
              <li key={p.patient_id}>
                <button type="button" className="picker-row" aria-pressed={p.patient_id === selectedId} onClick={() => choose(p.patient_id)}>
                  <strong>{p.patient_id}</strong>
                  <span className="small muted">
                    {p.age_years}, {p.gender} · {p.district}, {p.state} · {conditions(p)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
          <div className="picker-pager">
            <button type="button" className="btn btn-secondary btn-sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</button>
            <button type="button" className="btn btn-secondary btn-sm" disabled={offset + PAGE >= d.total} onClick={() => setOffset(offset + PAGE)}>Next</button>
          </div>
        </>
      )}
      {picked.state === "loading" && <LoadingBox what="patient" />}
      {picked.state === "error" && <ErrorBox message={picked.message} />}
      {picked.notReady && <NotReadyBox reason={picked.notReady.reason} fix={picked.notReady.fix} />}
      {picked.data && showCard && <PatientCard {...picked.data} />}
    </div>
  );
}

export function PatientCard({ patient: p, medications }: PickedPatient) {
  const facts: [string, string | number][] = [
    ["Age", p.age_years],
    ["Gender", p.gender],
    ["Location", `${p.district}, ${p.state} (${p.residence_type})`],
    ["Primary condition", p.primary_condition ?? "None"],
    ["Secondary condition", p.secondary_condition ?? "None"],
    ["Reported drug allergy", p.reported_drug_allergy ?? "None"],
    ["Kidney function (eGFR band)", p.egfr_category],
  ];
  return (
    <section className="picker-card" aria-label={`Patient ${p.patient_id}`}>
      <h3>{p.patient_id}</h3>
      <dl className="kv">
        {facts.map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
      <h4>Medicines ({medications.length})</h4>
      {medications.length === 0 ? (
        <p className="muted">No medications listed.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">Medicine</th><th scope="col">Strength</th><th scope="col">Route</th><th scope="col">Frequency</th><th scope="col">Days</th><th scope="col">For</th>
              </tr>
            </thead>
            <tbody>
              {medications.map((m) => (
                <tr key={m.medication_record_id}>
                  <th scope="row">{m.drug_name}</th>
                  <td>{m.strength}</td><td>{m.route}</td><td>{m.frequency}</td><td>{m.duration_days}</td><td>{m.indication}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
