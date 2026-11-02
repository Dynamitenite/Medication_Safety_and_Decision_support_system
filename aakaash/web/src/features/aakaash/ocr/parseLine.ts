// SOURCE: NOT IN PAPERS. Own rules for reading one line of a typed or printed prescription.
// Conservative: a field is filled only when its pattern is clearly there, and is left empty
// otherwise. Nothing here picks a medicine; the review screen shows catalogue matches and the user
// confirms each line. No imports, so `node --test` can run it with type stripping.

export type ParsedLine = {
  raw: string;
  /** Text to search the medicine list with, or null when the line does not look like a medicine. */
  name: string | null;
  /** The form word as written ("Tab.", "Cap."), if the line starts with one. */
  form: string | null;
  /** A strength with its unit ("500mg", "1.2 g", "250 mg/5 ml"). */
  strength: string | null;
  /** An amount per dose written with a volume or unit count ("5 ml", "1 tab"). */
  dose: string | null;
  /** The frequency as written ("BD", "1-0-1"). */
  frequency: string | null;
  /** What the frequency means in plain words. */
  frequencyText: string | null;
  durationDays: number | null;
  /** The duration as written ("x 5 days", "for 1 week"). */
  durationText: string | null;
  /** Food timing in plain words ("after food", "before breakfast"). */
  food: string | null;
};

type Hit = { start: number; end: number };

const NUMBERING = /^\s*(?:[-*•●]|\(?\d{1,2}[.)\]:]|\(?[ivx]{1,4}[.)\]])\s*/i;
const FORM = /^(tab(?:let)?s?|cap(?:sule)?s?|syr(?:up)?|inj(?:ection)?)(\.?)(?=\s|$)\s*/i;
const HEADER = /^(rx|r\/x|dr\.?|doctor|date|name|patient|age|sex|gender|diagnosis|advice|adv|signature|sign|reg(?:istration)?|hospital|clinic|phone|address|follow[- ]?up)\b/i;

const FREQ_WORDS: Record<string, string> = {
  od: "once a day",
  bd: "twice a day",
  bid: "twice a day",
  tds: "three times a day",
  tid: "three times a day",
  qid: "four times a day",
  hs: "at bedtime",
  sos: "only when needed",
};
const FREQ_WORD = /(?<![\w.])(od|bd|bid|tds|tid|qid|hs|sos)(?![\w])/i;
// 1-0-1 (morning, afternoon, night) or 1-0-0-1 (morning, afternoon, evening, night); ½ allowed
const FREQ_SLOTS = /(?<![\w./-])([012½](?:\s*-\s*[012½]){2,3})(?![\w./-])/;
const SLOT_NAMES: Record<number, string[]> = { 3: ["morning", "afternoon", "night"], 4: ["morning", "afternoon", "evening", "night"] };

const DURATION = /(?:(?:\bx|×|\bfor)\s*)?(?<![\d.])(\d{1,3})\s*(days?|d|weeks?|wks?|months?)(?![\w])/i;
const FOOD_WORDS = /\b(before|after)\s+(food|meals?|breakfast|lunch|dinner)\b/i;
const FOOD_SHORT = /(?<![\w.])(a\.?c\.?|p\.?c\.?)(?![\w])/i;
const STRENGTH = /(?<![\w.])(\d+(?:\.\d+)?\s*(?:mg|mcg|µg|g|gm|iu|%)(?:\s*\/\s*(?:\d+(?:\.\d+)?\s*)?(?:ml|g))?)(?![\w])/i;
const DOSE = /(?<![\w.])(\d+(?:\.\d+)?\s*(?:ml|tabs?|caps?|puffs?|drops?))(?![\w])/i;

const tidy = (s: string) => s.replace(/\s+/g, " ").trim();

function find(text: string, rx: RegExp): (Hit & { m: RegExpExecArray }) | null {
  const m = rx.exec(text);
  return m ? { start: m.index, end: m.index + m[0].length, m } : null;
}

function slotText(written: string): string {
  const parts = written.split("-").map((p) => p.trim());
  const names = SLOT_NAMES[parts.length];
  return parts.map((p, i) => `${p} ${names[i]}`).join(", ");
}

export function parseLine(raw: string): ParsedLine {
  const out: ParsedLine = {
    raw, name: null, form: null, strength: null, dose: null, frequency: null, frequencyText: null,
    durationDays: null, durationText: null, food: null,
  };
  let text = tidy(raw).replace(NUMBERING, "");
  if (!text || HEADER.test(text)) return out;
  const f = FORM.exec(text);
  if (f) {
    out.form = f[1] + f[2];
    text = text.slice(f[0].length);
  }
  const hits: Hit[] = [];
  const freq = find(text, FREQ_SLOTS) ?? find(text, FREQ_WORD);
  if (freq) {
    out.frequency = tidy(freq.m[1]).replace(/\s*-\s*/g, "-");
    out.frequencyText = /\d|½/.test(out.frequency) ? slotText(out.frequency) : FREQ_WORDS[out.frequency.toLowerCase()];
    if (!/\d|½/.test(out.frequency)) out.frequency = out.frequency.toUpperCase();
    hits.push(freq);
  }
  const dur = find(text, DURATION);
  if (dur) {
    const n = Number(dur.m[1]);
    const unit = dur.m[2].toLowerCase();
    out.durationText = tidy(dur.m[0]);
    // days and weeks are exact; a month has no fixed number of days, so it is not converted
    out.durationDays = unit.startsWith("d") ? n : unit.startsWith("w") ? n * 7 : null;
    hits.push(dur);
  }
  const food = find(text, FOOD_WORDS);
  if (food) {
    out.food = `${food.m[1].toLowerCase()} ${food.m[2].toLowerCase()}`;
    hits.push(food);
  } else {
    const short = find(text, FOOD_SHORT);
    if (short) {
      out.food = short.m[1].toLowerCase().startsWith("a") ? "before food" : "after food";
      hits.push(short);
    }
  }
  const strength = find(text, STRENGTH);
  if (strength) {
    out.strength = tidy(strength.m[1]);
    hits.push(strength);
  }
  const dose = find(text, DOSE);
  if (dose && !(strength && dose.start < strength.end && dose.end > strength.start)) {
    out.dose = tidy(dose.m[1]);
    hits.push(dose);
  }
  // A line counts as a medicine only when it has a form word or something to take it by;
  // free text such as "Review after one week" is left empty for the user to type or drop.
  if (!out.form && hits.length === 0) return out;
  const cut = hits.length ? Math.min(...hits.map((h) => h.start)) : text.length;
  const name = text.slice(0, cut).replace(/[\s,;:\-–]+$/, "").trim();
  out.name = /[a-z]{2}/i.test(name) && !text.slice(0, cut).includes(":") ? name : null;
  return out;
}
