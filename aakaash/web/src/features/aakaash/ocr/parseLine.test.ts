// SOURCE: NOT IN PAPERS. FIXTURES ONLY: every prescription line below is hand-written to exercise
// the parser. None of it is a real prescription and none of it may appear in the UI.
// Run from aakaash/web:  npm test   (Node's built-in test runner; Node strips the types)
import { test } from "node:test";
import assert from "node:assert/strict";
import { parseLine } from "./parseLine.ts";
import type { ParsedLine } from "./parseLine.ts";

const EMPTY = { name: null, form: null, strength: null, dose: null, frequency: null, frequencyText: null, durationDays: null, durationText: null, food: null };

function check(raw: string, want: Partial<ParsedLine>) {
  const got = parseLine(raw);
  assert.deepEqual({ ...got, raw: undefined }, { ...EMPTY, ...want, raw: undefined }, raw);
}

test("numbered tablet with 1-0-1, days and food", () =>
  check("1. Tab. Dolo 650 1-0-1 x 5 days after food", {
    form: "Tab.", name: "Dolo 650", frequency: "1-0-1", frequencyText: "1 morning, 0 afternoon, 1 night",
    durationDays: 5, durationText: "x 5 days", food: "after food",
  }));

test("capsule with strength and TDS", () =>
  check("2) Cap. Mox 500mg TDS x 7 days", {
    form: "Cap.", name: "Mox", strength: "500mg", frequency: "TDS", frequencyText: "three times a day", durationDays: 7, durationText: "x 7 days",
  }));

test("syrup: a volume is a dose, not a strength", () =>
  check("Syr. Crocin 5 ml TDS for 3 days", {
    form: "Syr.", name: "Crocin", dose: "5 ml", frequency: "TDS", frequencyText: "three times a day", durationDays: 3, durationText: "for 3 days",
  }));

test("form word without a dot, OD, before food", () =>
  check("Tab Pan 40 mg OD before food", { form: "Tab", name: "Pan", strength: "40 mg", frequency: "OD", frequencyText: "once a day", food: "before food" }));

test("no strength and HS: the number stays in the name", () =>
  check("Tab. Warf 5 HS", { form: "Tab.", name: "Warf 5", frequency: "HS", frequencyText: "at bedtime" }));

test("injection with a decimal strength and BD", () =>
  check("3. Inj. Augmentin 1.2 g BD x5 days", {
    form: "Inj.", name: "Augmentin", strength: "1.2 g", frequency: "BD", frequencyText: "twice a day", durationDays: 5, durationText: "x5 days",
  }));

test("weeks are converted to days; AC is before food", () =>
  check("Tab. Azithral 500 mg OD for 1 week AC", {
    form: "Tab.", name: "Azithral", strength: "500 mg", frequency: "OD", frequencyText: "once a day", durationDays: 7, durationText: "for 1 week", food: "before food",
  }));

test("BID and PC", () =>
  check("Cap. Omez 20mg BID PC", { form: "Cap.", name: "Omez", strength: "20mg", frequency: "BID", frequencyText: "twice a day", food: "after food" }));

test("SOS with no strength", () =>
  check("Tab Montair LC SOS", { form: "Tab", name: "Montair LC", frequency: "SOS", frequencyText: "only when needed" }));

test("after meals and a four-slot pattern", () =>
  check("Tab. Metformin 500 mg 1-0-0-1 after meals", {
    form: "Tab.", name: "Metformin", strength: "500 mg", frequency: "1-0-0-1", frequencyText: "1 morning, 0 afternoon, 0 evening, 1 night", food: "after meals",
  }));

test("micrograms, before breakfast", () =>
  check("Tab. Thyronorm 50 mcg 1-0-0 before breakfast", {
    form: "Tab.", name: "Thyronorm", strength: "50 mcg", frequency: "1-0-0", frequencyText: "1 morning, 0 afternoon, 0 night", food: "before breakfast",
  }));

test("strength per volume is one strength", () =>
  check("Syr. Amoxyclav 228.5 mg/5 ml BD", { form: "Syr.", name: "Amoxyclav", strength: "228.5 mg/5 ml", frequency: "BD", frequencyText: "twice a day" }));

test("a month is not converted to days", () =>
  check("Tab. Shelcal 500 OD x 1 month", { form: "Tab.", name: "Shelcal 500", frequency: "OD", frequencyText: "once a day", durationText: "x 1 month" }));

test("a form word alone is enough to read a name", () => check("Tab. Ecosprin 75", { form: "Tab.", name: "Ecosprin 75" }));

test("header lines are left empty", () => {
  check("Rx", {});
  check("Dr. A. Fixture, MBBS", {});
  check("Date: 12-03-2026", {});
  check("Patient name: Fixture Person", {});
});

test("free text with nothing to take it by is left empty", () => {
  check("Review after one week", {});
  check("Plenty of fluids", {});
  check("", {});
});

test("a date is never read as a 1-0-1 pattern", () => assert.equal(parseLine("Tab. Dolo 650 12-03-2026").frequency, null));
