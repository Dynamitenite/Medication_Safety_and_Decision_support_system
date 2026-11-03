import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { X } from "@phosphor-icons/react";
import { api, ApiError, errorText } from "../api";
import { Field, FormError } from "../components/Form";
import { MedicineDetailsCard } from "../components/MedicineDetailsCard";
import { MedicineSearch, type Recent } from "../components/MedicineSearch";
import { Disclosure } from "../components/Disclosure";
import { OverallBanner, RiskAnalysis, type Analysis } from "../components/RiskAnalysis";
import { ScanPrescription } from "../components/ScanPrescription";
import { Sticker } from "../components/Sticker";
import { CourseBar, longestCourse } from "../components/viz/CourseBars";
import { InteractionGraph } from "../components/viz/InteractionGraph";
import { NoMedicinesArt } from "../components/viz/Illustrations";
import { emptyCourse, toCourse, type ToAddItem } from "../toAdd";

const MAX = 10;
const TABS = [
  { id: "type", label: "Type" },
  { id: "scan", label: "Scan prescription" },
] as const;
type TabId = (typeof TABS)[number]["id"];

function CourseFields({ it, onChange }: { it: ToAddItem; onChange: (p: Partial<ToAddItem>) => void }) {
  return (
    <div className="form-grid">
      <Field label="Reason (optional)">
        <input value={it.reason} maxLength={300} onChange={(e) => onChange({ reason: e.target.value })} />
      </Field>
      <Field label="Dose (optional)" hint="For example 1 tablet or 5 ml">
        <input value={it.dose} maxLength={100} onChange={(e) => onChange({ dose: e.target.value })} />
      </Field>
      <Field label="How often (optional)" hint="For example BD or 1-0-1">
        <input value={it.frequency} maxLength={100} onChange={(e) => onChange({ frequency: e.target.value })} />
      </Field>
      <Field label="With food (optional)" hint="For example after food">
        <input value={it.food} maxLength={100} onChange={(e) => onChange({ food: e.target.value })} />
      </Field>
      <Field label="Start date (optional)" hint="Today, if left empty">
        <input type="date" value={it.start_date} onChange={(e) => onChange({ start_date: e.target.value })} />
      </Field>
      <Field label="Length of the course">
        <select value={it.end_mode} onChange={(e) => onChange({ end_mode: e.target.value as ToAddItem["end_mode"] })}>
          <option value="duration">Number of days</option>
          <option value="end">End date</option>
        </select>
      </Field>
      {it.end_mode === "duration" ? (
        <Field label="Days (optional)" hint="Empty means no end date">
          <input inputMode="numeric" value={it.duration_days} onChange={(e) => onChange({ duration_days: e.target.value.replace(/\D/g, "").slice(0, 4) })} />
        </Field>
      ) : (
        <Field label="End date (optional)">
          <input type="date" value={it.end_date} min={it.start_date || undefined} onChange={(e) => onChange({ end_date: e.target.value })} />
        </Field>
      )}
    </div>
  );
}

function ToAddCard({ it, onChange, onRemove }: { it: ToAddItem; onChange: (p: Partial<ToAddItem>) => void; onRemove: () => void }) {
  const [editing, setEditing] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const edit = () => {
    setEditing(true);
    window.setTimeout(() => ref.current?.querySelector("input")?.focus(), 0);
  };
  return (
    <div className="card to-add">
      <div className="card-head">
        <h3>{it.name}</h3>
        <span className="row-actions">
          <Sticker>{it.source === "scanned" ? "From a scan" : "Typed"}</Sticker>
          <button type="button" className="btn btn-plain btn-icon btn-sm" aria-label={`Remove ${it.name}`} onClick={onRemove}>
            <X size={16} />
          </button>
        </span>
      </div>
      <p className="small muted">
        {it.composition} · {it.manufacturer ?? "manufacturer not stated"} · <Link to={`/medicine/${it.id}`}>Medicine page</Link>
      </p>
      {it.raw && <p className="small muted">Scanned line: “{it.raw}”</p>}
      <div ref={ref}>
        <button type="button" className="btn btn-secondary btn-sm" aria-expanded={editing} onClick={() => setEditing(!editing)}>
          {editing ? "Done" : "Edit reason, dose and dates"}
        </button>
        {editing && <CourseFields it={it} onChange={onChange} />}
      </div>
      <Disclosure title="Why it is taken, dose and instructions">
        <MedicineDetailsCard it={it} onEditCourse={edit} />
      </Disclosure>
    </div>
  );
}

/** Add medicines by typing or by scanning a printed prescription, see their label details, check
 *  them against current medicines and allergies, then add them to the medical history. */
