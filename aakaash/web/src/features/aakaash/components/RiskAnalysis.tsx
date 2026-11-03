import { Link } from "react-router-dom";
import type { ReactNode } from "react";
import { Warning } from "@phosphor-icons/react";
import type { AllergyFinding, AnalyzeResponse, CheckerMedicine, PairFinding, RiskLevel } from "../api";
import { SEVERITY_LABEL } from "../format";
import { Disclaimer } from "./Disclaimer";
import { InteractionType } from "./InteractionType";
import { ErrorBox, NotReadyBox } from "./Panel";
import { Sticker } from "./Sticker";
import { findingId } from "../viz/graph";
import { LevelGlyph, SeverityGlyph } from "./viz/icons";

export type Analysis = { state: "idle" } | { state: "loading" } | { state: "error"; message: string } | { state: "ok"; data: AnalyzeResponse };

const LEVELS: RiskLevel[] = ["Medium", "High", "Critical"];
const rank = (l: RiskLevel | null | undefined) => (l ? LEVELS.indexOf(l) : -1);
const lvClass = (l: RiskLevel) => `lv-${l.toLowerCase()}`;

/** Three labelled segments; the active one is filled and also named in text. No score. */
export function RiskMeter({ level }: { level: RiskLevel | null }) {
  const label = level ? `Overall level: ${level}` : "No known interaction found in our rules";
  return (
    <div className="risk-meter-wrap">
      <div className="risk-meter" role="img" aria-label={label}>
        {LEVELS.map((l) => (
          <span key={l} className={`risk-seg ${lvClass(l)}${l === level ? " on" : ""}`} aria-hidden="true">
            <LevelGlyph level={l} size={14} />{l}
          </span>
        ))}
      </div>
      {level && (
        <p className="risk-meter-text">
          Overall level: <strong className={`lv-text ${lvClass(level)}`}>{level}</strong>
        </p>
      )}
    </div>
  );
}

function LevelBadge({ level }: { level: RiskLevel }) {
  return <span className={`badge lv-badge ${lvClass(level)}`}><LevelGlyph level={level} size={14} />{level}</span>;
}

const ings = (m: CheckerMedicine) => (m.kind === "generic" && m.ingredients.length === 1 && m.ingredients[0].name === m.name ? "ingredients not known" : m.ingredients.map((g) => g.name).join(" + ") || "ingredients not known");
const role = (r: "new" | "current") => (r === "new" ? "to add" : "current");

