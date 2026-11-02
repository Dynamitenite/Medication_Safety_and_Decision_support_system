export const DISCLAIMER = "Informational only. Not a substitute for advice from your doctor or pharmacist.";

/** The one-line disclaimer shown in the footer and under every risk result. */
export function Disclaimer({ className = "" }: { className?: string }) {
  return <p className={`small muted disclaimer ${className}`.trim()}>{DISCLAIMER}</p>;
}
