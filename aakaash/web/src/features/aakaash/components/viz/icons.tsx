import type { ReactNode, SVGProps } from "react";
import type { RiskLevel } from "../../api";

/* Custom icons. One family: 24 px grid, 1.5 px stroke, round caps and joins, no fill (the Critical
   level icon is the one filled shape, so it differs from High by more than colour). Colour comes from
   currentColor; every icon is paired with a text label by its caller or carries its own aria-label. */

type SvgProps = Omit<SVGProps<SVGSVGElement>, "children"> & { size?: number; label?: string };

function Svg({ size = 20, label, children, ...rest }: SvgProps & { children: ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      focusable="false"
      {...rest}
    >
      {children}
    </svg>
  );
}

// ---- dosage-form families (medsafe/forms.py) ------------------------------------------------
export const FORM_LABEL: Record<string, string> = {
  "oral solid": "Oral solid",
  "oral liquid": "Oral liquid",
  injectable: "Injectable",
  topical: "Topical",
  "eye/ear": "Eye or ear",
  nasal: "Nasal",
  inhalation: "Inhalation",
  "mouth/throat": "Mouth or throat",
  "rectal/vaginal": "Rectal or vaginal",
  other: "Other form",
  unknown: "Form not stated",
};
export const formLabel = (family: string | null | undefined) => FORM_LABEL[family ?? "unknown"] ?? FORM_LABEL.unknown;

const FORM_DRAW: Record<string, ReactNode> = {
  "oral solid": (
    <g transform="rotate(-40 12 12)">
      <rect x="2.5" y="8.5" width="19" height="7" rx="3.5" />
      <path d="M12 8.5v7" />
    </g>
  ),
  "oral liquid": (
    <>
      <path d="M9.5 3h5M10.5 3v3.5M13.5 3v3.5" />
      <path d="M8 10a3.5 3.5 0 0 1 2.5-3.5h3A3.5 3.5 0 0 1 16 10v9a2 2 0 0 1-2 2h-4a2 2 0 0 1-2-2z" />
      <path d="M8 13.5h8" />
    </>
  ),
  injectable: (
    <g transform="rotate(45 12 12)">
      <rect x="9.5" y="5.5" width="5" height="10" rx="1" />
      <path d="M12 15.5v5M12 5.5V2.5M9.5 2.5h5M9.5 8.5h2M9.5 11.5h2" />
    </g>
  ),
  topical: (
    <>
      <path d="M9 3h6l-.6 3H9.6z" />
      <path d="M8 6h8l-1.4 13.2a1.5 1.5 0 0 1-1.5 1.3h-2.2a1.5 1.5 0 0 1-1.5-1.3z" />
      <path d="M9.4 21h5.2" />
    </>
  ),
  "eye/ear": (
    <>
      <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" />
      <circle cx="12" cy="12" r="3" />
    </>
  ),
  nasal: (
    <>
      <rect x="8" y="11" width="8" height="10" rx="2" />
      <path d="M10 11V7h4v4M12 7V3.5" />
      <path d="M5 4.5l2.2 1.5M4.5 8h3M19 4.5L16.8 6M19.5 8h-3" />
    </>
  ),
  inhalation: (
    <>
      <rect x="8" y="3" width="6" height="9" rx="1" />
      <path d="M6 12h10v6a3 3 0 0 1-3 3H9a3 3 0 0 1-3-3z" />
      <path d="M16 17h4.5M17.5 14.5h3" />
    </>
  ),
  "mouth/throat": (
    <>
      <path d="M3 12c3-4 6-5 9-3 3-2 6-1 9 3-3 4-6 5-9 5s-6-1-9-5z" />
      <path d="M3 12h18" />
    </>
  ),
  "rectal/vaginal": (
    <g transform="rotate(25 12 12)">
      <path d="M12 2.5c3 0 4.5 3.7 4.5 6.5v9a2 2 0 0 1-2 2h-5a2 2 0 0 1-2-2V9c0-2.8 1.5-6.5 4.5-6.5z" />
      <path d="M7.5 12.5h9" />
    </g>
  ),
  other: (
    <>
      <rect x="3" y="7" width="18" height="13" rx="2" />
      <path d="M9 7V5.5A1.5 1.5 0 0 1 10.5 4h3A1.5 1.5 0 0 1 15 5.5V7M12 11v5M9.5 13.5h5" />
    </>
  ),
  unknown: (
    <>
      <circle cx="12" cy="12" r="9" strokeDasharray="3 3" />
      <path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 .9-1 1.7M12 16.8h.01" />
    </>
  ),
};

