// SOURCE: NOT IN PAPERS (own tooling). Drives headless Chrome through the sign-in, profile and medical
// history journey the way a person would (typing, clicking, logging out and in), checks what the page
// shows, and takes full-page screenshots at 1280 and 390 px in light and dark.
// Usage (API and dev server already running): node scripts/flow.mjs http://localhost:5300 outdir [--delete-account]
// Each width/theme run signs up its own account, flow-<width>-<theme>@example.com.
import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const [base, outDir, ...flags] = process.argv.slice(2);
mkdirSync(outDir, { recursive: true });
const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const PASSWORD = "Flow-test-pass-1";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const q = (s) => JSON.stringify(s ?? null);
const iso = (offsetDays) => new Date(Date.now() + offsetDays * 86400000).toISOString().slice(0, 10);

const port = 9500 + Math.floor(Math.random() * 400);
const chrome = spawn(CHROME, [`--remote-debugging-port=${port}`, `--user-data-dir=${mkdtempSync(join(tmpdir(), "flow-"))}`,
  "--headless=new", "--no-first-run", "--disable-gpu", "--hide-scrollbars", "about:blank"], { stdio: "ignore" });

async function connect() {
  for (let i = 0; i < 60; i++) {
    try {
      const t = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((x) => x.type === "page");
      if (t) return t.webSocketDebuggerUrl;
    } catch {}
    await sleep(200);
  }
  throw new Error("Chrome did not start");
}
const ws = new WebSocket(await connect());
await new Promise((r) => (ws.onopen = r));
let id = 0;
const waiting = new Map();
let logs = [];
ws.onmessage = (m) => {
  const d = JSON.parse(m.data);
  if (d.id && waiting.has(d.id)) {
    waiting.get(d.id)(d);
    waiting.delete(d.id);
  } else if (d.method === "Runtime.consoleAPICalled" && d.params.type === "error") {
    logs.push(d.params.args.map((a) => a.value ?? a.description).join(" "));
  } else if (d.method === "Runtime.exceptionThrown") logs.push("EXC " + d.params.exceptionDetails.text);
};
const send = (method, params = {}) =>
  new Promise((res, rej) => {
    const i = ++id;
    waiting.set(i, (d) => (d.error ? rej(new Error(JSON.stringify(d.error))) : res(d.result)));
    ws.send(JSON.stringify({ id: i, method, params }));
  });
const evalJs = async (expr) => {
  const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
  if (r.exceptionDetails) throw new Error("page error: " + (r.exceptionDetails.exception?.description ?? r.exceptionDetails.text));
  return r.result.value;
};

// Helpers injected into every page before its own scripts run.
const HELPERS = `window.__h = {
  field(label, scope) {
    const root = scope ? document.querySelector(scope) : document;
    const l = [...root.querySelectorAll('label.field')].find((x) => x.querySelector('.field-label')?.textContent.trim() === label);
    return l && l.querySelector('input,select,textarea');
  },
  set(el, v) {
    const proto = el.tagName === 'SELECT' ? HTMLSelectElement.prototype : el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v);
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  },
  btn(text, scope) {
    const root = scope ? document.querySelector(scope) : document;
    return root && [...root.querySelectorAll('button,a')].find((b) => b.textContent.replace(/\\s+/g, ' ').trim() === text && !b.disabled);
  },
};`;

