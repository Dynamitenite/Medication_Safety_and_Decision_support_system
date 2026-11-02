// Which alternatives go into the price chart. Pure logic.
export type PriceInput = {
  id: string;
  name: string;
  manufacturer: string | null;
  pack_size: string;
  price: number | null;
  discontinued?: boolean;
  different_pack_size?: boolean;
};
export type PriceBar = PriceInput & { price: number; selected: boolean };
export type PriceSelection = {
  bars: PriceBar[];
  /** alternatives listed but left out because the catalogue lists no price for them */
  noPrice: number;
  /** alternatives with a price that are not among the cheapest `limit` */
  notShown: number;
};

export const PRICE_LIMIT = 15;

/** The cheapest `limit` same-form alternatives with a price, plus the selected brand (when it has a price),
 *  all cheapest first. A price of 0 or null is "not stated" and is never drawn as a bar. */
export function selectPrices(alts: PriceInput[], selected: PriceInput | null, limit = PRICE_LIMIT): PriceSelection {
  const priced = alts.filter((a): a is PriceBar => a.price != null && a.price > 0).map((a) => ({ ...a, selected: false }));
  priced.sort((a, b) => a.price - b.price || a.name.localeCompare(b.name));
  const shown = priced.slice(0, limit);
  const bars = [...shown];
  if (selected && selected.price != null && selected.price > 0) bars.push({ ...(selected as PriceBar), selected: true });
  bars.sort((a, b) => a.price - b.price || Number(b.selected) - Number(a.selected) || a.name.localeCompare(b.name));
  return { bars, noPrice: alts.length - priced.length, notShown: priced.length - shown.length };
}
