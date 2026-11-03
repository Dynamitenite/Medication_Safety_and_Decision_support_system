// Shared helpers for the Playwright scripts (visual-check, e2e, axe). Each run signs up its own
// throwaway account, so nothing depends on data from an earlier run.
import { chromium } from "playwright";

export const PASSWORD = "Flow-test-pass-1";
export const RUN = Date.now().toString(36);
export const iso = (offsetDays) => new Date(Date.now() + offsetDays * 86400000).toISOString().slice(0, 10);
export const VIEWPORTS = [
  { name: "1280", width: 1280, height: 900 },
  { name: "390", width: 390, height: 844 },
];
export const THEMES = ["light", "dark"];

export async function launch() {
  return chromium.launch({ headless: true });
}

/** A browser context at one width and colour scheme, with the saved theme preset. */
export async function newContext(browser, base, vp, theme) {
  const ctx = await browser.newContext({ baseURL: base, viewport: { width: vp.width, height: vp.height }, colorScheme: theme, isMobile: vp.width < 600 });
  await ctx.addInitScript((t) => { try { localStorage.setItem("medsafe.theme", t); } catch {} }, theme);
  return ctx;
}

export async function signUp(ctx, tag) {
  const email = `${tag}-${RUN}@example.com`;
  const r = await ctx.request.post("/api/auth/login", { data: { email, password: PASSWORD } });
  if (!r.ok()) throw new Error(`login failed ${r.status()}`);
  return email;
}

export async function suggest(ctx, q) {
  const r = await ctx.request.get(`/api/medicine/suggest?q=${encodeURIComponent(q)}&limit=8`);
  return (await r.json()).matches;
}

const post = async (ctx, path, data) => {
  const r = await ctx.request.post(path, { data });
  if (!r.ok()) throw new Error(`${path} ${r.status()} ${await r.text()}`);
  return r.json();
};

/** Medicine records and conditions that exercise the timelines: very short and long courses, open-ended,
 *  upcoming, every outcome, an undated row and a long name. */
export async function seedHistory(ctx) {
  const m = async (q, name) => (await suggest(ctx, q)).find((x) => x.name === name) ?? (await suggest(ctx, q))[0];
  const warf = await m("Warf 5", "Warf 5 Tablet");
  const cof = await m("Cofarin", "Cofarin 5mg Tablet");
  const telma = await m("Telma 40", "Telma 40 Tablet");
  const rec = (med, extra) => post(ctx, "/api/medicine-records", { catalogue_id: med?.id ?? null, display_name: med?.name ?? "Unknown", source: "typed", ...extra });
  await rec(warf, { start_date: iso(-30), reason: "Blood thinner" });
  await rec(telma, { start_date: iso(-60), reason: "Blood pressure" });
  await rec(cof, { start_date: iso(-420), end_date: iso(-414), outcome: "cured" });
  await rec(await m("Dolo 650", "Dolo 650 Tablet"), { start_date: iso(-20), end_date: iso(-15), outcome: "improved" });
  await rec(await m("Azithral 500", "Azithral 500 Tablet"), { start_date: iso(-200), end_date: iso(-196), outcome: "stopped" });
  await rec(await m("Pan 40", "PAN 40 Tablet"), { start_date: iso(-365), end_date: iso(-300), outcome: "not_cured" });
  await rec(await m("Glycomet 500", "Glycomet 500 SR Tablet"), { start_date: iso(5) });
  await rec(null, { display_name: "Vitamin D3 60000 IU weekly sachet (long name test)", start_date: iso(-90), end_date: iso(-40), outcome: "unknown" });
  await rec(null, { display_name: "Undated old medicine" });
  await post(ctx, "/api/conditions", { name: "Hypertension", kind: "illness", status: "current", onset_date: iso(-800), outcome: "ongoing" }).catch(() => post(ctx, "/api/conditions", { name: "Hypertension", kind: "illness", status: "current", onset_date: iso(-800) }));
  await post(ctx, "/api/conditions", { name: "Viral fever", kind: "illness", status: "past", onset_date: iso(-300), resolved_date: iso(-294), outcome: "cured" });
  await post(ctx, "/api/conditions", { name: "Knee surgery", kind: "surgery", status: "past", onset_date: iso(-150), resolved_date: iso(-149), outcome: "cured" });
  await post(ctx, "/api/allergies", { allergen: "Amoxycillin", severity: "severe" });
}

/** Type into the medicine combobox of `scope` and click the suggestion called `want`. */
export async function pickMedicine(page, term, want, scope = "main") {
  const box = page.locator(`${scope} [role=combobox]`).first();
  await box.click();
  await box.fill("");
  await box.pressSequentially(term, { delay: 20 });
  const opt = page.locator(`${scope} .combo-opt:not(.combo-similar)`).filter({ has: page.locator(".combo-title").getByText(want, { exact: true }) }).first();
  await opt.waitFor({ timeout: 15000 });
  await opt.click();
}

export async function waitRisk(page) {
  await page.waitForFunction(() => document.querySelector("section[aria-labelledby=risk-h]")?.getAttribute("aria-busy") === "false" && document.querySelector(".risk-meter"), null, { timeout: 60000 });
}
export async function waitDetails(page) {
  await page.waitForFunction(() => [...document.querySelectorAll(".to-add .details")].every((d) => d.getAttribute("aria-busy") === "false"), null, { timeout: 30000 });
}