function PairCard({ p }: { p: PairFinding }) {
  const n = p.text_match.matches_total;
  return (
    <li id={findingId("p", p.a.key, p.b.key)} tabIndex={-1} className={`finding${p.level ? ` ${lvClass(p.level)}` : ""}`}>
      <div className="finding-head">
        <span className="finding-names">
          {p.a.name} <span className="small muted">({role(p.a_role)})</span> <span className="muted">+</span> {p.b.name}{" "}
          <span className="small muted">({role(p.b_role)})</span>
        </span>
        {p.level ? <LevelBadge level={p.level} /> : <Sticker>No level from our rules</Sticker>}
      </div>
      <p className="small muted">
        Ingredients: {ings(p.a)} · {ings(p.b)}
      </p>
      {p.hits.length > 0 && (
        <section aria-label="Interaction rules">
          <h4>Reason (interaction rules)</h4>
          <ul className="evidence">
            {p.hits.map((h, i) => (
              <li key={i}>
                <p>
                  <LevelBadge level={h.level} /> {h.explanation}
                </p>
                <p className="small muted">
                  Ingredients involved: {h.a_ingredient} and {h.b_ingredient}.
                  {h.rule_tier === "moderate" && " The rules call this tier “Moderate”; it is shown here as Medium."}
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}
      {p.shared_ingredients.length > 0 && (
        <p className="small">
          <Warning size={14} aria-hidden="true" /> Both contain {p.shared_ingredients.join(", ")}. Taking both may double the dose of that
          ingredient.
        </p>
      )}
      {n > 0 && (
        <div>
          <h4>Label text (supporting evidence, does not change the level)</h4>
          <p className="small muted">{p.text_match.source_label}</p>
          <ul className="evidence">
            {p.text_match.matches.map((m, i) => (
              <li key={i}>
                <blockquote>{m.sentence}</blockquote>
                {m.source_term && <InteractionType sentence={m.sentence} drug1={m.source_term} drug2={m.matched_term} disclosure />}
                <p className="small muted">
                  From the US label for <strong>{m.source_ingredient}</strong> (<Link to={`/label/${m.in_label_set_id}`}>{m.in_label_name}</Link>),
                  section “{m.section}”. Names <strong>{m.named_ingredient}</strong>, in {m.names_drug}.
                </p>
              </li>
            ))}
          </ul>
          {n > p.text_match.matches.length && <p className="small muted">Showing {p.text_match.matches.length} of {n} sentences.</p>}
        </div>
      )}
      {p.notes.map((t) => (
        <p key={t} className="small">
          <Sticker wrap>Check</Sticker> {t}
        </p>
      ))}
    </li>
  );
}

function AllergyCard({ f }: { f: AllergyFinding }) {
  return (
    <li id={findingId("a", f.allergy_id, f.medicine.key)} tabIndex={-1} className={`finding ${lvClass(f.level)}`}>
      <div className="finding-head">
        <span className="finding-names">
          {f.medicine.name} <span className="muted">+</span> your allergy to {f.allergen}
        </span>
        <LevelBadge level={f.level} />
      </div>
      <h4>Reason (your allergies)</h4>
      <p>
        You recorded an allergy to <strong>{f.allergen}</strong>
        {f.reaction ? ` (reaction: ${f.reaction})` : ""}, severity: <SeverityGlyph severity={f.severity} size={14} /> {SEVERITY_LABEL[f.severity].toLowerCase()}. {f.medicine.name} contains{" "}
        <strong>{f.ingredients.join(", ")}</strong>.
      </p>
      <p className="small muted">
        Ingredients: {ings(f.medicine)}. {f.note}
      </p>
      {f.notes.map((t) => (
        <p key={t} className="small">
          <Sticker wrap>Check</Sticker> {t}
        </p>
      ))}
    </li>
  );
}

/** The analysis of the "To add" list against the user's current medicines and allergies. */
export function RiskAnalysis({ result, onRetry, graph }: { result: Analysis; onRetry: () => void; graph?: ReactNode }) {
  if (result.state === "idle") return <p className="muted">The check runs when you add a medicine to the list.</p>;
  if (result.state === "loading")
    return (
      <div aria-hidden="true">
        <div className="skeleton" />
        <div className="skeleton" />
      </div>
    );
  if (result.state === "error") return <ErrorBox message={result.message} onRetry={onRetry} />;
  const d = result.data;
  if (d.status === "not_ready") return <NotReadyBox reason={d.reason} fix={d.fix} />;
  const current = d.medicines.filter((m) => m.role === "current");
  const findings = [
    ...d.allergy_findings.map((f) => ({ level: f.level, el: <AllergyCard key={`a${f.allergy_id}-${f.medicine.key}`} f={f} /> })),
    ...d.pairs.map((p) => ({ level: p.level ?? null, el: <PairCard key={`${p.a.key}|${p.b.key}`} p={p} /> })),
  ].sort((x, y) => rank(y.level) - rank(x.level));
  return (
    <>
      {d.overall === "Critical" && (
        <div className="risk-panel lv-critical" role="alert">
          <Warning size={22} weight="fill" aria-hidden="true" />
          <p>{d.overall_text}</p>
        </div>
      )}
      <RiskMeter level={d.overall ?? null} />
      {d.overall === "High" && <p className="notice risk-note lv-high">{d.overall_text}</p>}
      {d.overall === "Medium" && <p className="risk-note">{d.overall_text}</p>}
      {!d.overall && <p className="risk-note">{d.overall_text}</p>}
      {d.rules.status === "not_ready" && <NotReadyBox reason={d.rules.reason} fix={d.rules.fix} title={d.rules.source_label} />}

      <details className="checked">
        <summary>
          What was checked: {d.medicines.length - current.length} to add, {current.length} current{" "}
          {current.length === 1 ? "medicine" : "medicines"}, {d.allergies_checked} {d.allergies_checked === 1 ? "allergy" : "allergies"}
        </summary>
        <p className="small">
          Each medicine to add is compared with every current medicine and with the other medicines to add, by their ingredients. Current
          medicines are the ones in your history that you take now, and the ones whose dates were not entered (they are included).
        </p>
        {current.length > 0 ? (
          <ul className="small">
            {current.map((m) => (
              <li key={m.medicine.key}>
                {m.medicine.name}
                {m.dates_not_entered && <> <Sticker>Dates not entered</Sticker></>}
                {m.checked_by_name_only && <> <Sticker wrap>Checked by name only</Sticker></>}
              </li>
            ))}
          </ul>
        ) : (
          <p className="small muted">
            No current medicines in <Link to="/history?tab=medicines">your medical history</Link>.
          </p>
        )}
        <p className="small muted">{d.allergy_note}</p>
        <p className="small muted">
          {d.level_rule} <Link to="/about/data">How levels are set</Link>
        </p>
      </details>

      {graph}

      {findings.length > 0 && <ul className="finding-list">{findings.map((f) => f.el)}</ul>}
      {findings.length === 0 && d.pairs_checked > 0 && (
        <p className="small muted">
          {d.pairs_checked} {d.pairs_checked === 1 ? "pair was" : "pairs were"} checked. None matched a rule, a label sentence or a shared
          ingredient.
        </p>
      )}
      <Disclaimer />
    </>
  );
}