export function AddMedicine() {
  const [params, setParams] = useSearchParams();
  const tab: TabId = params.get("tab") === "scan" ? "scan" : "type";
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const [text, setText] = useState("");
  const [items, setItems] = useState<ToAddItem[]>([]);
  const [note, setNote] = useState("");
  const [analysis, setAnalysis] = useState<Analysis>({ state: "idle" });
  const [ack, setAck] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string[] | null>(null);
  const ids = items.map((i) => i.id).join(",");

  const go = (id: TabId) => setParams(id === "type" ? {} : { tab: id }, { replace: true });
  function onKey(e: KeyboardEvent<HTMLButtonElement>, i: number) {
    const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    const next = TABS[(i + step + TABS.length) % TABS.length];
    go(next.id);
    refs.current[next.id]?.focus();
  }

  const run = useCallback(() => {
    if (!items.length) {
      setAnalysis({ state: "idle" });
      return;
    }
    setAnalysis({ state: "loading" });
    api
      .analyze(items.map(toCourse))
      .then((data) => setAnalysis({ state: "ok", data }))
      .catch((e: unknown) => setAnalysis({ state: "error", message: errorText(e) }));
    // the analysis uses only which medicines are listed, so course edits do not re-run it
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ids]);
  useEffect(run, [run]); // runs whenever a medicine is added or removed
  useEffect(() => setAck(false), [ids]);

  function add(item: ToAddItem) {
    setSaved(null);
    if (items.some((i) => i.id === item.id)) return setNote(`${item.name} is already in the list.`);
    if (items.length >= MAX) return setNote(`The limit is ${MAX} medicines at a time.`);
    setItems((xs) => [...xs, item]);
    setNote(`${item.name} added to the list.`);
  }
  const typed = (s: Recent) => add({ id: s.id, name: s.name, manufacturer: s.manufacturer, composition: s.composition, source: "typed", ...emptyCourse });
  const change = (id: string, p: Partial<ToAddItem>) => setItems((xs) => xs.map((x) => (x.id === id ? { ...x, ...p } : x)));
  const remove = (it: ToAddItem) => {
    setItems((xs) => xs.filter((x) => x.id !== it.id));
    setNote(`${it.name} removed from the list.`);
  };

  const critical = analysis.state === "ok" && analysis.data.overall === "Critical";
  async function save() {
    setSaving(true);
    setSaveError(null);
    try {
      const res = await api.addMedicines(items.map(toCourse), ack);
      setSaved(res.added.map((m) => m.display_name));
      setItems([]);
    } catch (e) {
      setSaveError(errorText(e));
      if (e instanceof ApiError && e.status === 409) run(); // the server found a Critical warning: show it
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <h1>Add new medicine</h1>
      <p className="lead">Add a medicine. It is checked against your current medicines and allergies first.</p>
      <div className="tabs" role="tablist" aria-label="How to add">
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
      <section role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} className="card">
        {tab === "type" ? (
          <MedicineSearch
            label="Find a medicine"
            placeholder="Search by brand or ingredient"
            value={text}
            onValueChange={setText}
            onSelect={typed}
            clearOnSelect
            hint="Each pick goes into the “To add” list below. Not in our list? Add it by name in My medical history."
          />
        ) : (
          <ScanPrescription onAdd={add} />
        )}
        <span className="sr-only" role="status" aria-live="polite">
          {note}
        </span>
      </section>

      {saved && (
        <div className="notice" role="status">
          <p>
            Added to your medicines: {saved.join(", ")}. <Link to="/history?tab=medicines">Open My medical history</Link>
          </p>
        </div>
      )}

      <section aria-labelledby="to-add-h">
        <h2 id="to-add-h">To add {items.length > 0 && <span className="small muted">({items.length})</span>}</h2>
        <OverallBanner result={analysis} />
        {items.length === 0 ? (
          <div className="empty-illustrated"><NoMedicinesArt /><p className="muted">No medicines yet. Pick one above.</p></div>
        ) : (
          <ul className="to-add-list">
            {items.map((it) => (
              <li key={it.id} className="to-add-item">
                <ToAddCard it={it} onChange={(p) => change(it.id, p)} onRemove={() => remove(it)} />
                <CourseBar it={it} maxDays={longestCourse(items)} />
              </li>
            ))}
          </ul>
        )}
      </section>

      {items.length > 0 && (
        <>
          <section className="card" aria-labelledby="risk-h" aria-busy={analysis.state === "loading"}>
            <div className="card-head">
              <h2 id="risk-h">Risk analysis</h2>
              <button type="button" className="btn btn-secondary btn-sm" onClick={run} disabled={analysis.state === "loading"}>
                {analysis.state === "loading" ? "Checking…" : "Check before adding"}
              </button>
            </div>
            <RiskAnalysis result={analysis} onRetry={run} graph={analysis.state === "ok" && analysis.data.status === "ready" ? <InteractionGraph data={analysis.data} /> : undefined} />
          </section>

          <section className="card add-bar" aria-label="Add to my medicines">
            {critical && (
              <label className="toggle ack">
                <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />I have read this warning
              </label>
            )}
            <FormError message={saveError} />
            <div className="form-actions">
              <button type="button" className="btn btn-primary" disabled={saving || analysis.state === "loading" || (critical && !ack)} onClick={save}>
                {saving ? "Adding…" : `Add to my medicines (${items.length})`}
              </button>
            </div>
            <p className="small muted">Start date is today unless you enter one. A number of days sets the end date.</p>
          </section>
        </>
      )}
    </>
  );
}
