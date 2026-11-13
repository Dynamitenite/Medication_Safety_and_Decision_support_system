// SOURCE: NOT IN PAPERS (own tooling). Captures every feature of the app for the paper with Playwright (Chromium).
// Landscape: 1600x900 viewport, device scale factor 2 (3200x1800 files), viewport screenshots only, light mode first, then dark.
// Each shot scrolls the key part of the page to the top of the viewport. If it does not fit, the page is zoomed out
// (document.body.style.zoom 0.85, 0.75, 0.67) until it does; text stays sharp at scale factor 2.
// Usage (API and web already running; the demo account must exist, see artifacts/screens/CREDENTIALS.txt):
//   node scripts/paper-shots.mjs [baseUrl=http://localhost:4174] [outDir=../artifacts/screens/paper]
// Files go to <outDir>/{light,dark}/NN-name.png. ONLY=<regex on step number> runs some steps.
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
const THEMES = ["light", "dark"];
const VIEW = { width: 1600, height: 900 };
const ZOOMS = [1, 0.85, 0.75, 0.67];
const ECOSPRIN = { id: "72318", name: "Ecosprin 150 Tablet" };
const only = process.env.ONLY ? new RegExp(process.env.ONLY) : null;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const report = { files: [], overflow: [], problems: [], zoom: {} };

async function settle(page, ms = 700) {
  await page.waitForFunction(() => !document.querySelector(".skeleton") && !document.querySelector("[aria-busy=true]") && !/Loading/.test(document.querySelector("#main")?.innerText ?? ""), null, { timeout: 30000 }).catch(() => report.problems.push(`still busy: ${page.url()}`));
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
      if (!held && !el.closest(".recharts-tooltip-wrapper")) bad.push(`${el.tagName.toLowerCase()}.${String(el.className).slice(0, 30)} right=${Math.round(b.right)}`);
    }
    return { scrollW: document.documentElement.scrollWidth, W, bad: bad.slice(0, 4) };
  });
  if (r.bad.length) report.overflow.push(`${label}: scrollWidth ${r.scrollW} vs ${r.W}; ${r.bad.join("; ")}`);
}

/** Zoom the page out by z. The sidebar and shell are 100vh, which the zoom would shrink, so they are stretched back. */
async function setZoom(page, z) {
  await page.evaluate((z) => {
    document.body.style.zoom = z === 1 ? "" : String(z);
    let s = document.getElementById("zfix");
    if (!s) { s = document.createElement("style"); s.id = "zfix"; document.head.append(s); }
    s.textContent = z === 1 ? "" : `.sidebar{height:calc(100vh / ${z}) !important}.app,.login-wrap{min-height:calc(100vh / ${z}) !important}`;
  }, z);
  await sleep(250);
}

/** Put the part of the page from `from` to the bottom of `to` (CSS selectors; default: the page top) at the top of the
 *  viewport, zooming out until it fits, then save the viewport. */
async function view(page, dir, name, { from = null, to = null, zooms = ZOOMS } = {}) {
  await settle(page);
  const file = path.join(dir, `${name}.png`);
  let used = 1, fits = true;
  for (const z of zooms) {
    await setZoom(page, z);
    used = z;
    if (!from) { await page.evaluate(() => scrollTo(0, 0)); break; }
    const r = await page.evaluate(([from, to]) => {
      const a = document.querySelector(from), b = document.querySelector(to ?? from);
      if (!a || !b) return null;
      a.scrollIntoView({ block: "start" });
      if (scrollY > 12) scrollBy(0, -12);
      const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
      return { height: rb.bottom - ra.top, vh: innerHeight };
    }, [from, to]);
    if (!r) throw new Error(`selector not found: ${from} .. ${to ?? from}`);
    fits = r.height <= r.vh - 70; // leave room for the line that follows the target
    if (fits) break;
  }
  if (!fits) { // too tall for one view: show the start of it at a readable size
    used = 0.85;
    await setZoom(page, used);
    await page.evaluate((from) => { document.querySelector(from).scrollIntoView({ block: "start" }); if (scrollY > 12) scrollBy(0, -12); }, from);
  }
  await sleep(250);
  await page.screenshot({ path: file });
  report.files.push(file);
  report.zoom[path.relative(out, file).replace(/\\/g, "/")] = { zoom: used, fits };
  if (!fits) report.problems.push(`${path.relative(out, file)}: target taller than the viewport even at zoom ${used}; the view starts at the target top`);
  await checkRight(page, file);
  await setZoom(page, 1);
}

/** Mark the #main children from the one whose heading matches `a` to the one before the heading matching `b`,
 *  so `view` can use [data-sf] .. [data-st]. */