const checks = [];
function expect(name, ok, detail = "") {
  checks.push({ name, ok: Boolean(ok), detail });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? "  [" + detail + "]" : ""}`);
}
async function waitFor(expr, label, ms = 10000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    if (await evalJs(`Boolean(${expr})`)) return true;
    await sleep(150);
  }
  throw new Error("timed out waiting for: " + label);
}
const text = (sel = "main") => evalJs(`(document.querySelector(${q(sel)})?.innerText ?? '').replace(/\\n+/g, ' | ')`);
const url = () => evalJs("location.pathname + location.search");

async function go(path) {
  await send("Page.navigate", { url: base + path });
  await sleep(300);
  await waitFor("document.readyState === 'complete' && document.querySelector('h1')", `page ${path}`);
  await sleep(500); // client-side fetches
}
async function click(text, scope) {
  const ok = await evalJs(`(() => { const b = __h.btn(${q(text)}, ${q(scope)}); if (!b) return false; b.click(); return true; })()`);
  if (!ok) throw new Error(`no button "${text}" in ${scope ?? "page"}`);
  await sleep(250);
}
async function clickSel(sel) {
  const ok = await evalJs(`(() => { const b = document.querySelector(${q(sel)}); if (!b) return false; b.click(); return true; })()`);
  if (!ok) throw new Error(`nothing matches ${sel}`);
  await sleep(250);
}
async function fill(label, value, scope) {
  const r = await evalJs(`(() => { const el = __h.field(${q(label)}, ${q(scope)}); if (!el) return 'missing'; __h.set(el, ${q(value)}); return 'ok'; })()`);
  if (r !== "ok") throw new Error(`no field "${label}" in ${scope ?? "page"}`);
}
async function pickMedicine(term) {
  await evalJs("document.querySelector('[role=combobox]').focus()");
  await send("Input.insertText", { text: term });
  await waitFor("document.querySelector('.combo-opt:not(.combo-similar)')", `suggestions for ${term}`);
  const name = await evalJs("document.querySelector('.combo-opt:not(.combo-similar) .combo-title').textContent");
  await clickSel(".combo-opt:not(.combo-similar)");
  return name;
}

let W = 1280;
let mobile = false;
async function shot(name) {
  const info = await evalJs(`({ overflowX: document.documentElement.scrollWidth - window.innerWidth, height: document.documentElement.scrollHeight })`);
  await send("Emulation.setDeviceMetricsOverride", { width: W, height: Math.min(info.height, 12000), deviceScaleFactor: 1, mobile });
  await sleep(350);
  const png = await send("Page.captureScreenshot", { format: "png" });
  writeFileSync(join(outDir, `${name}.png`), Buffer.from(png.data, "base64"));
  await send("Emulation.setDeviceMetricsOverride", { width: W, height: 900, deviceScaleFactor: 1, mobile });
  if (info.overflowX > 0) console.log(`WARN  ${name}: horizontal overflow ${info.overflowX}px`);
  return info;
}
async function shotEl(name, selector) {
  const r = await evalJs(`(() => { const e = document.querySelector(${q(selector)}); if (!e) return null; const b = e.getBoundingClientRect(); return { y: b.top + window.scrollY, h: b.height }; })()`);
  if (!r) throw new Error("no element " + selector);
  const png = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true, clip: { x: 0, y: Math.max(0, r.y - 8), width: W, height: r.h + 16, scale: 1 } });
  writeFileSync(join(outDir, `${name}.png`), Buffer.from(png.data, "base64"));
}
async function openMenuIfMobile() {
  if (mobile) await clickSel('button[aria-label="Open menu"]');
}

await send("Page.enable");
await send("Runtime.enable");

for (const [w, mob] of [[1280, false], [390, true]]) {
  for (const theme of ["light", "dark"]) {
    W = w;
    mobile = mob;
    const tag = `${w}-${theme}`;
    const email = `flow-${tag}@example.com`;
    console.log(`\n=== ${tag} (${email}) ===`);
    logs = [];
    await send("Emulation.setDeviceMetricsOverride", { width: w, height: 900, deviceScaleFactor: 1, mobile: mob });
    await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: theme }] });
    await send("Network.enable");
    await send("Network.clearBrowserCookies");
    const sid = (await send("Page.addScriptToEvaluateOnNewDocument", { source: HELPERS + `try{localStorage.setItem('medsafe.theme','${theme}')}catch(e){}` })).identifier;

    // 1. signed out: protected pages go to /login
    await go("/profile");
    expect(`${tag} signed-out /profile redirects to login`, (await url()).startsWith("/login?next=%2Fprofile"), await url());
    await go("/history");
    expect(`${tag} signed-out /history redirects to login`, (await url()).startsWith("/login?next=%2Fhistory"), await url());
    await go("/login");
    const loginText = await text("main");
    expect(`${tag} login shows the neutral storage line`, loginText.includes("Your information is stored in this app's database and can be deleted from your account settings."));
    expect(`${tag} theme applied`, (await evalJs("document.documentElement.dataset.theme")) === theme, theme);
    await shot(`${tag}-01-login`);

    // 2. new email creates the account
    await fill("Email", email);
    await fill("Password", PASSWORD);
    await click("Continue");
    await waitFor("location.pathname === '/'", "menu after sign-up");
    await waitFor("document.querySelectorAll('.tile').length === 4", "four tiles");
    const tiles = await evalJs("[...document.querySelectorAll('.tile-title')].map((x) => x.textContent)");
    expect(`${tag} menu has exactly the four options`, JSON.stringify(tiles) === JSON.stringify(["My profile", "Past and current medical history", "Add new medicine", "Alternative medicines"]), tiles.join(" / "));
    await shot(`${tag}-02-menu`);
    if (!mob) {
      const nav = await evalJs("[...document.querySelectorAll('.sidebar-nav a')].map((x) => x.textContent.trim())");
      expect(`${tag} sidebar has exactly four items, no Search/Checker/Coming soon`, nav.length === 4 && !/Search|Checker|Soon/.test(nav.join()), nav.join(" / "));
    }

    // 3. pre-filled profile
    await clickSel('.tile[href="/profile"]');
    await waitFor("document.querySelector('section[aria-label=\"Patient information\"] dl')", "profile card");
    await sleep(600);
    const prefilled = await text("main");
    console.log("PROFILE (pre-filled): " + prefilled.slice(0, 700));
    expect(`${tag} profile is pre-filled with conditions or medicines`, /Current conditions \| (?!No current)/.test(prefilled) || /Current medicines \| (?!No current)/.test(prefilled));
    expect(`${tag} sample wording never shown to the user`, !/sample|synthetic|demo|dummy|APPMS|dataset|research|prototype/i.test(prefilled));
    await shot(`${tag}-03-profile-prefilled`);

    // 4. edit height and weight
    await click("Edit", 'section[aria-label="Patient information"]');
    await fill("Name", "Test Person");
    await fill("Date of birth", "1990-05-20");
    await fill("Sex", "female");
    await fill("Blood group", "O+");
    await fill("Height (cm)", "172");
    await fill("Weight (kg)", "68");
    await shot(`${tag}-04-profile-edit`);
    await click("Save", 'section[aria-label="Patient information"]');
    await waitFor("document.querySelector('section[aria-label=\"Patient information\"] dl')", "profile saved");
    await sleep(500);
    const card = await text('section[aria-label="Patient information"]');
    console.log("PROFILE CARD: " + card);
    expect(`${tag} BMI computed from height and weight (68 kg, 172 cm = 23.0)`, /BMI \| 23\.0/.test(card) || card.includes("23.0"), card);
    expect(`${tag} age computed from date of birth`, /Age \| \d+ years/.test(card), card);

    // 5. add an allergy
    await click("Add", 'section[aria-label="Allergies"]');
    await fill("Allergic to", "Penicillin test allergy");
    await fill("Severity", "severe");
    await fill("What happens, and what triggers it", "Skin rash within an hour of taking tablets");
    await click("Save", 'section[aria-label="Allergies"]');
    await waitFor("document.body.innerText.includes('Penicillin test allergy')", "allergy listed");
    const allergies = await text('section[aria-label="Allergies"]');
    console.log("ALLERGIES: " + allergies);
    expect(`${tag} allergy added with reaction and severity`, allergies.includes("Skin rash within an hour") && /Severe/i.test(allergies));
    await shot(`${tag}-05-profile-allergy`);

    // 6. history: add a past illness with an outcome
    await go("/history");
    await click("Add", 'section[aria-label="Past"]');
    await fill("Name", "Dengue fever");
    await fill("Started", iso(-200));
    await fill("Resolved", iso(-188));
    await fill("Outcome", "cured");
    await shot(`${tag}-06-history-condition-form`);
    await click("Save", "main form");
    await waitFor("document.body.innerText.includes('Dengue fever')", "condition listed");
    const pastC = await text('section[aria-label="Past"]');
    console.log("PAST CONDITIONS: " + pastC);
    expect(`${tag} past illness saved with outcome Cured`, pastC.includes("Dengue fever") && /cured/i.test(pastC) && pastC.includes("Resolved"), pastC);
    await shot(`${tag}-07-history-conditions`);

    // 7. medicines: current, past, and one deleted with confirmation
    await go("/history?tab=medicines");
    await click("Add a medicine");
    const m1 = await pickMedicine("Dolo");
    await fill("Taken for", "Fever");
    await fill("Dose", "650 mg");
    await fill("How often", "Twice daily");
    await fill("Started", iso(-9));
    await shot(`${tag}-08-medicine-form`);
    await click("Save", "main form");
    await waitFor("document.querySelector('section[aria-label=\"Current\"] .rows li')", "current medicine listed");
    await click("Add a medicine");
    const m2 = await pickMedicine("Crocin");
    await fill("Taken for", "Headache");
    await fill("Dose", "500 mg");
    await fill("How often", "As needed");
    await fill("Started", iso(-40));
    await fill("Ended", iso(-30));
    await fill("How did it go?", "improved");
    await click("Save", "main form");
    await waitFor("document.querySelector('section[aria-label=\"Past\"] .rows li')", "past medicine listed");
    await click("Add a medicine");
    await evalJs("document.querySelector('[role=combobox]').focus()");
    await send("Input.insertText", { text: "Temp typed medicine" });
    await fill("Started", iso(-3));
    await click("Save", "main form");
    await waitFor("document.body.innerText.includes('Temp typed medicine')", "typed medicine listed");
    // edit the first one: change its dose
    await clickSel(`button[aria-label="Edit ${m1.trim()}"]`);
    await fill("Dose", "500 mg");
    await click("Save", "main form");
    await sleep(700);
    // delete the throwaway with confirmation
    await clickSel('button[aria-label="Delete Temp typed medicine"]');
    await waitFor("document.querySelector('dialog[open]')", "confirm dialog");
    await shot(`${tag}-09-confirm-delete`);
    await click("Delete", "dialog");
    await waitFor("!document.body.innerText.includes('Temp typed medicine')", "typed medicine removed");
    const cur = await text('section[aria-label="Current"]');
    const past = await text('section[aria-label="Past"]');
    console.log("CURRENT MEDICINES: " + cur);
    console.log("PAST MEDICINES: " + past);
    expect(`${tag} current medicine shows why, dose, frequency, ongoing course`, cur.includes(m1.trim()) && cur.includes("For Fever") && cur.includes("500 mg") && cur.includes("Twice daily") && /ongoing, 10 days so far/.test(cur), cur);
    expect(`${tag} past medicine shows dates, duration and outcome`, past.includes(m2.trim()) && /11 days/.test(past) && /improved/i.test(past) && past.includes("For Headache"), past);
    expect(`${tag} history text has none of the banned words`, !/prototype|synthetic|demo|dummy|research|dataset|APPMS|part6/i.test(cur + past + pastC), (cur + past).slice(0, 200));
    expect(`${tag} deleted medicine is gone after confirmation`, !(cur + past).includes("Temp typed medicine"));
    await shot(`${tag}-10-history-medicines`);

    // 7b. interim pages, the public data page and the mobile drawer
    await go("/search");
    const search = await text("main");
    expect(`${tag} Add new medicine opens the search page with a link to the checker`, search.includes("Find a medicine") && search.includes("interaction checker"), search.slice(0, 160));
    expect(`${tag} search page has none of the banned words`, !/prototype|synthetic|demo|dummy|research|dataset|APPMS|part6/i.test(search));
    await shot(`${tag}-15-search`);
    await go("/alternatives");
    const alts = await text("main");
    expect(`${tag} Alternative medicines page opens`, alts.includes("Alternative medicines") && alts.includes("Find a medicine"), alts.slice(0, 160));
    await shot(`${tag}-16-alternatives`);
    await go("/about/data");
    const about = await text("main");
    expect(`${tag} data page lists the pending modules by technical name`, about.includes("Modules not built yet") && about.includes("Allergy Check") && about.includes("Focal Loss interaction model"));
    expect(`${tag} data page states the database truthfully`, about.includes("SQLite") && about.includes("argon2") && !about.includes("stores no patient data") && !about.includes("no database or login"));
    await shotEl(`${tag}-17-about-modules`, 'section[aria-labelledby="mods-h"]');
    await shotEl(`${tag}-17-about-does-not`, 'section[aria-labelledby="not-h"]');
    if (mob) {
      await go("/");
      await clickSel('button[aria-label="Open menu"]');
      await sleep(300);
      const drawer = await evalJs("[...document.querySelectorAll('.sidebar-nav a, .account-menu a, .account-menu button')].map((x) => x.textContent.trim())");
      expect(`${tag} drawer shows the four options, account settings and log out`, drawer.length === 6 && drawer.includes("Log out") && drawer.includes("Account settings"), drawer.join(" / "));
      await shot(`${tag}-18-drawer`);
    }

    // 8. account page
    await go("/account");
    await shot(`${tag}-11-account`);
    await click("Delete my data and account");
    await waitFor("document.querySelector('dialog[open]')", "delete-account dialog");
    await shot(`${tag}-12-account-delete-dialog`);
    const del = flags.includes("--delete-account") && tag === "390-dark";
    if (!del) await click("Cancel", "dialog");

    // 9. log out; protected pages redirect
    if (del) {
      await click("Delete everything", "dialog");
      await waitFor("location.pathname === '/login'", "login after account deletion");
      expect(`${tag} account deleted and signed out`, true);
    } else {
      await openMenuIfMobile();
      await click("Log out");
      await waitFor("location.pathname === '/login'", "login after log out");
      await go("/profile");
      expect(`${tag} after log out /profile redirects to login`, (await url()).startsWith("/login"), await url());
      await go("/history");
      expect(`${tag} after log out /history redirects to login`, (await url()).startsWith("/login"), await url());

      // 10. same email: wrong password, then the right one
      await go("/login");
      await fill("Email", email);
      await fill("Password", "definitely-wrong-1");
      await click("Continue");
      await waitFor("document.querySelector('[role=alert]')", "wrong password error");
      const err = await text("[role=alert]");
      expect(`${tag} wrong password shows an error and stays on login`, err.includes("Email or password is incorrect.") && (await url()).startsWith("/login"), err);
      await shot(`${tag}-13-login-wrong-password`);
      await fill("Password", PASSWORD);
      await click("Continue");
      await waitFor("location.pathname === '/' && document.querySelectorAll('.tile').length === 4", "menu after sign-in");
      await go("/profile");
      await sleep(600);
      const again = await text('section[aria-label="Patient information"]');
      expect(`${tag} same account back: edited height and name kept`, again.includes("172 cm") && again.includes("Test Person"), again);
      await shot(`${tag}-14-profile-after-relogin`);
    }
    expect(`${tag} no console errors`, logs.length === 0, logs.slice(0, 3).join(" ; "));
    await send("Page.removeScriptToEvaluateOnNewDocument", { identifier: sid });
  }
}

const failed = checks.filter((c) => !c.ok);
console.log(`\n${checks.length - failed.length}/${checks.length} checks passed`);
writeFileSync(join(outDir, "checks.json"), JSON.stringify(checks, null, 1));
ws.close();
chrome.kill();
process.exit(failed.length ? 1 : 0);
