// SOURCE: NOT IN PAPERS. FIXTURES ONLY: every value below is hand-written to exercise the layout and
// selection code. None of it is real patient or product data and none of it may appear in the UI.
// Run from aakaash/web:  npm test
import { test } from "node:test";
import assert from "node:assert/strict";
import { bmiBand, bmiScale } from "./bmi.ts";
import { layoutTimeline, type TimelineInput } from "./timeline.ts";
import { selectPrices, type PriceInput } from "./priceChart.ts";
import { layoutGraph, MAX_NODES, pillWidth, wrapLabel, type GraphInput } from "./graph.ts";

// ---- BMI -------------------------------------------------------------------------------------
test("BMI band edges follow the WHO adult ranges", () => {
  assert.equal(bmiBand(18.4).id, "underweight");
  assert.equal(bmiBand(18.5).id, "normal");
  assert.equal(bmiBand(24.9).id, "normal");
  assert.equal(bmiBand(25).id, "overweight");
  assert.equal(bmiBand(29.9).id, "overweight");
  assert.equal(bmiBand(30).id, "obese");
  assert.equal(bmiBand(55).id, "obese");
});

test("BMI scale is hidden without a date of birth, under 18, or without a BMI, and says why", () => {
  for (const [age, bmi] of [[null, 22], [undefined, 22], [17, 22], [0, 22]] as const) {
    const s = bmiScale(age, bmi);
    assert.equal(s.show, false);
    assert.ok(!s.show && s.reason.length > 20);
  }
  const noBmi = bmiScale(40, null);
  assert.ok(!noBmi.show && /height and weight/.test(noBmi.reason));
});

test("BMI scale is shown from age 18 with a marker clamped to the axis", () => {
  const s = bmiScale(18, 22.5);
  assert.ok(s.show && s.band.id === "normal" && s.position > 0.2 && s.position < 0.5);
  const low = bmiScale(30, 9);
  assert.ok(low.show && low.position === 0 && low.band.id === "underweight");
  const high = bmiScale(30, 60);
  assert.ok(high.show && high.position === 1 && high.band.id === "obese");
});

// ---- timeline --------------------------------------------------------------------------------
const item = (id: string, start: string | null, end: string | null, openEnded = false, outcome = "unknown"): TimelineInput => ({ id, label: id, start, end, outcome, openEnded });

test("timeline: ongoing course runs to today and is flagged", () => {
  const l = layoutTimeline([item("a", "2026-01-01", null, true)], "2026-03-01");
  const b = l.bars[0];
  assert.equal(b.ongoing, true);
  assert.ok(Math.abs(b.x1 - l.todayX) < 1e-9);
  assert.equal(b.days, 60);
  assert.ok(l.todayX > b.x0 && l.todayX < 1);
});

test("timeline: items with no start date are listed, never drawn", () => {
  const l = layoutTimeline([item("dated", "2026-01-01", "2026-01-10"), item("none", null, null), item("endonly", null, "2026-02-01")], "2026-03-01");
  assert.deepEqual(l.bars.map((b) => b.id), ["dated"]);
  assert.deepEqual(l.undated.map((u) => u.id).sort(), ["endonly", "none"]);
});

test("timeline: overlapping courses keep their own rows and overlap on the axis", () => {
  const l = layoutTimeline([item("late", "2026-02-01", "2026-02-20"), item("early", "2026-01-15", "2026-02-10")], "2026-03-01");
  assert.deepEqual(l.bars.map((b) => b.id), ["early", "late"]); // sorted by start
  const [early, late] = l.bars;
  assert.ok(late.x0 < early.x1, "bars overlap");
  assert.ok(early.x0 >= 0 && late.x1 <= 1);
});

test("timeline: a future course is flagged and an empty list still has an axis", () => {
  const l = layoutTimeline([item("soon", "2026-04-01", null, true)], "2026-03-01");
  assert.equal(l.bars[0].upcoming, true);
  assert.ok(l.bars[0].x0 > l.todayX);
  const empty = layoutTimeline([], "2026-03-01");
  assert.equal(empty.bars.length, 0);
  assert.ok(empty.todayX > 0 && empty.todayX < 1);
});

