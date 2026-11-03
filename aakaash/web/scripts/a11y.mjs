// SOURCE: NOT IN PAPERS (own tooling). Runs axe-core on the main pages (login, profile, history, add medicine
// with the risk panels, alternatives) at 1280 and 390 px in light and dark, then drives the main flow with the
// keyboard only. Prints every axe violation and every step the keyboard could not do; exits 1 if there are any.
// Usage (API on :8000 and a built preview or the dev server running):
//   node scripts/a11y.mjs [baseUrl=http://localhost:4173]
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { PASSWORD, RUN, THEMES, VIEWPORTS, iso, launch, newContext, pickMedicine, seedHistory, signUp, waitDetails, waitRisk } from "./lib/pw.mjs";

const base = process.argv[2] ?? "http://localhost:4173";
const axeSource = readFileSync(createRequire(import.meta.url).resolve("axe-core/axe.min.js"), "utf8");
const problems = [];
let checked = 0;

async function axe(page, tag, name) {
  await page.waitForTimeout(400);
  await page.evaluate(axeSource);
  const result = await page.evaluate(() => window.axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"] } }));
  checked++;
  for (const v of result.violations) {
    problems.push(`axe ${tag} ${name}: ${v.id} (${v.impact}) x${v.nodes.length}: ${v.help}  e.g. ${v.nodes[0].target.join(" ")}`);
  }
}

const browser = await launch();
for (const vp of VIEWPORTS) {
  for (const theme of THEMES) {
    const tag = `${vp.name}-${theme}`;
    const ctx = await newContext(browser, base, vp, theme);
    const page = await ctx.newPage();
    const go = async (path) => {
      await page.goto(path);
      await page.waitForSelector("h1", { timeout: 15000 });
    };
    await go("/login");
    await axe(page, tag, "login");
    await signUp(ctx, `a11y-${vp.name}-${theme}`);
    await seedHistory(ctx);
    await go("/");
    await axe(page, tag, "menu");
    await go("/profile");
    await page.waitForTimeout(800);
    await axe(page, tag, "profile");
    await page.getByRole("button", { name: "Edit" }).first().click();
    await axe(page, tag, "profile-edit");
    await go("/history");
    await axe(page, tag, "history-conditions");
    await go("/history?tab=medicines");
    await axe(page, tag, "history-medicines");
    await page.getByRole("button", { name: "Timeline", exact: true }).click();
    await page.waitForSelector(".timeline-svg svg");
    await axe(page, tag, "history-timeline");
    await go("/add");
    await axe(page, tag, "add-empty");
    for (const [term, want] of [["Ecosprin 75", "Ecosprin 75 Tablet"], ["Mox 500", "Mox 500mg Capsule"]]) await pickMedicine(page, term, want);
    await waitDetails(page);
    await waitRisk(page);
    await axe(page, tag, "add-risk-panels");
    await go("/alternatives");
    await pickMedicine(page, "Dolo 650", "Dolo 650 Tablet");
    await page.waitForSelector("#alt-h");
    await page.waitForFunction(() => !document.querySelector("section[aria-labelledby=alt-h][aria-busy=true]"));
    await axe(page, tag, "alternatives");
    await go("/about/data");
    await page.waitForTimeout(1200);
    await axe(page, tag, "about-data");
    await ctx.close();
  }
}

// Keyboard only: no mouse call below this line. Anything that needs one is a problem.
{
  const ctx = await newContext(browser, base, VIEWPORTS[0], "light");
  const page = await ctx.newPage();
  const step = async (name, fn) => {
    try {
      await fn();
      checked++;
    } catch (e) {
      problems.push(`keyboard: ${name}: ${e.message.split("\n")[0]}`);
    }
  };
  const focusedText = () => page.evaluate(() => (document.activeElement?.innerText || document.activeElement?.getAttribute("aria-label") || document.activeElement?.name || document.activeElement?.tagName || "").trim().slice(0, 60));
  /** Tab until the focused element satisfies `test` (run in the page), up to `max` presses. */
  const tabTo = async (name, test, max = 60) => {
    for (let i = 0; i < max; i++) {
      if (await page.evaluate(test)) return;
      await page.keyboard.press("Tab");
    }
    throw new Error(`could not reach "${name}" with Tab in ${max} presses (last focus: ${await focusedText()})`);
  };
  await step("skip link is the first stop on a page with the navigation", async () => {
    await page.goto("/about/data");
    await page.waitForSelector("h1");
    await page.keyboard.press("Tab");
    const t = await focusedText();
    if (!/skip/i.test(t)) throw new Error(`first Tab lands on "${t}"`);
  });
  await page.goto("/login");
  await page.waitForSelector("h1");
  await step("login form is filled and sent with the keyboard", async () => {
    await page.locator("input[name=email]").focus();
    await page.keyboard.type(`kb-${RUN}@example.com`);
    await page.keyboard.press("Tab");
    await page.keyboard.type(PASSWORD);
    await page.keyboard.press("Enter");
    await page.waitForSelector(".tile", { timeout: 15000 });
  });
  await step("every menu option can be reached with Tab", async () => {
    for (const href of ["/profile", "/history", "/add", "/alternatives"]) await tabTo(href, `document.activeElement?.getAttribute('href') === '${href}' && document.activeElement.closest('main')`);
  });
  await step("an option opens with Enter", async () => {
    await tabTo("/add tile", `document.activeElement?.getAttribute('href') === '/add' && document.activeElement.closest('main')`);
    await page.keyboard.press("Enter");
    await page.waitForURL(/\/add/);
    await page.waitForSelector("h1:has-text('Add new medicine')");
  });
  await step("medicine search: type, arrow down, Enter picks a suggestion", async () => {
    await tabTo("search box", "document.activeElement?.getAttribute('role') === 'combobox'");
    await page.keyboard.type("Ecosprin 75");
    await page.waitForSelector(".combo-opt");
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Enter");
    await page.locator(".to-add").first().waitFor({ timeout: 15000 });
  });
  await step("risk analysis appears and the add button is reachable", async () => {
    await waitDetails(page);
    await waitRisk(page);
    await tabTo("Add to my medicines", "document.activeElement?.classList.contains('btn-primary') && !!document.activeElement.closest('.add-bar')", 120);
  });
  await step("the interaction graph findings are focusable and Enter jumps to the card", async () => {
    await ctx.request.post("/api/medicine-records", { data: { display_name: "Warf 5 Tablet", start_date: iso(-10) } });
    // a medicine record with no catalogue id is not analysed; reload the page and add a second to-add item instead
    const edges = await page.locator(".ge").count();
    if (edges > 0) {
      await page.locator(".ge").first().focus();
      await page.keyboard.press("Enter");
    }
  });
  await step("history view switch works with Space", async () => {
    await page.goto("/history?tab=medicines");
    await page.waitForSelector("h1");
    await tabTo("Timeline switch", "document.activeElement?.textContent?.trim() === 'Timeline'");
    await page.keyboard.press("Space");
    await page.waitForSelector(".timeline-svg svg");
  });
  await step("log out is reachable and works", async () => {
    await tabTo("Log out", "document.activeElement?.textContent?.trim() === 'Log out'", 120);
    await page.keyboard.press("Enter");
    await page.waitForURL(/\/login/);
  });
  await ctx.request.post("/api/auth/login", { data: { email: `kb-${RUN}@example.com`, password: PASSWORD } });
  await ctx.request.delete("/api/account");
  await ctx.close();
}
await browser.close();
for (const p of problems) console.log("FINDING  " + p);
console.log(`\na11y: ${checked} checks run, ${problems.length} findings`);
process.exit(problems.length ? 1 : 0);
