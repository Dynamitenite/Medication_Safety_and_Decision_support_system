// SOURCE: NOT IN PAPERS (own tooling). Captures every feature of the app for the paper with Playwright (Chromium).
// Light mode first, then dark; each at 1280x800 and 390x844, device scale factor 2.
// Usage (API and web already running; the demo account must exist, see artifacts/screens/CREDENTIALS.txt):
//   node scripts/paper-shots.mjs [baseUrl=http://localhost:4174] [outDir=../artifacts/screens/paper]
// It signs in as the demo account and does not change its data (nothing is added to the medicine list).
import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright";
import { pickMedicine, waitDetails, waitRisk } from "./lib/pw.mjs";

const base = process.argv[2] ?? "http://localhost:4174";
const out = path.resolve(process.argv[3] ?? "../artifacts/screens/paper");
const cred = Object.fromEntries(
  fs.readFileSync("../artifacts/screens/CREDENTIALS.txt", "utf8").trim().split(/\r?\n/).map((l) => l.split(": ")),
);
const MAX_TILE = 6500; // CSS px; at scale 2 this stays under Chromium's 16384 px texture limit
const THEMES = ["light", "dark"];
const VPS = [
  { name: "1280", width: 1280, height: 800, mobile: false },
  { name: "390", width: 390, height: 844, mobile: true },
];
const ECOSPRIN = { id: "72318", name: "Ecosprin 150 Tablet" };
const only = process.env.ONLY ? new RegExp(process.env.ONLY) : null;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const report = { files: [], overflow: [], problems: [] };

async function settle(page, ms = 700) {
  await page.waitForFunction(() => !document.querySelector(".skeleton") && !document.querySelector("[aria-busy=true]"), null, { timeout: 30000 }).catch(() => report.problems.push(`still busy: ${page.url()}`));
  await page.evaluate(() => document.fonts.ready);
  await sleep(ms);
}

/** Layout check: anything wider than the window that is not inside a scroll container. */
async function checkRight(page, label) {
  const r = await page.evaluate(() => {
    const W = document.documentElement.clientWidth;
    const bad = [];
    for (const el of document.querySelectorAll("body *")) {
      const b = el.getBoundingClientRect();
      if (!b.width || !b.height || b.right <= W + 1) continue;
      let p = el.parentElement, held = false;
      while (p && p !== document.body) {
        const ox = getComputedStyle(p).overflowX;
        if (["auto", "scroll", "hidden", "clip"].includes(ox) && p.getBoundingClientRect().right <= W + 1) { held = true; break; }
        p = p.parentElement;
      }
      if (!held) bad.push(`${el.tagName.toLowerCase()}.${String(el.className).slice(0, 30)} right=${Math.round(b.right)}`);
    }
    return { scrollW: document.documentElement.scrollWidth, W, bad: bad.slice(0, 4) };
  });
  if (r.scrollW > r.W || r.bad.length) report.overflow.push(`${label}: scrollWidth ${r.scrollW} vs ${r.W}; ${r.bad.join("; ")}`);
}

/** Save one screenshot. `file` is relative to this run's folder. */
async function save(page, dir, file, shot) {
  const full = path.join(dir, file);
  const vp = page.viewportSize();
  const h = await page.evaluate(() => document.documentElement.scrollHeight);
  if (h > vp.height && h < 15000) { await page.setViewportSize({ width: vp.width, height: h }); await sleep(300); }
  await shot(full);
  await page.setViewportSize(vp);
  report.files.push(full);
  await checkRight(page, full);
}

/** Whole page, or the page tiled at section boundaries when it is taller than MAX_TILE. */
async function shootPage(page, dir, name) {
  await settle(page);
  const h = await page.evaluate(() => document.documentElement.scrollHeight);
  if (h <= MAX_TILE) return save(page, dir, `${name}.png`, (f) => page.screenshot({ path: f, fullPage: true }));
  const cuts = await page.evaluate(() => [...document.querySelectorAll("#main > *")].map((e) => Math.floor(e.getBoundingClientRect().top + scrollY)));
  return tile(page, dir, name, 0, h, cuts);
}

