import { useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { PencilSimple, Plus, Trash } from "@phosphor-icons/react";
import {
  api,
  errorText,
  type ConditionIn,
  type ConditionOut,
  type MedicineRecordIn,
  type MedicineRecordOut,
} from "../api";
import { ConfirmDialog, EmptyState, Field, FormError } from "../components/Form";
import { MedicineSearch } from "../components/MedicineSearch";
import { ErrorBox } from "../components/Panel";
import { Skeleton } from "../components/LabelTabs";
import { Sticker } from "../components/Sticker";
import { CONDITION_OUTCOME_LABEL, courseText, fmtDate, KIND_LABEL, MEDICINE_OUTCOME_LABEL } from "../format";
import { useApi, type Query } from "../useApi";

const TABS = [
  { id: "conditions", label: "Conditions" },
  { id: "medicines", label: "Medicines" },
] as const;
type TabId = (typeof TABS)[number]["id"];

const today = () => new Date().toISOString().slice(0, 10);

/** Loading skeleton, error with retry, or the data. */
function Loaded<T>({ query, children }: { query: Query<T>; children: (data: T) => ReactNode }) {
  if (query.state === "error") return <ErrorBox message={query.message} onRetry={query.reload} />;
  if (query.data === undefined)
    return (
      <div aria-busy="true" aria-label="Loading">
        <Skeleton lines={5} />
      </div>
    );
  return <>{children(query.data)}</>;
}

/** Delete confirmation for one row: `ask(label, action)` opens it, the dialog runs `action`. */
function useConfirmDelete(onDone: () => void) {
  const [pending, setPending] = useState<{ label: string; run: () => Promise<void> } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dialog = (title: string) => (
    <ConfirmDialog
      open={pending !== null}
      title={title}
      confirmLabel="Delete"
      busy={busy}
      error={error}
      onCancel={() => (setPending(null), setError(null))}
      onConfirm={async () => {
        if (!pending) return;
        setBusy(true);
        setError(null);
        try {
          await pending.run();
          setPending(null);
          onDone();
        } catch (e) {
          setError(errorText(e));
        } finally {
          setBusy(false);
        }
      }}
    >
      <p>{pending?.label} will be removed from your history.</p>
    </ConfirmDialog>
  );
  return { ask: (label: string, run: () => Promise<void>) => setPending({ label, run }), dialog };
}

function RowActions({ label, onEdit, onDelete }: { label: string; onEdit: () => void; onDelete: () => void }) {
  return (
    <div className="row-actions">
      <button type="button" className="btn btn-plain btn-icon btn-sm" aria-label={`Edit ${label}`} onClick={onEdit}>
        <PencilSimple size={16} />
      </button>
      <button type="button" className="btn btn-plain btn-icon btn-sm" aria-label={`Delete ${label}`} onClick={onDelete}>
        <Trash size={16} />
      </button>
    </div>
  );
}

function FormButtons({ busy, onCancel, disabled }: { busy: boolean; onCancel: () => void; disabled?: boolean }) {
  return (
    <div className="form-actions">
      <button type="button" className="btn btn-secondary" onClick={onCancel} disabled={busy}>
        Cancel
      </button>
      <button type="submit" className="btn btn-primary" disabled={busy || disabled}>
        {busy ? "Saving…" : "Save"}
      </button>
    </div>
  );
}

// ---- conditions -----------------------------------------------------------------------------
type CondDraft = { name: string; kind: string; status: string; onset_date: string; resolved_date: string; outcome: string; notes: string };

function ConditionForm({ initial, defaultStatus, onSaved, onCancel }: { initial?: ConditionOut; defaultStatus: "current" | "past"; onSaved: () => void; onCancel: () => void }) {
  const [d, setD] = useState<CondDraft>({
    name: initial?.name ?? "",
    kind: initial?.kind ?? "illness",
    status: initial?.status ?? defaultStatus,
    onset_date: initial?.onset_date ?? "",
    resolved_date: initial?.resolved_date ?? "",
    outcome: initial?.outcome ?? (defaultStatus === "current" ? "ongoing" : "unknown"),
    notes: initial?.notes ?? "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const past = d.status === "past";
  const set = (k: keyof CondDraft) => (e: { target: { value: string } }) => setD({ ...d, [k]: e.target.value });

  function setStatus(status: string) {
    // a current condition has no resolved date and cannot be "cured"; a past one is not "ongoing" by default
    setD({
      ...d,
      status,
      resolved_date: status === "current" ? "" : d.resolved_date,
      outcome: status === "current" && d.outcome === "cured" ? "ongoing" : status === "past" && d.outcome === "ongoing" ? "unknown" : d.outcome,
    });
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (d.onset_date && d.resolved_date && d.resolved_date < d.onset_date) return setError("The resolved date cannot be before the start date.");
    setBusy(true);
    setError(null);
    const body: ConditionIn = {
      name: d.name,
      kind: d.kind as ConditionIn["kind"],
      status: d.status as ConditionIn["status"],
      onset_date: d.onset_date || null,
      resolved_date: past ? d.resolved_date || null : null,
      outcome: d.outcome as ConditionIn["outcome"],
      notes: d.notes || null,
    };
    try {
      await (initial ? api.saveCondition(initial.id, body) : api.addCondition(body));
      onSaved();
    } catch (err) {
      setError(errorText(err));
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="card form-card">
      <h3>{initial ? "Edit condition" : "Add a condition"}</h3>
      <div className="form-grid">
        <Field label="Name" wide>
          <input type="text" value={d.name} maxLength={200} required autoFocus onChange={set("name")} />
        </Field>
        <Field label="Type">
          <select value={d.kind} onChange={set("kind")}>
            {Object.entries(KIND_LABEL).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Status">
          <select value={d.status} onChange={(e) => setStatus(e.target.value)}>
            <option value="current">Current</option>
            <option value="past">Past</option>
          </select>
        </Field>
        <Field label="Started">
          <input type="date" value={d.onset_date} max={today()} onChange={set("onset_date")} />
        </Field>
        <Field label="Resolved" hint={past ? undefined : "Only for past conditions."}>
          <input type="date" value={d.resolved_date} min={d.onset_date || undefined} max={today()} disabled={!past} onChange={set("resolved_date")} />
        </Field>
        <Field label="Outcome">
          <select value={d.outcome} onChange={set("outcome")}>
            {(Object.keys(CONDITION_OUTCOME_LABEL) as (keyof typeof CONDITION_OUTCOME_LABEL)[])
              .filter((o) => !(o === "cured" && !past))
              .map((o) => (
                <option key={o} value={o}>
                  {CONDITION_OUTCOME_LABEL[o]}
                </option>
              ))}
          </select>
        </Field>
        <Field label="Notes" wide>
          <textarea rows={2} maxLength={2000} value={d.notes} onChange={set("notes")} />
        </Field>
      </div>
      <FormError message={error} />
      <FormButtons busy={busy} onCancel={onCancel} disabled={!d.name.trim()} />
    </form>
  );
}

function ConditionRow({ c, onEdit, onDelete }: { c: ConditionOut; onEdit: () => void; onDelete: () => void }) {
  const dates = [c.onset_date && `Started ${fmtDate(c.onset_date)}`, c.resolved_date && `Resolved ${fmtDate(c.resolved_date)}`].filter(Boolean).join(" · ");
  return (
    <li>
      <div className="row-body">
        <span className="row-main">
          {c.name} <Sticker>{KIND_LABEL[c.kind]}</Sticker>{" "}
          <Sticker tone={c.outcome === "cured" ? "good" : "neutral"}>{CONDITION_OUTCOME_LABEL[c.outcome]}</Sticker>
        </span>
        <span className="small muted">{dates || "Dates not given"}</span>
        {c.notes && <span className="small">{c.notes}</span>}
      </div>
      <RowActions label={c.name} onEdit={onEdit} onDelete={onDelete} />
    </li>
  );
}

function ConditionsTab() {
  const q = useApi(api.conditions);
  const [form, setForm] = useState<{ id?: number; status: "current" | "past" } | null>(null);
  const del = useConfirmDelete(q.reload);
  const done = () => (setForm(null), q.reload());
  return (
    <Loaded query={q}>
      {(all) => {
        const group = (status: "current" | "past", title: string) => {
          const items = all.filter((c) => c.status === status);
          return (
            <section aria-label={title} className="group">
              <div className="card-head">
                <h2>{title}</h2>
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => setForm({ status })}>
                  <Plus size={14} aria-hidden="true" /> Add
                </button>
              </div>
              {form && form.id === undefined && form.status === status && <ConditionForm defaultStatus={status} onSaved={done} onCancel={() => setForm(null)} />}
              {items.length === 0 && !(form && form.id === undefined && form.status === status) && (
                <EmptyState title={status === "current" ? "No current conditions." : "No past conditions."} />
              )}
              <ul className="rows">
                {items.map((c) =>
                  form?.id === c.id ? (
                    <li key={c.id}>
                      <ConditionForm initial={c} defaultStatus={c.status} onSaved={done} onCancel={() => setForm(null)} />
                    </li>
                  ) : (
                    <ConditionRow key={c.id} c={c} onEdit={() => setForm({ id: c.id, status: c.status })} onDelete={() => del.ask(c.name, () => api.deleteCondition(c.id))} />
                  ),
                )}
              </ul>
            </section>
          );
        };
        return (
          <>
            {group("current", "Current")}
            {group("past", "Past")}
            {del.dialog("Delete this condition?")}
          </>
        );
      }}
    </Loaded>
  );
}

// ---- medicines ------------------------------------------------------------------------------
type MedDraft = { name: string; catalogue_id: string | null; reason: string; dose: string; frequency: string; start_date: string; end_date: string; outcome: string; notes: string };

function MedicineForm({ initial, onSaved, onCancel }: { initial?: MedicineRecordOut; onSaved: () => void; onCancel: () => void }) {
  const [d, setD] = useState<MedDraft>({
    name: initial?.display_name ?? "",
    catalogue_id: initial?.catalogue_id ?? null,
    reason: initial?.reason ?? "",
    dose: initial?.dose ?? "",
    frequency: initial?.frequency ?? "",
    start_date: initial?.start_date ?? "",
    end_date: initial?.end_date ?? "",
    outcome: initial?.outcome ?? "",
    notes: initial?.notes ?? "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof MedDraft) => (e: { target: { value: string } }) => setD({ ...d, [k]: e.target.value });
  const ended = d.end_date !== "";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (d.end_date && !d.start_date) return setError("Enter a start date to go with the end date.");
    if (d.start_date && d.end_date && d.end_date < d.start_date) return setError("The end date cannot be before the start date.");
    setBusy(true);
    setError(null);
    const body: MedicineRecordIn = {
      catalogue_id: d.catalogue_id,
      display_name: d.name,
      reason: d.reason || null,
      dose: d.dose || null,
      frequency: d.frequency || null,
      start_date: d.start_date || null,
      end_date: d.end_date || null,
      outcome: ended && d.outcome ? (d.outcome as MedicineRecordIn["outcome"]) : null,
      source: initial?.source ?? "typed",
      notes: d.notes || null,
    };
    try {
      await (initial ? api.saveMedicineRecord(initial.id, body) : api.addMedicineRecord(body));
      onSaved();
    } catch (err) {
      setError(errorText(err));
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="card form-card">
      <h3>{initial ? "Edit medicine" : "Add a medicine"}</h3>
      <MedicineSearch
        label="Medicine"
        placeholder="Search by brand name or ingredient"
        value={d.name}
        onValueChange={(v) => setD((p) => ({ ...p, name: v, catalogue_id: null }))}
        onSelect={(s) => setD((p) => ({ ...p, name: s.name, catalogue_id: s.id }))}
        hint={d.catalogue_id ? "Chosen from the medicine list, so its ingredients are recorded." : "Choose a match from the list to record its ingredients, or type any name."}
      />
      <div className="form-grid">
        <Field label="Taken for" wide>
          <input type="text" value={d.reason} maxLength={300} onChange={set("reason")} />
        </Field>
        <Field label="Dose">
          <input type="text" value={d.dose} maxLength={100} placeholder="for example 500 mg" onChange={set("dose")} />
        </Field>
        <Field label="How often">
          <input type="text" value={d.frequency} maxLength={100} placeholder="for example twice daily" onChange={set("frequency")} />
        </Field>
        <Field label="Started">
          <input type="date" value={d.start_date} onChange={set("start_date")} />
        </Field>
        <Field label="Ended" hint="Leave empty if you still take it.">
          <input type="date" value={d.end_date} min={d.start_date || undefined} onChange={set("end_date")} />
        </Field>
        {ended && (
          <Field label="How did it go?">
            <select value={d.outcome} onChange={set("outcome")}>
              <option value="">Not given</option>
              {(Object.keys(MEDICINE_OUTCOME_LABEL) as (keyof typeof MEDICINE_OUTCOME_LABEL)[]).map((o) => (
                <option key={o} value={o}>
                  {MEDICINE_OUTCOME_LABEL[o]}
                </option>
              ))}
            </select>
          </Field>
        )}
        <Field label="Notes" wide>
          <textarea rows={2} maxLength={2000} value={d.notes} onChange={set("notes")} />
        </Field>
      </div>
      <FormError message={error} />
      <FormButtons busy={busy} onCancel={onCancel} disabled={!d.name.trim()} />
    </form>
  );
}

function MedicineRow({ m, onEdit, onDelete }: { m: MedicineRecordOut; onEdit: () => void; onDelete: () => void }) {
  return (
    <li>
      <div className="row-body">
        <span className="row-main">
          {m.display_name}
          {m.status === "past" && m.outcome && <> <Sticker tone={m.outcome === "cured" || m.outcome === "improved" ? "good" : "neutral"}>{MEDICINE_OUTCOME_LABEL[m.outcome]}</Sticker></>}
        </span>
        {m.reason && <span className="small">For {m.reason}</span>}
        {(m.dose || m.frequency) && <span className="small muted">{[m.dose, m.frequency].filter(Boolean).join(" · ")}</span>}
        <span className="small muted">{courseText(m)}</span>
        {m.notes && <span className="small">{m.notes}</span>}
      </div>
      <RowActions label={m.display_name} onEdit={onEdit} onDelete={onDelete} />
    </li>
  );
}

function MedicinesTab() {
  const q = useApi(api.medicineRecords);
  // "new" = add form open; a number = that record is being edited
  const [editing, setEditing] = useState<"new" | number | null>(null);
  const del = useConfirmDelete(q.reload);
  const done = () => (setEditing(null), q.reload());
  return (
    <Loaded query={q}>
      {(all) => {
        const group = (status: MedicineRecordOut["status"], title: string, always = false) => {
          const items = all.filter((m) => m.status === status);
          if (!always && items.length === 0) return null;
          return (
            <section aria-label={title} className="group" key={status}>
              <h2>{title}</h2>
              {items.length === 0 && (
                <EmptyState title={status === "current" ? "No current medicines." : "No past medicines."} />
              )}
              <ul className="rows">
                {items.map((m) =>
                  editing === m.id ? (
                    <li key={m.id}>
                      <MedicineForm initial={m} onSaved={done} onCancel={() => setEditing(null)} />
                    </li>
                  ) : (
                    <MedicineRow key={m.id} m={m} onEdit={() => setEditing(m.id)} onDelete={() => del.ask(m.display_name, () => api.deleteMedicineRecord(m.id))} />
                  ),
                )}
              </ul>
            </section>
          );
        };
        return (
          <>
            {editing === "new" ? (
              <MedicineForm onSaved={done} onCancel={() => setEditing(null)} />
            ) : (
              <div className="toolbar">
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => setEditing("new")}>
                  <Plus size={14} aria-hidden="true" /> Add a medicine
                </button>
                <span className="small muted">Include medicines you take now and ones you took in the past.</span>
              </div>
            )}
            {group("current", "Current", true)}
            {group("upcoming", "Upcoming")}
            {group("past", "Past", true)}
            {group("not_stated", "Dates not given")}
            {del.dialog("Delete this medicine?")}
          </>
        );
      }}
    </Loaded>
  );
}

// ---- page -----------------------------------------------------------------------------------
export function History() {
  const [params, setParams] = useSearchParams();
  const tab: TabId = params.get("tab") === "medicines" ? "medicines" : "conditions";
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  const go = (id: TabId) => setParams(id === "conditions" ? {} : { tab: id }, { replace: true });
  function onKey(e: KeyboardEvent<HTMLButtonElement>, i: number) {
    const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    const next = TABS[(i + step + TABS.length) % TABS.length];
    go(next.id);
    refs.current[next.id]?.focus();
  }

  return (
    <>
      <h1>Past and current medical history</h1>
      <div className="tabs" role="tablist" aria-label="Medical history">
        {TABS.map((t, i) => (
          <button
            key={t.id}
            ref={(el) => void (refs.current[t.id] = el)}
            type="button"
            role="tab"
            id={`tab-${t.id}`}
            aria-selected={tab === t.id}
            aria-controls={`panel-${t.id}`}
            tabIndex={tab === t.id ? 0 : -1}
            className={tab === t.id ? "tab active" : "tab"}
            onClick={() => go(t.id)}
            onKeyDown={(e) => onKey(e, i)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === "conditions" ? <ConditionsTab /> : <MedicinesTab />}
      </div>
    </>
  );
}
