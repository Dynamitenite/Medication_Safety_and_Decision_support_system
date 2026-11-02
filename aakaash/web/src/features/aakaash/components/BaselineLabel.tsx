import { Sticker } from "./Sticker";

/** A neutral "Baseline" sticker next to the full sentence, which stays as text. */
export function BaselineLabel({ text }: { text: string }) {
  return (
    <p className="baseline">
      <Sticker>Baseline</Sticker>
      <span>{text}</span>
    </p>
  );
}
