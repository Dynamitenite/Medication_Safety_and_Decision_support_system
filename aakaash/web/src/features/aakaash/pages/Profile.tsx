import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { CalendarBlank, PencilSimple, Plus, Ruler, Scales, Trash } from "@phosphor-icons/react";
import { api, errorText, type AllergyOut, type ProfileIn, type ProfileOut } from "../api";
import { ConfirmDialog, EmptyState, Field, FormError } from "../components/Form";
import { ErrorBox, KeyValues } from "../components/Panel";
import { Skeleton } from "../components/LabelTabs";
import { Sticker } from "../components/Sticker";
import { BmiScaleCard } from "../components/viz/BmiScale";
import { RecordFormTag } from "../components/viz/RecordFormTag";
import { LevelGlyph, SeverityGlyph } from "../components/viz/icons";
import { NoAllergiesArt, NoMedicinesArt } from "../components/viz/Illustrations";
import { courseText, fmtDate, SEVERITY_LABEL, SEX_LABEL } from "../format";
import { useApi, type Query } from "../useApi";

const BLOOD_GROUPS = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"] as const;
const NOT_GIVEN = <span className="muted">Not given</span>;

/** A titled card that shows a skeleton while loading and an error with retry. */
function Section<T>({ title, query, action, children }: { title: string; query: Query<T>; action?: React.ReactNode; children: (data: T) => React.ReactNode }) {
  let body: React.ReactNode;
  if (query.state === "error") body = <ErrorBox message={query.message} onRetry={query.reload} />;
  else if (query.data === undefined) body = <Skeleton lines={3} />;
  else body = children(query.data);
  return (
    <section className="card" aria-label={title}>
      <div className="card-head">
        <h2>{title}</h2>
        {query.data !== undefined && action}
      </div>
      {body}
    </section>
  );
}

// ---- patient information --------------------------------------------------------------------
type ProfileDraft = { name: string; date_of_birth: string; sex: string; height_cm: string; weight_kg: string; blood_group: string; notes: string };

const draftOf = (p: ProfileOut): ProfileDraft => ({
  name: p.name ?? "",
  date_of_birth: p.date_of_birth ?? "",
  sex: p.sex ?? "",
  height_cm: p.height_cm?.toString() ?? "",
  weight_kg: p.weight_kg?.toString() ?? "",
  blood_group: p.blood_group ?? "",
  notes: p.notes ?? "",
});

const payloadOf = (d: ProfileDraft): ProfileIn => ({
  name: d.name || null,
  date_of_birth: d.date_of_birth || null,
  sex: (d.sex || null) as ProfileIn["sex"],
  height_cm: d.height_cm ? Number(d.height_cm) : null,
  weight_kg: d.weight_kg ? Number(d.weight_kg) : null,
  blood_group: (d.blood_group || null) as ProfileIn["blood_group"],
  notes: d.notes || null,
});

