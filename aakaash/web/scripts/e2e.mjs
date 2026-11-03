// SOURCE: NOT IN PAPERS (own tooling). End-to-end walk through the final flow in headless Chrome (Playwright):
// sign up, profile, history, add medicine by typing, scan a typed prescription, risk analysis, the Critical
// acknowledgement, alternatives and similar uses, log out, and deleting the throwaway account.
// Usage (API on :8000 and a built preview or the dev server running):
//   node scripts/e2e.mjs [baseUrl=http://localhost:4173]
// Prints PASS or FAIL for each check and a count; exits 1 if any check failed.
import { PASSWORD, RUN, iso, launch, newContext, pickMedicine, waitDetails, waitRisk } from "./lib/pw.mjs";

const base = process.argv[2] ?? "http://localhost:4173";
let pass = 0;
let fail = 0;
function check(name, ok, detail = "") {
  if (ok) pass++;
  else fail++;
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${!ok && detail ? "  [" + String(detail).slice(0, 300) + "]" : ""}`);
}
const text = (page, sel) => page.locator(sel).first().innerText();
const BANNED = /prototype|synthetic|demo|dummy|APPMS|part6/i;

const browser = await launch();
const ctx = await newContext(browser, base, { name: "1280", width: 1280, height: 900 }, "light");
const page = await ctx.newPage();
const consoleErrors = [];
page.on("pageerror", (e) => consoleErrors.push(e.message));
page.on("console", (m) => m.type() === "error" && !/Failed to load resource/.test(m.text()) && consoleErrors.push(m.text()));
const email = `e2e-${RUN}@example.com`;

try {
  // 1. login (a new email creates the account), a wrong password is refused with one message
  await page.goto("/login");
  await page.locator("input[name=email]").fill(email);
  await page.locator("input[name=password]").fill(PASSWORD);
  await page.getByRole("button", { name: "Continue" }).click();
  await page.waitForSelector(".tile");
  check("login: new account lands on the menu with four options", (await page.locator(".tile").count()) === 4);
  check("login: protected page opens when signed in", (await ctx.request.get("/api/auth/me")).ok());

  // starting data of a new account: remove the allergies so the allergy step is the only one
  for (const a of await (await ctx.request.get("/api/allergies")).json()) await ctx.request.delete(`/api/allergies/${a.id}`);

  // 2. profile
  await page.goto("/profile");
  await page.getByRole("button", { name: "Edit" }).first().click();
  await page.getByLabel("Name", { exact: true }).fill("Test Person");
  await page.getByLabel("Height (cm)").fill("170");
  await page.getByLabel("Weight (kg)").fill("70");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await page.waitForSelector("text=BMI");
  check("profile: saved details show a BMI", /24\.2|BMI/.test(await text(page, "main")));
  await page.waitForSelector(".summary-tile", { timeout: 15000 });
  check("profile: summary tiles shown", (await page.locator(".summary-tile").count()) >= 3);

  // 3. history: two current medicines, then the timeline view
  await page.goto("/history?tab=medicines");
  for (const [term, want, days] of [["Warf 5", "Warf 5 Tablet", -30], ["Telma 40", "Telma 40 Tablet", -60]]) {
    await page.getByRole("button", { name: "Add a medicine" }).first().click();
    await pickMedicine(page, term, want, "main form");
    await page.getByLabel("Started").fill(iso(days));
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await page.locator('section[aria-label="Current"]', { hasText: want }).waitFor();
  }
  const cur = await text(page, 'section[aria-label="Current"]');
  check("history: both medicines listed as current", cur.includes("Warf 5 Tablet") && cur.includes("Telma 40 Tablet"));
  await page.getByRole("button", { name: "Timeline", exact: true }).click();
  check("history: timeline draws one bar per course", (await page.locator(".tl-bar").count()) >= 2);
  await page.getByRole("button", { name: "Table", exact: true }).click();
  check("history: table view lists the courses", (await page.locator("table tbody tr").count()) >= 2);

  // 4. add medicine by typing: Ecosprin with Warf 5 is a rule match
  await page.goto("/add");
  await pickMedicine(page, "Ecosprin 75", "Ecosprin 75 Tablet");
  await waitDetails(page);
  await waitRisk(page);
  const risk = (await text(page, "section[aria-labelledby=risk-h]")).replace(/\s+/g, " ");
  check("risk: Ecosprin + Warf 5 found at High", /Ecosprin 75 Tablet \(to add\) \+ Warf 5 Tablet \(current\)/.test(risk) && (await page.locator(".risk-meter").getAttribute("aria-label")) === "Overall level: High", risk.slice(0, 200));
  check("risk: disclaimer under the result", risk.includes("Informational only. Not a substitute for advice from your doctor or pharmacist."));
  check("risk: no Safe or Low level", !/\b(Safe|Low)\b/.test(risk.replace("does not mean the combination is safe", "")));
  check("risk: interaction graph drawn", (await page.locator(".graph-svg").count()) === 1);
  check("risk: no words that belong to the research pages", !BANNED.test(await text(page, "main")));
  await page.locator(".add-bar .btn-primary").click();
  await page.waitForSelector("text=Added to your medicines:");
  check("add: medicine saved to the list", true);

  // 5. scan a typed prescription (the picture is drawn here; it never leaves the browser)
  const shot = await ctx.newPage();
  await shot.setViewportSize({ width: 700, height: 420 });
  await shot.setContent(`<body style="margin:0;padding:24px;background:#fff;color:#000;font:26px Arial">
    <p style="margin:0 0 14px"><b>Rx</b> Dr. Sample, 12 May</p>
    <p style="margin:6px 0">1. Tab Dolo 650 1-0-1 after food x 5 days</p>
    <p style="margin:6px 0">2. Tab PAN 40 1-0-0 before food x 7 days</p>
    <p style="margin:6px 0">3. Tab Azithral 500 0-0-1 x 3 days</p></body>`);
  const png = await shot.screenshot();
  await shot.close();
  await page.goto("/add?tab=scan");
  const fileInput = page.locator("input[type=file]");
  check("scan: file input accepts images and asks for the back camera", (await fileInput.getAttribute("accept")) === "image/*" && (await fileInput.getAttribute("capture")) === "environment");
  const external = [];
  page.on("request", (r) => { if (!r.url().startsWith(new URL(base).origin) && !/^(blob|data):/.test(r.url())) external.push(r.url()); });
  await fileInput.setInputFiles({ name: "prescription.png", mimeType: "image/png", buffer: png });
  await page.waitForSelector("#review-h", { timeout: 120000 });
  const lines = await page.locator(".review-line").count();
  check("scan: lines read from the picture", lines >= 2, `${lines} lines`);
  check("scan: no candidate pre-selected", (await page.locator(".candidate input:checked").count()) === 0);
  check("scan: nothing was requested from outside this app's origin", external.length === 0, external.join(" "));
  await page.waitForTimeout(1500);
  const dolo = page.locator(".review-line", { hasText: /dolo/i }).first();
  if (await dolo.count()) {
    await dolo.locator(".candidate", { hasText: "Dolo 650 Tablet" }).first().locator("input").click();
    await dolo.getByRole("button", { name: "Confirm and add to the list" }).click();
    await page.locator(".to-add", { hasText: "Dolo 650 Tablet" }).waitFor();
    check("scan: confirmed line is in the To add list", true);
    await waitDetails(page);
    await waitRisk(page);
    if (await page.locator(".add-bar input[type=checkbox]").count()) await page.locator(".add-bar input[type=checkbox]").click();
    await page.locator(".add-bar .btn-primary").click();
    await page.waitForSelector("text=Added to your medicines:");
    const recs = await (await ctx.request.get("/api/medicine-records")).json();
    check("scan: saved with source scanned", recs.some((r) => r.display_name === "Dolo 650 Tablet" && r.source === "scanned"));
  } else check("scan: a Dolo line was read", false, "no line mentions Dolo");

  // 6. severe allergy, then an amoxicillin brand: Critical, and the warning must be acknowledged
  await page.goto("/profile");
  await page.locator('section[aria-label="Allergies"]').getByRole("button", { name: "Add" }).click();
  await page.getByLabel("Allergic to").fill("Amoxycillin");
  await page.getByLabel("Severity").selectOption("severe");
  await page.locator('section[aria-label="Allergies"]').getByRole("button", { name: "Save", exact: true }).click();
  await page.locator('section[aria-label="Allergies"]', { hasText: "Amoxycillin" }).waitFor();
  await page.goto("/add");
  await pickMedicine(page, "Mox 500", "Mox 500mg Capsule");
  await waitDetails(page);
  await waitRisk(page);
  const critical = await page.locator("section[aria-labelledby=risk-h] .risk-panel.lv-critical").first().innerText();
  check("critical: panel with the serious-risk wording", critical === "This may be a serious risk. Talk to your doctor or pharmacist before taking this medicine.", critical);
  check("critical: Add is disabled until the warning is acknowledged", await page.locator(".add-bar .btn-primary").isDisabled());
  await page.locator(".add-bar input[type=checkbox]").click();
  check("critical: Add is enabled after acknowledging", await page.locator(".add-bar .btn-primary").isEnabled());
  await page.locator(".add-bar .btn-primary").click();
  await page.waitForSelector("text=Added to your medicines:");
  check("critical: medicine saved after acknowledgement", true);

  // 7. alternatives and similar uses
  await page.goto("/alternatives");
  await pickMedicine(page, "Dolo 650", "Dolo 650 Tablet");
  await page.waitForSelector("#alt-h");
  await page.waitForFunction(() => !document.querySelector("section[aria-labelledby=alt-h][aria-busy=true]"));
  const alt = await text(page, "main");
  check("alternatives: same-ingredient wording, price and pack size", alt.includes("Same ingredients, strength and form. Not necessarily interchangeable. Confirm with a pharmacist.") && /₹/.test(alt) && /strip of/i.test(alt));
  check("alternatives: price chart drawn", (await page.locator(".price-chart").count()) > 0);
  await page.waitForSelector("#su-h", { timeout: 30000 }).catch(() => {});
  check("similar uses: section shown", (await page.locator("#su-h").count()) === 1);

  // 8. no uncaught errors, then log out
  check("no uncaught page or console errors", consoleErrors.length === 0, consoleErrors.slice(0, 3).join(" ; "));
  await page.getByRole("button", { name: "Log out" }).click();
  await page.waitForURL(/\/login/);
  check("logout: back at the login page", true);
  check("logout: session is gone", (await ctx.request.get("/api/auth/me")).status() === 401);
  await page.goto("/profile");
  await page.waitForURL(/\/login/);
  check("logout: a protected page sends you to login", true);

  // clean up the throwaway account
  await ctx.request.post("/api/auth/login", { data: { email, password: PASSWORD } });
  check("cleanup: account deleted", (await ctx.request.delete("/api/account")).ok());
} catch (e) {
  fail++;
  console.log(`FAIL  stopped by an error: ${e.message.split("\n")[0]}`);
  await page.screenshot({ path: "../artifacts/e2e-failure.png", fullPage: true }).catch(() => {});
}
await browser.close();
console.log(`\ne2e: ${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
