import { useId } from "react";
import type { MedicineResponse } from "../../api";
import { SectionGlyph } from "./icons";

/** The sections this app reads from a US label, in the order the label tabs use. */
const SECTIONS: [string, string][] = [
  ["boxed_warning", "Boxed warning"],
  ["indications", "Indications"],
  ["contraindications", "Contraindications"],
  ["warnings_precautions", "Warnings and precautions"],
  ["precautions", "Precautions"],
  ["drug_interactions", "Drug interactions"],
  ["adverse_reactions", "Adverse reactions"],
  ["specific_populations", "Specific populations"],
];

/** Which sections the linked label has: a filled page icon with a tick when present, a dashed outline when not. */
export function LabelSectionStrip({ label }: { label: Pick<MedicineResponse, "sections"> }) {
  const id = useId();
  const have = new Set(label.sections.map((s) => s.key));
  const n = SECTIONS.filter(([k]) => have.has(k)).length;
  return (
    <div className="section-strip">
      <p className="small muted" id={`${id}-h`}>
        Sections on this label: {n} of {SECTIONS.length}
      </p>
      <ul aria-labelledby={`${id}-h`}>
        {SECTIONS.map(([k, name]) => {
          const on = have.has(k);
          return (
            <li key={k} className={on ? "on" : "off"}>
              <SectionGlyph present={on} />
              <span>
                {name}
                <span className="sr-only">: {on ? "available" : "not on this label"}</span>
              </span>
              {!on && <span className="small muted" aria-hidden="true"> · none</span>}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