function ProfileForm({ profile, onSaved, onCancel }: { profile: ProfileOut; onSaved: () => void; onCancel: () => void }) {
  const [d, setD] = useState(() => draftOf(profile));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof ProfileDraft) => (e: { target: { value: string } }) => setD({ ...d, [k]: e.target.value });
  const today = new Date().toISOString().slice(0, 10);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.saveProfile(payloadOf(d));
      onSaved();
    } catch (err) {
      setError(errorText(err));
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit}>
      <div className="form-grid">
        <Field label="Name">
          <input type="text" value={d.name} maxLength={100} onChange={set("name")} autoComplete="name" />
        </Field>
        <Field label="Date of birth">
          <input type="date" value={d.date_of_birth} min="1900-01-01" max={today} onChange={set("date_of_birth")} />
        </Field>
        <Field label="Sex">
          <select value={d.sex} onChange={set("sex")}>
            <option value="">Not given</option>
            {Object.entries(SEX_LABEL).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Blood group">
          <select value={d.blood_group} onChange={set("blood_group")}>
            <option value="">Not given</option>
            {BLOOD_GROUPS.map((g) => (
              <option key={g} value={g}>
                {g}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Height (cm)">
          <input type="number" inputMode="decimal" min={40} max={250} step="0.1" value={d.height_cm} onChange={set("height_cm")} />
        </Field>
        <Field label="Weight (kg)">
          <input type="number" inputMode="decimal" min={2} max={400} step="0.1" value={d.weight_kg} onChange={set("weight_kg")} />
        </Field>
        <Field label="Notes" wide>
          <textarea rows={3} maxLength={2000} value={d.notes} onChange={set("notes")} />
        </Field>
      </div>
      <FormError message={error} />
      <div className="form-actions">
        <button type="button" className="btn btn-secondary" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
        <button type="submit" className="btn btn-primary" disabled={busy}>
          {busy ? "Saving…" : "Save"}
        </button>
      </div>
    </form>
  );
}

function PatientCard() {
  const q = useApi(api.profile);
  const [editing, setEditing] = useState(false);
  return (
    <Section
      title="Patient information"
      query={q}
      action={
        !editing && (
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => setEditing(true)}>
            <PencilSimple size={14} aria-hidden="true" /> Edit
          </button>
        )
      }
    >
      {(p) =>
        editing ? (
          <ProfileForm
            profile={p}
            onCancel={() => setEditing(false)}
            onSaved={() => {
              setEditing(false);
              q.reload();
            }}
          />
        ) : (
          <>
            <div className="profile-stats" aria-label="Age, height and weight">
              <div><CalendarBlank size={18} aria-hidden="true"/><span className="small muted">Age</span><strong>{p.age != null ? `${p.age} years` : "Not given"}</strong></div>
              <div><Ruler size={18} aria-hidden="true"/><span className="small muted">Height</span><strong>{p.height_cm != null ? `${p.height_cm} cm` : "Not given"}</strong></div>
              <div><Scales size={18} aria-hidden="true"/><span className="small muted">Weight</span><strong>{p.weight_kg != null ? `${p.weight_kg} kg` : "Not given"}</strong></div>
            </div>
            <BmiScaleCard age={p.age} bmi={p.bmi} />
            <KeyValues
              items={[
                ["Name", p.name ?? NOT_GIVEN],
                ["Sex", p.sex ? SEX_LABEL[p.sex] : NOT_GIVEN],
                ["Blood group", p.blood_group ?? NOT_GIVEN],
              ]}
            />
            {p.notes && <p className="small">{p.notes}</p>}
          </>
        )
      }
    </Section>
  );
}

// ---- current conditions ---------------------------------------------------------------------
function CurrentConditions() {
  const q = useApi(api.conditions);
  return (
    <Section title="Current conditions" query={q} action={<Link to="/history" className="small">All conditions</Link>}>
      {(all) => {
        const current = all.filter((c) => c.status === "current");
        if (current.length === 0)
          return <EmptyState title="No current conditions added." hint="Add them under Past and current medical history." action={<Link to="/history" className="btn btn-secondary btn-sm">Add a condition</Link>} />;
        return (
          <ul className="rows">
            {current.map((c) => (
              <li key={c.id}>
                <span className="row-main">{c.name}</span>
                <span className="small muted">{c.onset_date ? `Since ${fmtDate(c.onset_date)}` : "Start date not given"}</span>
              </li>
            ))}
          </ul>
        );
      }}
    </Section>
  );
}

// ---- allergies ------------------------------------------------------------------------------
const SEVERITIES = ["mild", "moderate", "severe", "unknown"] as const;

function AllergyForm({ initial, onSaved, onCancel }: { initial?: AllergyOut; onSaved: () => void; onCancel: () => void }) {
  const [allergen, setAllergen] = useState(initial?.allergen ?? "");
  const [reaction, setReaction] = useState(initial?.reaction ?? "");
  const [severity, setSeverity] = useState<AllergyOut["severity"]>(initial?.severity ?? "unknown");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body = { allergen, reaction: reaction || null, severity, notes: initial?.notes ?? null };
    try {
      await (initial ? api.saveAllergy(initial.id, body) : api.addAllergy(body));
      onSaved();
    } catch (err) {
      setError(errorText(err));
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="inline-form">
      <div className="form-grid">
        <Field label="Allergic to">
          <input type="text" value={allergen} maxLength={200} required onChange={(e) => setAllergen(e.target.value)} autoFocus />
        </Field>
        <Field label="Severity">
          <select value={severity} onChange={(e) => setSeverity(e.target.value as AllergyOut["severity"])}>
            {SEVERITIES.map((s) => (
              <option key={s} value={s}>
                {SEVERITY_LABEL[s]}
              </option>
            ))}
          </select>
        </Field>
        <Field label="What happens, and what triggers it" wide>
          <textarea rows={2} maxLength={500} value={reaction} onChange={(e) => setReaction(e.target.value)} />
        </Field>
      </div>
      <FormError message={error} />
      <div className="form-actions">
        <button type="button" className="btn btn-secondary btn-sm" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
        <button type="submit" className="btn btn-primary btn-sm" disabled={busy || !allergen.trim()}>
          {busy ? "Saving…" : "Save"}
        </button>
      </div>
    </form>
  );
}

function Allergies() {
  const q = useApi(api.allergies);
  // "new" = the add form is open; a number = that allergy is being edited
  const [editing, setEditing] = useState<"new" | number | null>(null);
  const [removing, setRemoving] = useState<AllergyOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const done = () => {
    setEditing(null);
    q.reload();
  };

  async function remove() {
    if (!removing) return;
    setBusy(true);
    setError(null);
    try {
      await api.deleteAllergy(removing.id);
      setRemoving(null);
      q.reload();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Section
      title="Allergies"
      query={q}
      action={
        editing !== "new" && (
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => setEditing("new")}>
            <Plus size={14} aria-hidden="true" /> Add
          </button>
        )
      }
    >
      {(items) => (
        <>
          {editing === "new" && <AllergyForm onSaved={done} onCancel={() => setEditing(null)} />}
          {items.length === 0 && editing !== "new" && (
            <div className="empty-illustrated"><NoAllergiesArt /><EmptyState title="No allergies added yet." hint="Add anything you are allergic to, so it is on record." /></div>
          )}
          <ul className="rows">
            {items.map((a) =>
              editing === a.id ? (
                <li key={a.id}>
                  <AllergyForm initial={a} onSaved={done} onCancel={() => setEditing(null)} />
                </li>
              ) : (
                <li key={a.id}>
                  <div className="row-body">
                    <span className="row-main">
                      {a.allergen} <Sticker tone={a.severity === "severe" ? "danger" : "neutral"}><SeverityGlyph severity={a.severity} size={14} /> {SEVERITY_LABEL[a.severity]}</Sticker>
                    </span>
            {a.reaction && <span className="small muted">{a.reaction}</span>}
                  </div>
                  <div className="row-actions">
                    <button type="button" className="btn btn-plain btn-icon btn-sm" aria-label={`Edit ${a.allergen}`} onClick={() => setEditing(a.id)}>
                      <PencilSimple size={16} />
                    </button>
                    <button type="button" className="btn btn-plain btn-icon btn-sm" aria-label={`Delete ${a.allergen}`} onClick={() => setRemoving(a)}>
                      <Trash size={16} />
                    </button>
                  </div>
                </li>
              ),
            )}
          </ul>
          <ConfirmDialog
            open={removing !== null}
            title="Delete this allergy?"
            confirmLabel="Delete"
            busy={busy}
            error={error}
            onConfirm={remove}
            onCancel={() => (setRemoving(null), setError(null))}
          >
            <p>{removing?.allergen} will be removed from your profile.</p>
          </ConfirmDialog>
        </>
      )}
    </Section>
  );
}

// ---- current medicines ----------------------------------------------------------------------
function CurrentMedicines() {
  const q = useApi(api.medicineRecords);
  return (
    <Section title="Current medicines" query={q} action={<Link to="/history?tab=medicines" className="small">All medicines</Link>}>
      {(all) => {
        const current = all.filter((m) => m.status === "current");
        if (current.length === 0)
          return <div className="empty-illustrated"><NoMedicinesArt /><EmptyState title="No current medicines." hint="Medicines you are taking now appear here." action={<Link to="/history?tab=medicines" className="btn btn-secondary btn-sm">Add a medicine</Link>} /></div>;
        return (
          <ul className="rows">
            {current.slice(0, 5).map((m) => (
              <li key={m.id}>
                <span className="row-main">{m.display_name}{m.catalogue_id && <> <RecordFormTag catalogueId={m.catalogue_id} /></>}</span>
                <span className="small muted">{[m.dose, m.frequency, courseText(m)].filter(Boolean).join(" · ")}</span>
              </li>
            ))}
            {current.length > 5 && (
              <li>
                <Link to="/history?tab=medicines">and {current.length - 5} more</Link>
              </li>
            )}
          </ul>
        );
      }}
    </Section>
  );
}

export function Profile() {
  const overview = useApi(api.profileOverview);
  return (
    <>
      <h1>My profile</h1>
      <section className="profile-overview" aria-label="Profile summary">
        {overview.state === "error" ? <ErrorBox message={overview.message} onRetry={overview.reload} /> : overview.data ? <>
          <div className="summary-tile"><strong>{overview.data.current_medicines}</strong><span>Current medicines</span></div>
          <div className="summary-tile"><strong>{overview.data.allergies}</strong><span>Allergies</span></div>
          <div className="summary-tile"><strong>{overview.data.current_conditions}</strong><span>Current conditions</span></div>
          <div className={`summary-tile summary-risk${overview.data.highest_risk ? ` lv-${overview.data.highest_risk.toLowerCase()}` : ""}`}>
            <LevelGlyph level={overview.data.highest_risk} size={20} />
            <strong>{overview.data.highest_risk ?? (overview.data.risk_status === "none_found" ? "No finding" : "Not enough data")}</strong>
            <span>Highest current-medicine pair</span>
            {overview.data.risk_note && <span className="small muted">{overview.data.risk_note}</span>}
          </div>
        </> : <div className="summary-loading" aria-busy="true">Loading profile summary…</div>}
      </section>
      <PatientCard />
      <CurrentConditions />
      <Allergies />
      <CurrentMedicines />
    </>
  );
}