/** The icon of a dosage-form family. Without `label` it is hidden from assistive technology (the text
 *  beside it says the form); with `label` it names itself. */
export function FormGlyph({ family, size = 20, label, ...rest }: SvgProps & { family: string | null | undefined }) {
  const key = family && family in FORM_DRAW ? family : "unknown";
  return (
    <Svg size={size} label={label} {...rest}>
      {FORM_DRAW[key]}
    </Svg>
  );
}

/** Icon and visible form name together. */
export function FormTag({ family, short = false }: { family: string | null | undefined; short?: boolean }) {
  return (
    <span className="form-tag" data-family={family ?? "unknown"}>
      <FormGlyph family={family} size={16} />
      <span>{short ? formLabel(family).split(" ")[0] : formLabel(family)}</span>
    </span>
  );
}

// ---- risk levels: three different shapes ----------------------------------------------------
// Medium: circle. High: triangle. Critical: octagon, filled. The exclamation mark is drawn in all three.
const MARK = <path d="M12 8.2v4.8M12 16.2h.01" />;

export function LevelGlyph({ level, size = 16, ...rest }: SvgProps & { level: RiskLevel | null }) {
  if (level === "Critical")
    return (
      <Svg size={size} {...rest}>
        <path d="M8.2 2.8h7.6l5.4 5.4v7.6l-5.4 5.4H8.2l-5.4-5.4V8.2z" fill="currentColor" />
        <path d="M12 8v5M12 16.2h.01" stroke="rgb(var(--c-card))" strokeWidth={2} />
      </Svg>
    );
  if (level === "High")
    return (
      <Svg size={size} {...rest}>
        <path d="M12 3.2 21.5 19.8h-19z" />
        <path d="M12 10v4.2M12 17h.01" />
      </Svg>
    );
  if (level === "Medium")
    return (
      <Svg size={size} {...rest}>
        <circle cx="12" cy="12" r="9" />
        {MARK}
      </Svg>
    );
  return (
    <Svg size={size} {...rest}>
      <circle cx="12" cy="12" r="9" strokeDasharray="3 3" />
      <path d="M8.5 12h7" />
    </Svg>
  );
}

// ---- allergy severity: one, two or three bars, plus a dashed ring when not known ---------------
export type SeverityKey = "mild" | "moderate" | "severe" | "unknown";

export function SeverityGlyph({ severity, size = 16, ...rest }: SvgProps & { severity: SeverityKey }) {
  const n = severity === "mild" ? 1 : severity === "moderate" ? 2 : severity === "severe" ? 3 : 0;
  if (n === 0)
    return (
      <Svg size={size} {...rest}>
        <circle cx="12" cy="12" r="9" strokeDasharray="3 3" />
        <path d="M9.8 9.8a2.3 2.3 0 1 1 3.3 2.1c-.6.3-.9.8-.9 1.4M12 16.5h.01" />
      </Svg>
    );
  return (
    <Svg size={size} {...rest}>
      {[0, 1, 2].map((i) => {
        const h = 6 + i * 5;
        return <rect key={i} x={3.5 + i * 6.5} y={20 - h} width="4" height={h} rx="1" fill={i < n ? "currentColor" : "none"} />;
      })}
    </Svg>
  );
}

/** Small icons for the sections a US label can have: filled when the section exists, outlined when it does not. */
export function SectionGlyph({ present, size = 16, ...rest }: SvgProps & { present: boolean }) {
  return (
    <Svg size={size} {...rest}>
      <path d="M6 3h8l4 4v14H6z" fill={present ? "currentColor" : "none"} fillOpacity={present ? 0.18 : 0} strokeDasharray={present ? undefined : "2.5 2.5"} />
      <path d="M14 3v4h4" />
      {present && <path d="M9 14.5l2 2 4-4.5" />}
    </Svg>
  );
}