async function tile(page, dir, name, from, to, cuts) {
  const W = page.viewportSize().width;
  const parts = [];
  let start = from;
  for (const c of [...cuts.filter((c) => c > from && c < to), to]) {
    if (c - start > MAX_TILE && parts.length === 0 && start === from) { parts.push([start, c]); start = c; continue; }
    if (c - start > MAX_TILE) { const prev = [...cuts, to].filter((x) => x > start && x < c).pop() ?? c; parts.push([start, prev]); start = prev; }
  }
  if (start < to) parts.push([start, to]);
  const names = parts.length === 1 ? [`${name}.png`] : parts.map((_, i) => `${name}-${"abcdefgh"[i]}.png`);
  for (const [i, [a, b]] of parts.entries()) {
    await save(page, dir, names[i], (f) => page.screenshot({ path: f, fullPage: true, clip: { x: 0, y: a, width: W, height: b - a } }));
  }
}

/** The #main children from the one whose heading matches `a` to the one before the heading matching `b` (or the end). */
async function shootRange(page, dir, name, a, b) {
  await settle(page);
  const info = await page.evaluate(([a, b]) => {
    const kids = [...document.querySelectorAll("#main > *")].map((e) => ({ t: ((e.matches("h1,h2,h3") ? e : e.querySelector("h1,h2,h3"))?.innerText ?? "").trim(), top: Math.floor(e.getBoundingClientRect().top + scrollY), bottom: Math.ceil(e.getBoundingClientRect().bottom + scrollY) }));
    const ia = kids.findIndex((k) => new RegExp(a).test(k.t));
    const ib = b ? kids.findIndex((k, i) => i > ia && new RegExp(b).test(k.t)) : -1;
    const end = ib === -1 ? kids.length : ib;
    return { ia, end, kids };
  }, [a, b]);
  if (info.ia < 0) { report.problems.push(`${name}: heading /${a}/ not found`); return; }
  const from = info.kids[info.ia].top;
  const to = info.kids[info.end - 1].bottom;
  await tile(page, dir, name, from - 8, to + 8, info.kids.slice(info.ia, info.end).map((k) => k.top));
}

async function shootEl(page, dir, name, selector, pad = 8) {
  await settle(page, 400);
  const el = page.locator(selector).first();
  await el.scrollIntoViewIfNeeded();
  await save(page, dir, `${name}.png`, (f) => el.screenshot({ path: f }));
}

const openAll = async (page, text) => {
  const sums = page.locator("details:not([open]) > summary").filter({ hasText: new RegExp("^" + text) });
  for (let i = await sums.count(); i > 0; i--) { await sums.first().click(); await sleep(250); }
};

async function addFlow(page, term, name) {
  await page.goto("/add");
  await page.waitForSelector("#to-add-h");
  await pickMedicine(page, term, name);
  await waitRisk(page);
  await waitDetails(page);
}

async function askOnce(page, q) {
  const card = page.locator("section[aria-labelledby=ask-h]");
  for (let tries = 1; tries <= 4; tries++) {
    await card.locator("input[type=text]").fill(q);
    await card.locator("button[type=submit]").click();
    await page.waitForFunction(() => { const c = document.querySelector("section[aria-labelledby=ask-h]"); return c && (c.querySelector(".ai-box") || c.querySelector("[role=alert]")) && !/Writing…/.test(c.innerText); }, null, { timeout: 90000 });
    if (await card.locator(".ai-box").count()) return true;
    report.problems.push(`ask "${q}" try ${tries}: ${(await card.innerText()).replace(/\s+/g, " ").slice(-160)}`);
    await sleep(25000);
  }
  return false;
}