async function markRange(page, a, b) {
  const ok = await page.evaluate(([a, b]) => {
    document.querySelectorAll("[data-sf],[data-st]").forEach((e) => { e.removeAttribute("data-sf"); e.removeAttribute("data-st"); });
    const kids = [...document.querySelectorAll("#main > *")];
    const head = (e) => ((e.matches("h1,h2,h3") ? e : e.querySelector("h1,h2,h3"))?.innerText ?? "").trim();
    const ia = kids.findIndex((k) => new RegExp(a).test(head(k)));
    if (ia < 0) return false;
    const ib = b ? kids.findIndex((k, i) => i > ia && new RegExp(b).test(head(k))) : -1;
    const end = ib === -1 ? kids.length : ib;
    kids[ia].setAttribute("data-sf", "1");
    kids[end - 1].setAttribute("data-st", "1");
    return true;
  }, [a, b]);
  if (!ok) throw new Error(`heading /${a}/ not found`);
}
const range = async (page, dir, name, a, b, opts) => { await markRange(page, a, b); await view(page, dir, name, { from: "[data-sf]", to: "[data-st]", ...opts }); };

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
const SAFETY = { from: "#to-add-h", to: "section[aria-labelledby=risk-h]" };
const SAFETY_FIRST = { from: "#to-add-h", to: "section[aria-labelledby=risk-h] li.finding" }; // banner, medicine and the first finding

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

