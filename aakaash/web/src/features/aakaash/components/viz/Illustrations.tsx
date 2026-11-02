import type { ReactNode } from "react";

/* Line art for empty states. One style: 1.5 px stroke, round caps, grey only, no fill, no gradients. */
function Art({ children }: { children: ReactNode }) {
  return (
    <svg className="illo" width="120" height="96" viewBox="0 0 120 96" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      {children}
    </svg>
  );
}

/** A blister strip with every cell empty. */
export function NoMedicinesArt() {
  return (
    <Art>
      <rect x="14" y="26" width="92" height="44" rx="6" />
      {[0, 1, 2].map((i) => (
        <g key={i}>
          <circle cx={35 + i * 25} cy="40" r="7" strokeDasharray="3 3" />
          <circle cx={35 + i * 25} cy="58" r="7" strokeDasharray="3 3" />
        </g>
      ))}
      <path d="M14 78h92" strokeDasharray="2 5" />
    </Art>
  );
}

/** A medical tag with empty lines. */
export function NoAllergiesArt() {
  return (
    <Art>
      <path d="M22 30a6 6 0 0 1 6-6h46l22 24-22 24H28a6 6 0 0 1-6-6z" />
      <circle cx="34" cy="48" r="3" />
      <path d="M46 40h28M46 48h20M46 56h24" strokeDasharray="3 4" />
      <path d="M96 48h10" />
    </Art>
  );
}

/** A magnifying glass over an empty list. */
export function NoResultsArt() {
  return (
    <Art>
      <rect x="16" y="18" width="58" height="60" rx="6" />
      <path d="M26 34h30M26 46h22M26 58h26" strokeDasharray="3 4" />
      <circle cx="78" cy="56" r="14" />
      <path d="M88 66l14 14" />
      <path d="M72 52l12 8M84 52l-12 8" />
    </Art>
  );
}
