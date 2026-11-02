import type { ReactNode } from "react";

export type StickerTone = "neutral" | "good" | "danger";

const TONE: Record<StickerTone, string> = { neutral: "", good: " badge-ok", danger: " badge-err" };

/** A small label: 10% tint, coloured text, fine ring. Mint = good, rose = a problem, grey = everything else. */
export function Sticker({ tone = "neutral", children, wrap = false }: { tone?: StickerTone; children: ReactNode; wrap?: boolean }) {
  return <span className={`badge${TONE[tone]}${wrap ? " badge-wrap" : ""}`}>{children}</span>;
}
