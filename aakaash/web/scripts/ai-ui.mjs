// SOURCE: NOT IN PAPERS (own tooling). Browser check of the AI-written answers (Playwright).
// Part 1 uses the REAL server: with no LLM_API_KEY set the generated parts must be hidden and the verbatim text must stay.
// Part 2 renders the READY state with the /api/answer/* responses REPLACED BY FIXTURES made here (text starts with
// "(UI fixture)"). It proves the layout, citation chips, flags and hiding rules. It is NOT output of the language model.
// Usage: node scripts/ai-ui.mjs [baseUrl=http://localhost:4173] [shotsDir=../artifacts/screens/ai]
import fs from "node:fs";
import { PASSWORD, RUN, VIEWPORTS, THEMES, launch, newContext, suggest, waitDetails, waitRisk, pickMedicine } from "./lib/pw.mjs";

const base = process.argv[2] ?? "http://localhost:4173";
const shots = process.argv[3] ?? "../artifacts/screens/ai";
fs.mkdirSync(shots, { recursive: true });
let pass = 0;
let fail = 0;
const check = (name, ok, detail = "") => {
  ok ? pass++ : fail++;
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${!ok && detail ? "  [" + String(detail).slice(0, 300) + "]" : ""}`);
};
const READY = { status: "ready", reason: null, fix: null, provider: "gemini", model: "gemini-3.5-flash-lite", retry_after: null, ai_label: "AI-written from label text", disclaimer: "Informational only. Not a substitute for advice from your doctor or pharmacist.", requests_per_minute: 5, note: "" };
const json = (body) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body) });

const browser = await launch();
const consoleErrors = [];

for (const vp of VIEWPORTS) {
  for (const theme of THEMES) {
    const tag = `${vp.name}-${theme}`;
    const ctx = await newContext(browser, base, vp, theme);
    const page = await ctx.newPage();
    page.on("pageerror", (e) => consoleErrors.push(e.message));
    const email = `ai-${tag}-${RUN}@example.com`;
    const r = await ctx.request.post("/api/auth/login", { data: { email, password: PASSWORD } });
    if (!r.ok()) throw new Error("login " + r.status());
    for (const a of await (await ctx.request.get("/api/allergies")).json()) await ctx.request.delete(`/api/allergies/${a.id}`);
    const dolo = (await suggest(ctx, "Dolo 650")).find((m) => m.name === "Dolo 650 Tablet");
    const warf = (await suggest(ctx, "Warf 5")).find((m) => m.name === "Warf 5 Tablet");
    await ctx.request.post("/api/medicine-records", { data: { catalogue_id: warf.id, display_name: warf.name, source: "typed" } });

    // ---- Part 1: real server, no key (run once, at the first context)
    if (tag === "1280-light") {
      const st = await (await ctx.request.get("/api/answer/status")).json();
      console.log("real status:", JSON.stringify({ status: st.status, provider: st.provider, model: st.model, reason: st.reason }));
      if (st.status === "not_ready") {
        for (const [p, body] of [["ask", { medicine_id: dolo.id, question: "What is it for?" }], ["simplify", { medicine_id: dolo.id, ingredient_index: 0, section_key: "indications" }], ["explain-finding", { kind: "pair", a: "x", b: "y", level: "High" }]]) {
          const j = await (await ctx.request.post(`/api/answer/${p}`, { data: body })).json();
          check(`real ${p}: not_ready with reason and fix, no generated text`, j.status === "not_ready" && !!j.reason && !!j.fix && !j.answer && !j.simplified && !j.text, JSON.stringify(j).slice(0, 200));
        }
        await page.goto(`/medicine/${dolo.id}`);
        await page.waitForSelector("#ls-h");
        await page.waitForTimeout(600);
        check("no key: 'Ask about this medicine' card is hidden, 'Search this label' stays", (await page.locator("#ask-h").count()) === 0 && (await page.locator("#ls-h").count()) === 1);
        await page.screenshot({ path: `${shots}/nokey-medicine-${tag}.png`, fullPage: true });
        await page.goto("/add");
        await pickMedicine(page, "Ecosprin 75", "Ecosprin 75 Tablet");
        await waitDetails(page);
        await waitRisk(page);
        await page.waitForTimeout(600);
        check("no key: no AI buttons on the details card or the risk cards", (await page.getByRole("button", { name: /Explain/ }).count()) === 0);
        check("no key: verbatim label text and the risk result still shown", (await page.locator(".details .label-text").count()) > 0 && (await page.locator(".finding").count()) > 0);
        await page.screenshot({ path: `${shots}/nokey-add-${tag}.png`, fullPage: true });
      }
    }

    // ---- Part 2: ready state with fixtures
    const asked = [];
    await ctx.route("**/api/answer/status", (route) => route.fulfill(json(READY)));
    await ctx.route("**/api/answer/ask", async (route) => {
      const body = route.request().postDataJSON();
      if (/price|cost|cheap|alternativ|generic|brand|substitut/i.test(body.question)) return route.fallback(); // answered by the REAL server, no model
      asked.push(body.question);
      const real = await (await ctx.request.post("/api/search/labels", { data: { query: body.question, medicine_id: body.medicine_id, k: 5, scope: body.scope } })).json();
      const sources = real.results.filter((x) => x.text && !x.withheld).map((x) => ({ chunk_id: x.chunk_id, section_label: x.section_label, product: x.product, set_id: x.set_id, text: x.text, cited: false }));
      if (/colou?r|blue|pink/i.test(body.question) || !sources.length) {
        return route.fulfill(json({ ...READY, answer: "Not found in the retrieved label text.", not_found: true, note: null, citations: [], sources: sources.map((s) => ({ ...s, cited: false })), dropped_sentences: 0, uncited_sentences: 0 }));
      }
      const [a, b] = sources;
      a.cited = true;
      if (b) b.cited = true;
      const answer = `(UI fixture) The label passages most similar to this question are about ${a.section_label.toLowerCase()} [${a.chunk_id}].` + (b ? ` A second passage covers ${b.section_label.toLowerCase()} [${b.chunk_id}].` : "");
      return route.fulfill(json({ ...READY, answer, not_found: false, note: null, citations: b ? [a.chunk_id, b.chunk_id] : [a.chunk_id], sources, dropped_sentences: 0, uncited_sentences: 0 }));
    });
    await ctx.route("**/api/answer/simplify", async (route) => {
      const body = route.request().postDataJSON();
      const d = await (await ctx.request.get(`/api/medicine/${body.medicine_id}/details`)).json();
      const g = d.ingredients[body.ingredient_index];
      const sec = body.section_key === "indications" ? g.indications : g.instructions.find((s) => s.key === body.section_key);
      return route.fulfill(json({ ...READY, section_label: sec.label, original: sec.text, simplified: "(UI fixture) A short rewrite of this section would appear here, in plain words, keeping the same facts.", flagged: body.section_key !== "indications", unmatched: body.section_key !== "indications" ? ["99 mg"] : [] }));
    });
    const explained = [];
    await ctx.route("**/api/answer/explain-finding", (route) => {
      const body = route.request().postDataJSON();
      explained.push(body);
      return route.fulfill(json({ ...READY, level: body.level, text: "(UI fixture) These two ingredients are named together in the rule text, which says they can add to each other's effect. Talk to your doctor or pharmacist.", flagged: false, unmatched: [] }));
    });

    await page.goto(`/medicine/${dolo.id}`);
    await page.waitForSelector("#ask-h");
    check(`[${tag}] ready: Ask card shown`, (await page.locator("#ask-h").count()) === 1);
    const input = page.locator("section[aria-labelledby=ask-h] input[type=text]");
    for (const q of ["What is this medicine used for?", "What are the adverse reactions?", "Does the tablet come in a blue colour?"]) {
      await input.fill(q);
      await page.locator("section[aria-labelledby=ask-h] button[type=submit]").click();
      await page.waitForSelector("section[aria-labelledby=ask-h] .ai-box");
      const box = page.locator("section[aria-labelledby=ask-h] .ai-box");
      const txt = (await box.innerText()).replace(/\s+/g, " ");
      check(`[${tag}] answer box marked and disclaimed: ${q}`, /ai-written from label text/i.test(txt) && txt.includes("Informational only. Not a substitute for advice from your doctor or pharmacist."));
      if (/blue/.test(q)) {
        check(`[${tag}] unanswerable question shows exactly the not-found sentence`, (await box.locator(".ai-text").innerText()).trim() === "Not found in the retrieved label text.");
        await page.screenshot({ path: `${shots}/ask-notfound-${tag}.png`, fullPage: false });
      } else if (/used for/.test(q)) {
        const chips = box.locator("button.cite-chip");
        check(`[${tag}] citation chips shown`, (await chips.count()) >= 1);
        await chips.first().click();
        check(`[${tag}] chip opens the cited passage`, (await box.locator(".evidence-text").count()) >= 1 && (await chips.first().getAttribute("aria-expanded")) === "true");
        await box.scrollIntoViewIfNeeded();
        await page.screenshot({ path: `${shots}/ask-cited-${tag}.png`, fullPage: false });
      }
    }
    check(`[${tag}] three questions sent`, asked.length === 3);

    // price question: the real server answers from the catalogue, no AI label, same list as the Alternatives page
    await input.fill("Is there a cheaper alternative?");
    await page.locator("section[aria-labelledby=ask-h] button[type=submit]").click();
    await page.waitForSelector("section[aria-labelledby=ask-h] .alt-answer");
    const alt = page.locator("section[aria-labelledby=ask-h] .alt-answer");
    const altTxt = (await alt.innerText()).replace(/\s+/g, " ");
    const rows = await alt.locator(".alt-rows > li").count();
    const real = await (await ctx.request.get(`/api/medicine/${dolo.id}/alternatives`)).json();
    check(`[${tag}] price question: sentence shown, no AI label, no model call`, altTxt.includes("Same ingredients, strength and form. Not necessarily interchangeable. Confirm with a pharmacist.") && !/AI-written/i.test(altTxt) && asked.length === 3);
    check(`[${tag}] price question: at most 5 rows, same names as the Alternatives page, link to all`, rows === Math.min(5, real.same_total) && rows >= 1 && (await alt.locator(".alt-rows > li a").allInnerTexts()).join("|") === real.same.slice(0, 5).map((x) => x.name).join("|") && (await alt.getByRole("link", { name: "See all alternatives" }).getAttribute("href")) === `/alternatives?id=${dolo.id}`);
    await alt.scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${shots}/ask-alternatives-${tag}.png`, fullPage: false });

    await page.goto("/add");
    // a medicine whose label matches its form (the button is not offered on a wrong-form label)
    for (const [term, want] of [["Warf 5", "Warf 5 Tablet"], ["Telma 40", "Telma 40 Tablet"], ["Ecosprin 75", "Ecosprin 75 Tablet"], ["Dolo 650", "Dolo 650 Tablet"]]) {
      await pickMedicine(page, term, want);
      await waitDetails(page);
      await page.waitForTimeout(500);
      if ((await page.getByRole("button", { name: "Explain in simple words" }).count()) > 0) {
        console.log(`simplify tested on: ${want}`);
        break;
      }
      await page.locator(".to-add").first().getByRole("button", { name: /Remove|Close|✕|×/ }).first().click().catch(() => {});
    }
    const btn = page.getByRole("button", { name: "Explain in simple words" }).first();
    await btn.waitFor({ timeout: 10000 }).catch(() => {});
    check(`[${tag}] ready: 'Explain in simple words' button on a details section`, (await btn.count()) >= 1);
    await btn.click();
    await page.waitForSelector(".details .ai-box");
    check(`[${tag}] rewrite marked, original still on the page`, /ai-written from label text/i.test(await page.locator(".details .ai-box").first().innerText()) && (await page.locator(".details blockquote.label-text").count()) >= 2);
    await page.locator(".details .ai-box").first().scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${shots}/simplify-${tag}.png`, fullPage: false });
    const instr = page.locator(".details .detail-section", { hasText: /Dosage and administration|Patient|Instructions/ }).first();
    if (await instr.count()) {
      await instr.getByRole("button", { name: "Explain in simple words" }).click();
      await instr.locator(".ai-box").waitFor();
      check(`[${tag}] changed-number flag is shown when the check fails`, (await instr.locator(".notice-inline").count()) === 1 && /99 mg/.test(await instr.locator(".notice-inline").innerText()));
      await instr.scrollIntoViewIfNeeded();
      await page.screenshot({ path: `${shots}/simplify-flag-${tag}.png`, fullPage: false });
    }
    await page.goto("/add");
    await pickMedicine(page, "Ecosprin 75", "Ecosprin 75 Tablet");
    await waitDetails(page);
    await waitRisk(page);
    await page.getByRole("button", { name: "Explain this finding" }).first().waitFor({ timeout: 10000 }).catch(() => {});
    const f = page.locator(".finding", { has: page.getByRole("button", { name: "Explain this finding" }) }).first();
    check(`[${tag}] ready: 'Explain this finding' on a risk card`, (await f.count()) === 1);
    const before = await f.locator(".lv-badge").first().innerText();
    await f.getByRole("button", { name: "Explain this finding" }).click();
    await f.locator(".ai-box").waitFor();
    const ft = (await f.locator(".ai-box").innerText()).replace(/\s+/g, " ");
    check(`[${tag}] finding explanation ends with the doctor line, level unchanged`, ft.includes("Talk to your doctor or pharmacist") && (await f.locator(".lv-badge").first().innerText()) === before, ft);
    const sent = explained[0] ?? {};
    check(`[${tag}] request body holds only the allowed fields`, Object.keys(sent).every((k) => ["kind", "a", "b", "level", "explanation", "sentences", "predicted_class"].includes(k)), JSON.stringify(Object.keys(sent)));
    await f.scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${shots}/finding-${tag}.png`, fullPage: false });
    // a rate-limited answer hides the generated part
    await ctx.unroute("**/api/answer/explain-finding");
    await ctx.route("**/api/answer/explain-finding", (route) => route.fulfill(json({ ...READY, status: "not_ready", reason: "The AI service is rate limited. Try again in 17 seconds.", fix: "Wait and try again.", retry_after: 17, level: null, text: null, flagged: false, unmatched: [] })));
    await f.getByRole("button", { name: "Explain this finding" }).click();
    await f.getByText("Try again in 17 seconds").waitFor();
    check(`[${tag}] rate limited: message shown, no generated text, finding still there`, (await f.locator(".ai-box").count()) === 0 && (await f.locator(".finding-head").count()) === 1);
    await f.scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${shots}/ratelimited-${tag}.png`, fullPage: false });
    await ctx.close();
  }
}
await browser.close();
check("no uncaught page errors", consoleErrors.length === 0, consoleErrors.join(" | "));
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