async function runOne(browser, theme, vp) {
  const dir = path.join(out, theme, vp.name);
  fs.mkdirSync(dir, { recursive: true });
  const tag = `${theme}/${vp.name}`;
  const ctx = await browser.newContext({
    baseURL: base, viewport: { width: vp.width, height: vp.height }, deviceScaleFactor: 2, colorScheme: theme,
    isMobile: vp.mobile, hasTouch: vp.mobile, reducedMotion: "reduce",
  });
  await ctx.addInitScript((t) => { try { localStorage.setItem("medsafe.theme", t); } catch {} }, theme);
  const page = await ctx.newPage();
  const step = async (key, fn) => {
    if (only && !only.test(key)) return;
    try { await fn(); console.log(`ok   ${tag} ${key}`); }
    catch (e) { report.problems.push(`${tag} ${key}: ${String(e.message).split("\n")[0]}`); console.log(`FAIL ${tag} ${key}: ${String(e.message).split("\n")[0]}`); }
  };

  // signed out
  await step("01", async () => {
    await page.goto("/login");
    await page.locator("input[name=email]").fill(cred.email);
    await page.locator("input[name=password]").fill(cred.password);
    await shootPage(page, dir, "01-sign-in");
  });
  await step("02", async () => {
    await page.goto("/login");
    await page.locator("input[name=email]").fill("new.user@example.com");
    await page.locator("input[name=password]").fill("newuser123");
    await shootPage(page, dir, "02-sign-up");
  });
  const r = await ctx.request.post("/api/auth/login", { data: { email: cred.email, password: cred.password } });
  if (!r.ok()) throw new Error("sign-in failed " + r.status());

  await step("03", async () => { await page.goto("/"); await shootPage(page, dir, "03-home"); });
  await step("04", async () => { await page.goto("/profile"); await page.waitForSelector("text=Current medicines"); await shootPage(page, dir, "04-profile"); });
  await step("05", async () => { await page.goto("/history?tab=medicines"); await shootPage(page, dir, "05-history-medicines"); });
  await step("06", async () => {
    await page.goto("/search");
    const box = page.locator("main [role=combobox]").first();
    await box.click();
    await box.pressSequentially("ecosprin", { delay: 40 });
    await page.waitForSelector(".combo-opt");
    await sleep(800);
    await shootPage(page, dir, "06-medicine-search");
  });
  await step("07", async () => { await page.goto(`/medicine/${ECOSPRIN.id}`); await page.waitForSelector("#alt-h"); await shootPage(page, dir, "07-medicine-page"); });
  await step("08", async () => {
    const d = await (await ctx.request.get(`/api/medicine/${ECOSPRIN.id}`)).json();
    await page.goto(`/label/${d.ingredient_details[0].labels[0].set_id}`);
    await shootPage(page, dir, "08-label-page");
  });
  await step("09", async () => { await page.goto(`/alternatives?id=${ECOSPRIN.id}`); await page.waitForSelector("#alt-h"); await shootPage(page, dir, "09-alternatives"); });

  // safety check = Add new medicine, analysed against the demo profile (nothing is saved)
  await step("10", async () => { await addFlow(page, "abomox", "Abomox 500mg Capsule"); await openAll(page, "Why this warning"); await shootPage(page, dir, "10-safety-critical-allergy"); });
  await step("11", async () => { await addFlow(page, "ecosprin", ECOSPRIN.name); await openAll(page, "Why this warning"); await openAll(page, "Show the interaction graph"); await shootPage(page, dir, "11-safety-high"); });
  await step("12", async () => { await addFlow(page, "diclofenac sodium injection", "Diclofenac Sodium Injection"); await openAll(page, "Why this warning"); await shootPage(page, dir, "12-safety-medium"); });
  await step("13", async () => { await addFlow(page, "cetirizine 10mg", "Cetirizine 10mg Tablet"); await shootPage(page, dir, "13-safety-none"); });

  // drug-drug result with classifier type, evidence sentence and Integrated Gradients
  await step("14", async () => {
    await addFlow(page, "zocon 150", "Zocon 150 Tablet");
    await openAll(page, "Why this warning");
    const discs = page.locator("details.ddi-disclosure");
    let chosen = null;
    for (let i = 0; i < await discs.count(); i++) {
      const d = discs.nth(i);
      await d.locator("> summary").click();
      await d.locator(".ddi-type-line").waitFor({ timeout: 60000 });
      const txt = await d.locator(".ddi-type-line").innerText();
      if (!/No interaction stated/.test(txt)) { chosen = d; break; }
      await d.locator("> summary").click();
    }
    if (!chosen) { chosen = discs.first(); await chosen.locator("> summary").click(); report.problems.push(`${tag} 14: every sentence classed "No interaction stated"`); }
    await chosen.locator(".ddi-why > summary").click();
    await page.waitForSelector(".attr-sentence", { timeout: 120000 });
    await sleep(600);
    await shootEl(page, dir, "14-ddi-classifier-ig", "section[aria-labelledby=risk-h]");
  });

  // ask box: label question with sources, then a price question
  await step("15", async () => {
    await page.goto(`/medicine/${ECOSPRIN.id}`);
    await page.waitForSelector("#ask-h");
    await sleep(15000); // stay under the model's requests-per-minute limit
    if (!(await askOnce(page, "What are the bleeding risks?"))) throw new Error("no grounded answer after 4 tries");
    await shootEl(page, dir, "15-ask-label-grounded", "section[aria-labelledby=ask-h]");
  });
  await step("16", async () => {
    await page.goto(`/medicine/${ECOSPRIN.id}`);
    await page.waitForSelector("#ask-h");
    const card = page.locator("section[aria-labelledby=ask-h]");
    await card.locator("input[type=text]").fill("What is the cheapest alternative?");
    await card.locator("button[type=submit]").click();
    await card.locator(".alt-answer .alt-rows li").first().waitFor({ timeout: 30000 });
    await shootEl(page, dir, "16-ask-price-cheapest-5", "section[aria-labelledby=ask-h]");
  });
  await step("17", async () => {
    await page.goto(`/medicine/${ECOSPRIN.id}`);
    await page.waitForSelector("#ls-h");
    const card = page.locator("section[aria-labelledby=ls-h]");
    await card.locator("input[type=search]").fill("bleeding risk with blood thinners");
    await card.locator("button[type=submit]").click();
    await page.waitForFunction(() => /score|similarity|cosine|passage|result/i.test(document.querySelector("section[aria-labelledby=ls-h]")?.innerText ?? ""), null, { timeout: 60000 });
    await shootEl(page, dir, "17-label-search", "section[aria-labelledby=ls-h]");
  });
  await step("18", async () => {
    await page.goto("/checker");
    await pickMedicine(page, "genericart warfarin", "Genericart Warfarin 2mg Tablet");
    await pickMedicine(page, "ecosprin", ECOSPRIN.name);
    await page.getByRole("button", { name: "Check", exact: true }).click();
    await page.waitForFunction(() => document.querySelector("section[aria-labelledby=res-h]")?.getAttribute("aria-busy") === "false", null, { timeout: 60000 });
    await openAll(page, "Why this warning");
    await shootPage(page, dir, "18-interaction-checker");
  });

  // about pages
  await step("19", async () => {
    await page.goto("/about/data");
    await page.waitForSelector("#system-status-h");
    await sleep(2500);
    await shootRange(page, dir, "19-how-it-works-a", "^How it works$", "^Medicine catalogue");
    await shootRange(page, dir, "19-how-it-works-b", "^What the app does not do", "^DailyMed");
    await shootRange(page, dir, "19-how-it-works-c", "^The project$", null);
  });
  await step("20", async () => {
    await page.goto("/about/data");
    await page.waitForSelector("#system-status-h");
    await sleep(2500);
    await shootRange(page, dir, "20-about-data-catalogue", "^Medicine catalogue", "^What the app does not do");
    await shootRange(page, dir, "20-about-data-labels-rules", "^DailyMed", "^Interaction-type model");
    await shootRange(page, dir, "20-about-data-ddi-model", "^Interaction-type model", "^System components");
  });
  await step("21", async () => {
    await page.goto("/about/data");
    await page.waitForSelector("#system-status-h");
    await sleep(2500);
    await shootRange(page, dir, "21-status", "^System components", "^Sample patients$");
  });
  await ctx.close();
}

const browser = await chromium.launch({ headless: true });
for (const theme of THEMES) for (const vp of VPS) await runOne(browser, theme, vp);
await browser.close();
fs.writeFileSync(path.join(out, "run-report.json"), JSON.stringify({ ...report, files: report.files.map((f) => path.relative(out, f).replace(/\\/g, "/")) }, null, 1));
console.log(`\n${report.files.length} files; ${report.overflow.length} overflow notes; ${report.problems.length} problems`);
for (const x of report.overflow) console.log("OVERFLOW", x);
for (const x of report.problems) console.log("PROBLEM", x);