test("timeline: a one-day course is still a visible bar and an end before the start is clamped", () => {
  const l = layoutTimeline([item("one", "2026-01-10", "2026-01-10"), item("bad", "2026-01-20", "2026-01-05")], "2026-03-01");
  for (const b of l.bars) assert.ok(b.x1 > b.x0);
  assert.equal(l.bars.find((b) => b.id === "bad")!.days, 1);
});

test("timeline: axis ticks fall inside the axis and carry month labels for a short span", () => {
  const l = layoutTimeline([item("a", "2026-01-10", "2026-04-20")], "2026-05-01");
  assert.ok(l.ticks.length >= 3);
  assert.ok(l.ticks.every((k) => k.x >= 0 && k.x <= 1));
  assert.match(l.ticks[0].label, /^[A-Z][a-z]{2} 2026$/);
});

// ---- price chart -----------------------------------------------------------------------------
const alt = (id: string, price: number | null, extra: Partial<PriceInput> = {}): PriceInput => ({ id, name: `Brand ${id}`, manufacturer: null, pack_size: "strip of 10", price, ...extra });

test("price chart: cheapest 15 with a price, selected brand added and highlighted, cheapest first", () => {
  const alts = Array.from({ length: 20 }, (_, i) => alt(`b${i}`, 100 - i)); // 100 down to 81
  const sel = selectPrices(alts, alt("me", 90));
  assert.equal(sel.bars.length, 16);
  assert.equal(sel.notShown, 5);
  assert.deepEqual(sel.bars.map((b) => b.price), [...sel.bars.map((b) => b.price)].sort((a, b) => a - b));
  assert.equal(sel.bars.filter((b) => b.selected).length, 1);
  assert.equal(sel.bars[0].price, 81);
});

test("price chart: null and zero prices are counted, not drawn; no selected price means no selected bar", () => {
  const sel = selectPrices([alt("a", 10), alt("b", null), alt("c", 0)], alt("me", null));
  assert.deepEqual(sel.bars.map((b) => b.id), ["a"]);
  assert.equal(sel.noPrice, 2);
  assert.equal(selectPrices([], null).bars.length, 0);
});

test("price chart: equal prices are ordered by name so the order is stable", () => {
  const sel = selectPrices([alt("z", 5, { name: "Zed" }), alt("a", 5, { name: "Alpha" })], null);
  assert.deepEqual(sel.bars.map((b) => b.name), ["Alpha", "Zed"]);
});

// ---- interaction graph -----------------------------------------------------------------------
const med = (key: string, role: "new" | "current" = "current") => ({ key, name: key.toUpperCase(), role });

test("graph: nodes sit on one circle, new medicines first, one edge per finding", () => {
  const input: GraphInput = {
    medicines: [med("c1"), med("n1", "new"), med("c2")],
    pairs: [{ a: "n1", b: "c1", level: "Critical" }, { a: "n1", b: "c2", level: null }],
    allergies: [{ medicineKey: "n1", allergyId: 7, allergen: "Penicillin", level: "High" }],
  };
  const l = layoutGraph(input);
  assert.equal(l.mode, "circular");
  if (l.mode !== "circular") return;
  assert.deepEqual(l.nodes.map((n) => n.id), ["n1", "c1", "c2", "allergy:7"]);
  const c = l.size / 2;
  const radii = l.nodes.map((n) => Math.hypot(n.x - c, n.y - c));
  for (const r of radii) assert.ok(Math.abs(r - radii[0]) < 1e-6);
  assert.equal(l.edges.length, 3);
  assert.deepEqual(l.edges.map((e) => e.label), ["Critical", "No level", "High"]);
  assert.ok(l.edges.every((e) => e.targetId.startsWith("finding-") && !/\s/.test(e.targetId)));
  assert.equal(new Set(l.edges.map((e) => e.id)).size, 3);
});

test("graph: 12 nodes are drawn, 13 give the list only", () => {
  const meds = (n: number) => Array.from({ length: n }, (_, i) => med(`m${i}`, i < 2 ? "new" : "current"));
  assert.equal(layoutGraph({ medicines: meds(MAX_NODES), pairs: [], allergies: [] }).mode, "circular");
  const over = layoutGraph({ medicines: meds(MAX_NODES + 1), pairs: [], allergies: [] });
  assert.ok(over.mode === "list-only" && over.nodeCount === 13);
  // allergen nodes count toward the cap
  const withAllergy = layoutGraph({ medicines: meds(MAX_NODES), pairs: [], allergies: [{ medicineKey: "m0", allergyId: 1, allergen: "X", level: "Medium" }] });
  assert.equal(withAllergy.mode, "list-only");
});