async function runOne(browser, theme) {
  const dir = path.join(out, theme);
  fs.mkdirSync(dir, { recursive: true });
  const tag = theme;
  const ctx = await browser.newContext({ baseURL: base, viewport: VIEW, deviceScaleFactor: 2, colorScheme: theme, reducedMotion: "reduce" });
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
    await view(page, dir, "01-sign-in");
  });
  await step("02", async () => {
    await page.goto("/login");
    await page.locator("input[name=email]").fill("new.user@example.com");
    await page.locator("input[name=password]").fill("newuser123");
    await view(page, dir, "02-sign-up");
  });
  const r = await ctx.request.post("/api/auth/login", { data: { email: cred.email, password: cred.password } });
  if (!r.ok()) throw new Error("sign-in failed " + r.status());

  await step("03", async () => { await page.goto("/"); await view(page, dir, "03-home"); });
  await step("04", async () => {
    await page.goto("/profile");
    await page.waitForSelector("section[aria-label=Allergies]");
    // conditions, allergies and current medicines; the tiles and patient information follow as -b
    await view(page, dir, "04-profile", { from: "section[aria-label='Current conditions']", to: "section[aria-label='Current medicines']" });
    await view(page, dir, "04-profile-b", { from: "h1", to: "section[aria-label='Patient information']" });
  });
  await step("05", async () => { await page.goto("/history?tab=medicines"); await view(page, dir, "05-history-medicines"); });
  await step("06", async () => {
    await page.goto("/search");
    const box = page.locator("main [role=combobox]").first();
    await box.click();
    await box.pressSequentially("ecosprin", { delay: 40 });
    await page.waitForSelector(".combo-opt");
    await sleep(800);
    await view(page, dir, "06-medicine-search", { from: "h1", to: ".combo-pop" });
  });
  await step("07", async () => {
    await page.goto(`/medicine/${ECOSPRIN.id}`);
    await page.waitForSelector("#alt-h");
    await view(page, dir, "07-medicine-page", { from: "h1", to: "section[aria-label='Medicine summary']" });
    await view(page, dir, "07-medicine-page-b", { from: "section[aria-labelledby=alt-h]" });
  });
  await step("08", async () => {
    const d = await (await ctx.request.get(`/api/medicine/${ECOSPRIN.id}`)).json();
    await page.goto(`/label/${d.ingredient_details[0].labels[0].set_id}`);
    await view(page, dir, "08-label-page", { from: "h1", to: "#main > section:first-of-type" });
  });
  await step("09", async () => {
    await page.goto(`/alternatives?id=${ECOSPRIN.id}`);
    await page.waitForSelector("#alt-h");
    await view(page, dir, "09-alternatives", { from: "#sel-h", to: "section[aria-labelledby=alt-h]" });
  });

  // safety check = Add new medicine, analysed against the demo profile (nothing is saved)
  await step("10", async () => { await addFlow(page, "abomox", "Abomox 500mg Capsule"); await openAll(page, "Why this warning"); await view(page, dir, "10-safety-critical-allergy", SAFETY); });
  await step("11", async () => {
    await addFlow(page, "ecosprin", ECOSPRIN.name);
    await openAll(page, "Why this warning");
    await view(page, dir, "11-safety-high", SAFETY_FIRST);
    await openAll(page, "Show the interaction graph");
    await page.evaluate(() => { for (const d of document.querySelectorAll("details")) if (d.querySelector(":scope > summary")?.textContent.trim().startsWith("Show the interaction graph")) d.setAttribute("data-sf", "1"); });
    await view(page, dir, "11-safety-high-b", { from: "[data-sf]" });
  });
  await step("12", async () => { await addFlow(page, "diclofenac sodium injection", "Diclofenac Sodium Injection"); await openAll(page, "Why this warning"); await view(page, dir, "12-safety-medium", SAFETY_FIRST); });
  await step("13", async () => { await addFlow(page, "cetirizine 10mg", "Cetirizine 10mg Tablet"); await view(page, dir, "13-safety-none", SAFETY); });

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
    await chosen.locator("xpath=ancestor::li[contains(@class,'finding')]").evaluate((e) => e.setAttribute("data-sf", "1"));
    await chosen.locator(".ddi-why").evaluate((e) => e.setAttribute("data-st", "1"));
    await view(page, dir, "14-ddi-classifier-ig", { from: "[data-sf]", to: "[data-st]" });
  });

  // ask box: label question with sources, then a price question
  await step("15", async () => {
    await page.goto(`/medicine/${ECOSPRIN.id}`);
    await page.waitForSelector("#ask-h");
    await sleep(15000); // stay under the model's requests-per-minute limit
    if (!(await askOnce(page, "What are the bleeding risks?"))) throw new Error("no grounded answer after 4 tries");
    await view(page, dir, "15-ask-label-grounded", { from: "section[aria-labelledby=ask-h]" });
  });
  await step("16", async () => {
    await page.goto(`/medicine/${ECOSPRIN.id}`);
    await page.waitForSelector("#ask-h");
    const card = page.locator("section[aria-labelledby=ask-h]");
    await card.locator("input[type=text]").fill("What is the cheapest alternative?");
    await card.locator("button[type=submit]").click();
    await card.locator(".alt-answer .alt-rows li").first().waitFor({ timeout: 30000 });
    await view(page, dir, "16-ask-price-cheapest-5", { from: "section[aria-labelledby=ask-h]" });
  });
  await step("17", async () => {
    await page.goto(`/medicine/${ECOSPRIN.id}`);
    await page.waitForSelector("#ls-h");
    const card = page.locator("section[aria-labelledby=ls-h]");
    await card.locator("input[type=search]").fill("bleeding risk with blood thinners");
    await card.locator("button[type=submit]").click();
    await page.waitForFunction(() => /score|similarity|cosine|passage|result/i.test(document.querySelector("section[aria-labelledby=ls-h]")?.innerText ?? ""), null, { timeout: 60000 });
    await view(page, dir, "17-label-search", { from: "section[aria-labelledby=ls-h]", to: "section[aria-labelledby=ls-h] .evidence-list > li:nth-child(2)" });
  });
  await step("18", async () => {
    await page.goto("/checker");
    await pickMedicine(page, "genericart warfarin", "Genericart Warfarin 2mg Tablet");
    await pickMedicine(page, "ecosprin", ECOSPRIN.name);
    await page.getByRole("button", { name: "Check", exact: true }).click();
    await page.waitForFunction(() => document.querySelector("section[aria-labelledby=res-h]")?.getAttribute("aria-busy") === "false", null, { timeout: 60000 });
    await openAll(page, "Why this warning");
    await view(page, dir, "18-interaction-checker", { from: "h1", to: "section[aria-labelledby=res-h]" });
  });

  // about pages: one or more views per name; extra views of a name get -b, -c (or -a2, -a3 where the name already ends in a letter)
  const about = async () => { await page.goto("/about/data"); await page.waitForSelector("#system-status-h"); await sleep(2500); };
  await step("19", async () => {
    await about();
    await range(page, dir, "19-how-it-works-a", "^How it works$", "^Medicine catalogue");
    await range(page, dir, "19-how-it-works-b", "^What the app does not do", "^Adding medicines");
    await range(page, dir, "19-how-it-works-b2", "^Adding medicines", "^DailyMed");
    await range(page, dir, "19-how-it-works-c", "^The project$", "^Baseline paper");
    await range(page, dir, "19-how-it-works-c2", "^Baseline paper", null);
  });
  await step("20", async () => {
    await about();
    await range(page, dir, "20-about-data-catalogue", "^Medicine catalogue", "^Catalogue figures");
    await range(page, dir, "20-about-data-catalogue-b", "^Catalogue figures", "^What the app does not do");
    await range(page, dir, "20-about-data-labels-rules", "^DailyMed", "^Label search");
    await range(page, dir, "20-about-data-labels-rules-b", "^Label search", "^Interaction rules");
    await range(page, dir, "20-about-data-labels-rules-c", "^Interaction rules", "^Interaction-type model");
    await range(page, dir, "20-about-data-ddi-model", "^Interaction-type model", "^DDI Extraction 2013");
    await range(page, dir, "20-about-data-ddi-model-b", "^DDI Extraction 2013", "^Real examples");
    await range(page, dir, "20-about-data-ddi-model-c", "^Real examples", "^System components");
  });
  await step("21", async () => {
    await about();
    await range(page, dir, "21-status", "^System components", "^Sample patients$");
  });
  await ctx.close();
}

const browser = await chromium.launch({ headless: true });
for (const theme of THEMES) await runOne(browser, theme);
await browser.close();
fs.writeFileSync(path.join(out, "run-report.json"), JSON.stringify({ ...report, files: report.files.map((f) => path.relative(out, f).replace(/\\/g, "/")) }, null, 1));
console.log(`\n${report.files.length} files; ${report.overflow.length} overflow notes; ${report.problems.length} problems`);
for (const x of report.overflow) console.log("OVERFLOW", x);
for (const x of report.problems) console.log("PROBLEM", x);
