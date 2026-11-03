// SOURCE: NOT IN PAPERS (own tooling). Opens every page that has charts or forms at 1280 and 390 px in
// light and dark and fails on: horizontal overflow, text set in Arial or Times (browser defaults),
// form controls that kept the browser's own look, and SVG text that is clipped by its card or the screen.
// Screenshots go to aakaash/artifacts/screens/ (gitignored).
// Usage (API on :8000 and a built preview or the dev server running):
//   node scripts/visual-check.mjs [baseUrl=http://127.0.0.1:4173] [outDir=../artifacts/screens]
import { mkdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { THEMES, VIEWPORTS, launch, newContext, pickMedicine, seedHistory, signUp, suggest, waitDetails, waitRisk } from "./lib/pw.mjs";

const base = process.argv[2] ?? "http://127.0.0.1:4173";
const outDir = resolve(process.argv[3] ?? "../artifacts/screens");
mkdirSync(outDir, { recursive: true });

let pass = 0;
const failures = [];
function check(name, ok, detail = "") {
  if (ok) pass++;
  else failures.push(`${name}${detail ? "  [" + String(detail).slice(0, 300) + "]" : ""}`);
}

/** Runs in the page. Returns problems found in what is currently visible. */
function audit() {
  const out = { overflow: document.documentElement.scrollWidth - window.innerWidth, fonts: [], defaults: [], clipped: [] };
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none";
  };
  const first = (ff) => ff.split(",")[0].replace(/["']/g, "").trim().toLowerCase();
  const BAD = /^(arial|times|times new roman|helvetica|system-ui|sans-serif|serif|monospace|courier new)$/;
  const describe = (el) => `${el.tagName.toLowerCase()}${el.className && typeof el.className === "string" ? "." + el.className.trim().split(/\s+/)[0] : ""} "${(el.textContent || el.value || "").trim().slice(0, 30)}"`;
  for (const el of document.querySelectorAll("body *")) {
    if (!visible(el) || (el.closest("svg") && el.tagName.toLowerCase() !== "text")) continue;
    const own = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    const control = /^(button|input|select|textarea)$/i.test(el.tagName);
    if (!own && !control) continue;
    const s = getComputedStyle(el);
    if (BAD.test(first(s.fontFamily))) out.fonts.push(`${describe(el)} -> ${s.fontFamily.slice(0, 40)}`);
    if (control && !["checkbox", "radio", "file", "hidden"].includes(el.type)) {
      if (s.borderTopStyle === "outset" || s.borderTopStyle === "inset") out.defaults.push(`${describe(el)} border ${s.borderTopStyle}`);
      if (el.tagName === "BUTTON" && /^rgb\((239, 239, 239|233, 233, 237)\)$/.test(s.backgroundColor)) out.defaults.push(`${describe(el)} bg ${s.backgroundColor}`);
    }
  }
  for (const el of document.querySelectorAll("table, details, summary")) {
    if (visible(el) && BAD.test(first(getComputedStyle(el).fontFamily))) out.fonts.push(`${describe(el)} -> ${getComputedStyle(el).fontFamily.slice(0, 40)}`);
  }
  for (const t of document.querySelectorAll("svg text")) {
    if (!t.textContent.trim()) continue;
    const r = t.getBoundingClientRect();
    if (r.width === 0) continue;
    const svg = t.closest("svg");
    const card = t.closest(".chart-frame, .card, .timeline-svg, .graph-wrap") ?? document.body;
    const c = card.getBoundingClientRect();
    const scroller = t.closest(".timeline-svg");
    const scrolls = scroller && scroller.scrollWidth > scroller.clientWidth + 1;
    const sv = svg.getBoundingClientRect();
    const slack = 1;
    if (r.left < Math.max(c.left, 0) - slack || r.right > Math.min(c.right, window.innerWidth) + slack || r.left < sv.left - slack || r.right > sv.right + slack || scrolls) {
      out.clipped.push(`"${t.textContent.trim().slice(0, 30)}" ${Math.round(r.left)}..${Math.round(r.right)} in ${Math.round(c.left)}..${Math.round(c.right)}${scrolls ? " (scrolls)" : ""}`);
    }
    const vbw = svg.viewBox.baseVal && svg.viewBox.baseVal.width ? svg.viewBox.baseVal.width : sv.width;
    const px = parseFloat(getComputedStyle(t).fontSize) * (sv.width / vbw);
    if (px < 10.5) out.clipped.push(`"${t.textContent.trim().slice(0, 30)}" renders at ${px.toFixed(1)}px`);
  }
  // a chart whose plot area collapsed (axis labels took the whole width) draws no bars
  for (const w of document.querySelectorAll(".recharts-wrapper")) {
    if (visible(w) && !w.querySelector(".recharts-bar-rectangle")) out.clipped.push("chart draws no bars");
  }
  // text drawn over other text inside one chart
  for (const svg of document.querySelectorAll("svg")) {
    const texts = [...svg.querySelectorAll("text")].filter((t) => t.textContent.trim() && t.getBoundingClientRect().width > 0);
    const boxes = texts.map((t) => ({ t, r: t.getBoundingClientRect() }));
    for (let i = 0; i < boxes.length; i++) {
      for (let j = i + 1; j < boxes.length; j++) {
        const a = boxes[i].r;
        const b = boxes[j].r;
        if (boxes[i].t.contains(boxes[j].t) || boxes[j].t.contains(boxes[i].t)) continue;
        const w = Math.min(a.right, b.right) - Math.max(a.left, b.left);
        const h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
        if (w > 1 && h > 3) out.clipped.push(`"${boxes[i].t.textContent.trim().slice(0, 20)}" overlaps "${boxes[j].t.textContent.trim().slice(0, 20)}"`);
      }
    }
  }
  return out;
}

async function inspect(page, tag, name) {
  await page.waitForTimeout(500);
  const r = await page.evaluate(audit);
  await page.screenshot({ path: join(outDir, `${tag}-${name}.png`), fullPage: true });
  check(`${tag} ${name}: no horizontal overflow`, r.overflow <= 0, `${r.overflow}px`);
  check(`${tag} ${name}: no Arial/Times/default fonts`, r.fonts.length === 0, r.fonts.slice(0, 4).join("; "));
  check(`${tag} ${name}: no browser-default controls`, r.defaults.length === 0, r.defaults.slice(0, 4).join("; "));
  check(`${tag} ${name}: no clipped or tiny SVG text`, r.clipped.length === 0, r.clipped.slice(0, 4).join("; "));
}

const browser = await launch();
const errors = [];
for (const vp of VIEWPORTS) {
  for (const theme of THEMES) {
    const tag = `${vp.name}-${theme}`;
    console.log(`== ${tag}`);
    const ctx = await newContext(browser, base, vp, theme);
    const page = await ctx.newPage();
    page.on("pageerror", (e) => errors.push(`${tag} ${e.message}`));
    const go = async (path, ready = "h1") => {
      await page.goto(path);
      await page.waitForSelector(ready, { timeout: 15000 });
    };
    await go("/login");
    await inspect(page, tag, "login");
    await signUp(ctx, `vis-${vp.name}-${theme}`);
    await seedHistory(ctx);
    await go("/");
    await inspect(page, tag, "menu");
    await go("/profile");
    await page.waitForTimeout(800);
    await inspect(page, tag, "profile");
    for (const tab of ["conditions", "medicines"]) {
      await go(tab === "conditions" ? "/history" : "/history?tab=medicines");
      await inspect(page, tag, `history-${tab}-list`);
      await page.getByRole("button", { name: "Timeline", exact: true }).click();
      await page.waitForSelector(".timeline-svg svg");
      await inspect(page, tag, `history-${tab}-timeline`);
      await page.getByRole("button", { name: "Table", exact: true }).click();
      await inspect(page, tag, `history-${tab}-table`);
    }
    // add medicine: typed medicines make a graph with pair and allergy edges
    await go("/add");
    for (const [term, want] of [["Ecosprin 75", "Ecosprin 75 Tablet"], ["Mox 500", "Mox 500mg Capsule"], ["Dolo 650", "Dolo 650 Tablet"]]) await pickMedicine(page, term, want);
    await waitDetails(page);
    await waitRisk(page);
    await inspect(page, tag, "add-risk");
    const graph = page.locator(".chart-frame", { hasText: "Interaction graph" }).first();
    check(`${tag} add: interaction graph drawn`, (await graph.count()) > 0);
    if (await graph.count()) {
      await graph.screenshot({ path: join(outDir, `${tag}-graph.png`) });
      await graph.getByRole("button", { name: "Table", exact: true }).click();
      await inspect(page, tag, "add-graph-table");
    }
    await go("/alternatives");
    await pickMedicine(page, "Dolo 650", "Dolo 650 Tablet");
    await page.waitForSelector("#alt-h");
    await page.waitForFunction(() => !document.querySelector("section[aria-labelledby=alt-h][aria-busy=true]"));
    await inspect(page, tag, "alternatives");
    await go("/about/data");
    await page.waitForTimeout(1500);
    await inspect(page, tag, "about-data");
    await go("/about/trace");
    await inspect(page, tag, "about-trace");
    await go("/account");
    await inspect(page, tag, "account");
    // the pages reached from search results and links
    const dolo = (await suggest(ctx, "Dolo 650")).find((m) => m.name === "Dolo 650 Tablet");
    const setId = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/.exec(await (await ctx.request.get(`/api/medicine/${dolo.id}`)).text())?.[0];
    for (const [name, path] of [["search", "/search"], ["checker", "/checker"], ["medicine", `/medicine/${dolo.id}`], ["label", `/label/${setId}`], ["module", "/modules/allergy_check"], ["not-found", "/no-such-page"]]) {
      await go(path);
      await page.waitForTimeout(1200);
      await inspect(page, tag, name);
    }
    await ctx.close();
  }
}
await browser.close();
check("no uncaught page errors", errors.length === 0, errors.slice(0, 3).join(" ; "));
for (const f of failures) console.log("FAIL  " + f);
console.log(`\nvisual-check: ${pass} passed, ${failures.length} failed. Screenshots in ${outDir}`);
process.exit(failures.length ? 1 : 0);