test("graph: an allergen shared by two medicines is one node; edges to unknown nodes are dropped", () => {
  const l = layoutGraph({
    medicines: [med("n1", "new"), med("n2", "new")],
    pairs: [{ a: "n1", b: "ghost", level: "High" }],
    allergies: [{ medicineKey: "n1", allergyId: 3, allergen: "Pen", level: "High" }, { medicineKey: "n2", allergyId: 3, allergen: "Pen", level: "High" }],
  });
  assert.equal(l.mode, "circular");
  if (l.mode !== "circular") return;
  assert.equal(l.nodes.filter((n) => n.kind === "allergen").length, 1);
  assert.equal(l.edges.length, 2);
});

test("graph: a single medicine with no findings still lays out", () => {
  const l = layoutGraph({ medicines: [med("only", "new")], pairs: [], allergies: [] });
  assert.ok(l.mode === "circular" && l.nodes.length === 1 && l.edges.length === 0);
});

test("graph: long names wrap to the room beside the node and end in an ellipsis when cut", () => {
  assert.deepEqual(wrapLabel("Cofarin 5mg Tablet", 11), ["Cofarin 5mg", "Tablet"]);
  assert.deepEqual(wrapLabel("Short", 11), ["Short"]);
  const cut = wrapLabel("Vitamin D3 60000 IU weekly sachet long name test", 10);
  assert.equal(cut.length, 3);
  assert.ok(cut[2].endsWith("…") && cut.every((l) => l.length <= 10));
  assert.ok(wrapLabel("Supercalifragilisticexpialidocious", 8).every((l) => l.length <= 8));
});

test("graph: every node name stays inside the square, and level labels do not cover each other", () => {
  const size = 340; // about a 390 px phone
  const input: GraphInput = {
    medicines: ["Cofarin 5mg Tablet", "Ecosprin 75 Tablet", "Mox 500mg Capsule", "Dolo 650 Tablet", "Warf 5 Tablet", "Telma 40 Tablet"].map((n, i) => ({ key: `k${i}`, name: n, role: i < 3 ? "new" : "current" })),
    pairs: [{ a: "k0", b: "k3", level: "High" }, { a: "k1", b: "k3", level: "Critical" }, { a: "k2", b: "k4", level: null }, { a: "k0", b: "k4", level: "Medium" }],
    allergies: [{ medicineKey: "k2", allergyId: 1, allergen: "Amoxycillin", level: "Critical" }],
  };
  const l = layoutGraph(input, size, size / 2 - 88);
  assert.equal(l.mode, "circular");
  if (l.mode !== "circular") return;
  for (const n of l.nodes) {
    const w = Math.max(...n.lines.map((x) => x.length)) * 6.2;
    const left = n.anchor === "middle" ? n.tx - w / 2 : n.anchor === "start" ? n.tx : n.tx - w;
    assert.ok(left >= -1 && left + w <= size + 1, `${n.label} spans ${left}..${left + w}`);
  }
  for (let i = 0; i < l.edges.length; i++) {
    for (let j = i + 1; j < l.edges.length; j++) {
      const a = l.edges[i];
      const b = l.edges[j];
      const overlap = Math.abs(a.lx - b.lx) < (pillWidth(a.label) + pillWidth(b.label)) / 2 && Math.abs(a.ly - b.ly) < 22;
      assert.ok(!overlap, `${a.label} and ${b.label} overlap`);
    }
  }
});

test("timeline: axis labels fit the width they are given", () => {
  const items = [item("a", "2025-01-10", "2025-01-16"), item("b", "2026-02-01", null, true)];
  const wide = layoutTimeline(items, "2026-03-01", 10);
  const narrow = layoutTimeline(items, "2026-03-01", 3);
  assert.ok(narrow.ticks.length <= 3 && narrow.ticks.length >= 1);
  assert.ok(wide.ticks.length > narrow.ticks.length);
  for (const k of narrow.ticks) assert.ok(k.x >= 0 && k.x <= 1);
  assert.ok(wide.todayX > 0 && wide.todayX < 1);
});
