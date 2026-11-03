import { useId, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import type { DetailSection, IngredientDetails } from "../api";
import { fmtDate, fmtDuration } from "../format";
import { addDays, durationOf, todayIso, type ToAddItem } from "../toAdd";
import { useApi } from "../useApi";
import { Skeleton } from "./LabelTabs";
import { SimplifyButton } from "./AiAnswer";
import { ErrorBox, KeyValues, NotReadyBox } from "./Panel";
import { Sticker } from "./Sticker";

const FIRST_SENTENCES = 3;
const MAX_LINES = 6;
const MAX_CHARS = 420;

/** Drop a leading all-capitals heading line ("2 DOSAGE AND ADMINISTRATION"); the card has its own. */
function body(text: string): string {
  const [first, ...rest] = text.split("\n");
  return rest.length && first.length < 90 && !/[a-z]/.test(first) ? rest.join("\n").trim() : text.trim();
}

/** Verbatim label text: the first few sentences, then "Show full text". Never summarised. */
export function Excerpt({ text }: { text: string }) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const full = body(text);
  // the first few sentences; label text is often lists and tables without full stops, so the
  // excerpt also stops after a few lines or characters (at a word boundary)
  let short = full.split(/(?<=[.!?])\s+(?=[A-Z(•●-])/).slice(0, FIRST_SENTENCES).join(" ");
  short = short.split("\n").slice(0, MAX_LINES).join("\n");
  if (short.length > MAX_CHARS) short = short.slice(0, short.lastIndexOf(" ", MAX_CHARS) > 0 ? short.lastIndexOf(" ", MAX_CHARS) : MAX_CHARS);
  short = short.trimEnd();
  const cut = short.length < full.length;
  return (
    <div className="excerpt">
      <blockquote id={id} className="label-text">
        {open || !cut ? full : `${short} …`}
      </blockquote>
      {cut && (
        <button type="button" className="btn btn-plain btn-sm" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}>
          {open ? "Show less" : "Show full text"}
        </button>
      )}
    </div>
  );
}

const formRoute = (g: IngredientDetails) => (g.label ? [g.label.form, g.label.route].filter(Boolean).join(" · ") : "");

function LabelTitle({ g }: { g: IngredientDetails }) {
  return (
    <p className="small muted">
      From the US label for <strong>{g.us_name ?? g.name}</strong>
      {g.label && (
        <>
          {" "}(<Link to={`/label/${g.label.set_id}`}>{g.label.name}</Link>
          {formRoute(g) && `, ${formRoute(g)}`})
        </>
      )}
    </p>
  );
}

function Mismatch({ g }: { g: IngredientDetails }) {
  if (!g.mismatch) return null;
  return (
    <p className="small">
      <Sticker wrap>{g.mismatch === "form_unknown" ? "Form unknown" : g.mismatch === "wrong_form" ? "Different form" : "Different product"}</Sticker>{" "}
      {g.mismatch_note}
    </p>
  );
}

function Section({ s, medicineId, ingredientIndex, simplify = true }: { s: DetailSection; medicineId: string; ingredientIndex: number; simplify?: boolean }) {
  return (
    <div className="detail-section">
      <h5>{s.label}</h5>
      <Excerpt text={s.text} />
      {simplify && <SimplifyButton medicineId={medicineId} ingredientIndex={ingredientIndex} sectionKey={s.key} />}
    </div>
  );
}

function TimeCourse({ it, onEdit }: { it: ToAddItem; onEdit: () => void }) {
  const start = it.start_date || todayIso();
  const days = durationOf(it);
  const end = it.end_mode === "end" ? it.end_date : days ? addDays(start, days - 1) : "";
  const length = end && end >= start ? Math.round((Date.parse(end) - Date.parse(start)) / 86_400_000) + 1 : null;
  const none = (
    <>
      Not entered{" "}
      <button type="button" className="btn btn-plain btn-sm" onClick={onEdit}>
        Edit
      </button>
    </>
  );
  return (
    <KeyValues
      items={[
        ["Dose", it.dose || none],
        ["How often", it.frequency || none],
        ["With food", it.food || none],
        ["Start", it.start_date ? fmtDate(it.start_date) : <>Not entered. Today ({fmtDate(start)}) will be used when you add it.</>],
        ["End", end ? fmtDate(end) : none],
        ["Duration", length ? fmtDuration(length) : none],
      ]}
    />
  );
}

