// SOURCE: NOT IN PAPERS (own tooling). Browser check of the price/alternatives answer in "Ask about this medicine".
// Uses the REAL server: the answer comes from the catalogue, so no key and no fixture is needed for it. Only
// /api/answer/status is replaced so that the Ask card is shown.
// Usage: node scripts/ask-price.mjs [baseUrl=http://localhost:4173] [shotsDir=../artifacts/screens/ask-price]
import fs from "node:fs";
import { createRequire } from "node:module";
import { PASSWORD, RUN, VIEWPORTS, THEMES, launch, newContext, suggest } from "./lib/pw.mjs";

const axeSource = fs.readFileSync(createRequire(import.meta.url).resolve("axe-core/axe.min.js"), "utf8");
const base = process.argv[2] ?? "http://localhost:4173";
const shots = process.argv[3] ?? "../artifacts/screens/ask-price";
fs.mkdirSync(shots, { recursive: true });
let fail = 0;
const check = (name, ok, detail = "") => {
  if (!ok) fail++;
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${!ok && detail ? "  [" + String(detail).slice(0, 300) + "]" : ""}`);
};
const READY = { status: "ready", reason: null, fix: null, provider: "gemini", model: "gemini-3.5-flash-lite", retry_after: null, ai_label: "AI-written from label text", disclaimer: "", requests_per_minute: 5, note: "" };

const browser = await launch();
for (const vp of VIEWPORTS) {
  for (const theme of THEMES) {
    const tag = `${vp.name}-${theme}`;
    const ctx = await newContext(browser, base, vp, theme);
    const page = await ctx.newPage();
    const r = await ctx.request.post("/api/auth/login", { data: { email: `ask-price-${tag}-${RUN}@example.com`, password: PASSWORD } });
    if (!r.ok()) throw new Error("login " + r.status());
    const dolo = (await suggest(ctx, "Dolo 650")).find((m) => m.name === "Dolo 650 Tablet");
    let modelCalls = 0;
    await ctx.route("**/api/answer/status", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(READY) }));
    await ctx.route("**/api/answer/ask", (route) => {
      const q = route.request().postDataJSON().question;
      if (!/price|cost|cheap|alternativ|generic|brand|substitut/i.test(q)) { modelCalls++; return route.fulfill({ status: 500, body: "{}" }); }
      return route.fallback();
    });
    await page.goto(`/medicine/${dolo.id}`);
    await page.waitForSelector("#ask-h");
    await page.locator("section[aria-labelledby=ask-h] input[type=text]").fill("Is there a cheaper alternative?");
    await page.locator("section[aria-labelledby=ask-h] button[type=submit]").click();
    const alt = page.locator("section[aria-labelledby=ask-h] .alt-answer");
    await alt.waitFor();
    const txt = (await alt.innerText()).replace(/\s+/g, " ");
    const real = await (await ctx.request.get(`/api/medicine/${dolo.id}/alternatives`)).json();
    const names = await alt.locator(".alt-rows > li a").allInnerTexts();
    check(`[${tag}] sentence shown, no AI label`, txt.includes("Same ingredients, strength and form. Not necessarily interchangeable. Confirm with a pharmacist.") && !/AI-written/i.test(txt), txt);
    check(`[${tag}] at most 5 rows, same as the Alternatives page`, names.length >= 1 && names.length <= 5 && names.join("|") === real.same.slice(0, 5).map((x) => x.name).join("|"), names.join("|"));
    check(`[${tag}] link to all alternatives`, (await alt.getByRole("link", { name: "See all alternatives" }).getAttribute("href")) === `/alternatives?id=${dolo.id}`);
    check(`[${tag}] no horizontal overflow`, await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.evaluate(axeSource);
    const axe = await page.evaluate(() => axe.run("section[aria-labelledby=ask-h]", { runOnly: ["wcag2a", "wcag2aa", "wcag21aa"] }));
    check(`[${tag}] axe: no violations in the Ask card`, axe.violations.length === 0, axe.violations.map((v) => v.id + ": " + v.help).join("; "));
    await alt.scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${shots}/ask-price-${tag}.png` });
    await ctx.close();
  }
}
await browser.close();
process.exit(fail ? 1 : 0);