/** "Why it is taken", the time course and the major instructions, from verbatim US label text. */
export function MedicineDetailsCard({ it, onEditCourse }: { it: ToAddItem; onEditCourse: () => void }) {
  const q = useApi(() => api.medicineDetails(it.id), [it.id]);
  const d = q.data;
  return (
    <div className="details" aria-busy={q.state === "loading"}>
      <h4>Why it is taken</h4>
      {q.state === "error" && <ErrorBox message={q.message} onRetry={q.reload} />}
      {q.state === "loading" && !d && <Skeleton lines={3} />}
      {d?.status === "not_ready" && <NotReadyBox reason={d.reason} fix={d.fix} />}
      {d?.status === "ready" && (
        <>
          {d.ingredients.length === 0 && <p>No ingredient is recorded for this medicine, so no label text can be shown.</p>}
          {d.ingredients.map((g) => (
            <div key={g.name} className="detail-block">
              {!g.label ? (
                <p>
                  No US label is linked for <strong>{g.name}</strong>. Some ingredients sold in India are not approved in the US, so
                  they have no US label.
                </p>
              ) : g.status === "not_ready" ? (
                <NotReadyBox reason={g.reason} fix={g.fix} title={g.name} />
              ) : (
                <>
                  <LabelTitle g={g} />
                  <Mismatch g={g} />
                  {g.indications ? (
                    <>
                      <Excerpt text={g.indications.text} />
                      {/* a label of another form or product is shown with a notice; a rewrite would drop it */}
                      {!g.mismatch && <SimplifyButton medicineId={it.id} ingredientIndex={d.ingredients.indexOf(g)} sectionKey="indications" />}
                    </>
                  ) : (
                    <p className="muted">This label has no Indications section.</p>
                  )}
                </>
              )}
            </div>
          ))}
          {d.composition_incomplete && !d.composition_unclear && (
            <p className="small">
              <Sticker wrap>Composition may be incomplete</Sticker> Only two ingredients are listed for this product. It may contain more.
            </p>
          )}
          {d.composition_unclear && (
            <p className="small">
              <Sticker wrap>Composition unclear</Sticker> The listed composition repeats an ingredient and may be wrong.
            </p>
          )}
          <p className="small muted">{d.label_note}</p>
        </>
      )}

      <h4>Time course</h4>
      <TimeCourse it={it} onEdit={onEditCourse} />

      <h4>Major instructions</h4>
      {d?.status === "ready" &&
        d.ingredients
          .filter((g) => g.label && g.status === "ready")
          .map((g) => (
            <div key={g.name} className="detail-block">
              <LabelTitle g={g} />
              {g.boxed_warning && <Section s={g.boxed_warning} medicineId={it.id} ingredientIndex={0} simplify={false} />}
              {g.withheld_note ? (
                <p className="notice">{g.withheld_note}</p>
              ) : (
                g.instructions.map((s) => <Section key={s.key} s={s} medicineId={it.id} ingredientIndex={d.ingredients.indexOf(g)} />)
              )}
              {g.missing.filter((m) => m !== "Indications and usage").map((m) => (
                <p key={m} className="small muted">
                  This label has no {m} section.
                </p>
              ))}
            </div>
          ))}
      {d?.status === "ready" && !d.ingredients.some((g) => g.label && g.status === "ready") && (
        <p className="muted">No US label text is available for this medicine.</p>
      )}
    </div>
  );
}
