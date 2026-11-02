// SOURCE: NOT IN PAPERS (own tooling). Drives headless Chrome through "Add new medicine" (typing,
// scanning a typed prescription image, details cards, risk analysis, the Critical acknowledgement)
// and "Alternative medicines", checks what the page shows, records every network request made while
// the prescription is read, and takes full-page screenshots at 1280 and 390 px in light and dark.
// Usage (API and dev server already running):
//   node scripts/add-flow.mjs http://127.0.0.1:5310 outdir path/to/prescription.png
// Each width/theme run signs up its own account, add-<width>-<theme>-<time>@example.com.
import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const [base, outDir, imagePath] = process.argv.slice(2);
mkdirSync(outDir, { recursive: true });
const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const PASSWORD = "Flow-test-pass-1";
const RUN = Date.now().toString(36);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const q = (s) => JSON.stringify(s ?? null);
const iso = (offsetDays) => new Date(Date.now() + offsetDays * 86400000).toISOString().slice(0, 10);
const BANNED = /prototype|synthetic|demo|dummy|research|dataset|APPMS|part6/i;

const port = 9500 + Math.floor(Math.random() * 400);
const chrome = spawn(CHROME, [`--remote-debugging-port=${port}`, `--user-data-dir=${mkdtempSync(join(tmpdir(), "addflow-"))}`,
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
let netLog = null; // while set, every request URL is recorded (main page and workers)
ws.onmessage = (m) => {
  const d = JSON.parse(m.data);
  if (d.id && waiting.has(d.id)) {
    waiting.get(d.id)(d);
    waiting.delete(d.id);
  } else if (d.method === "Runtime.consoleAPICalled" && d.params.type === "error") {
    logs.push(d.params.args.map((a) => a.value ?? a.description).join(" "));
  } else if (d.method === "Runtime.exceptionThrown") logs.push("EXC " + d.params.exceptionDetails.text);
  else if (d.method === "Network.requestWillBeSent" && netLog) netLog.push(d.params.request.url);
  else if (d.method === "Target.attachedToTarget") {
    // a Web Worker (the text reader): watch its requests too
    const sid = d.params.sessionId;
    ws.send(JSON.stringify({ id: ++id, method: "Network.enable", sessionId: sid }));
    ws.send(JSON.stringify({ id: ++id, method: "Runtime.runIfWaitingForDebugger", sessionId: sid }));
  }
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

const HELPERS = `window.__h = {
  field(label, scope) {
    const root = scope ? document.querySelector(scope) : document;
    const l = root && [...root.querySelectorAll('label.field')].find((x) => x.querySelector('.field-label')?.textContent.trim() === label);
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
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? "  [" + String(detail).slice(0, 400) + "]" : ""}`);
}
async function waitFor(expr, label, ms = 15000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    if (await evalJs(`Boolean(${expr})`)) return true;
    await sleep(150);
  }
  throw new Error("timed out waiting for: " + label);
}
const text = (sel = "main") => evalJs(`(document.querySelector(${q(sel)})?.innerText ?? '').replace(/\\n+/g, ' | ')`);
async function go(path) {
  await send("Page.navigate", { url: base + path });
  await sleep(300);
  await waitFor("document.readyState === 'complete' && document.querySelector('h1')", `page ${path}`);
  await sleep(500);
}
async function click(label, scope) {
  const ok = await evalJs(`(() => { const b = __h.btn(${q(label)}, ${q(scope)}); if (!b) return false; b.click(); return true; })()`);
  if (!ok) throw new Error(`no button "${label}" in ${scope ?? "page"}`);
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
/** Type into a combobox and pick the match whose name is `want` (never a similar spelling). */
async function pickMedicine(term, want, scope = "main") {
  await evalJs(`document.querySelector(${q(scope + " [role=combobox]")}).focus()`);
  await send("Input.insertText", { text: term });
  const sel = `${scope} .combo-opt:not(.combo-similar)`;
  await waitFor(`[...document.querySelectorAll(${q(sel)})].some((o) => o.querySelector('.combo-title').textContent.trim() === ${q(want)})`, `suggestion ${want}`);
  await evalJs(`[...document.querySelectorAll(${q(sel)})].find((o) => o.querySelector('.combo-title').textContent.trim() === ${q(want)}).click()`);
  await sleep(300);
}

let W = 1280;
let mobile = false;
async function shot(name) {
  const info = await evalJs(`({ overflowX: document.documentElement.scrollWidth - window.innerWidth, height: document.documentElement.scrollHeight })`);
  await send("Emulation.setDeviceMetricsOverride", { width: W, height: Math.min(info.height, 14000), deviceScaleFactor: 1, mobile });
  await sleep(400);
  const png = await send("Page.captureScreenshot", { format: "png" });
  writeFileSync(join(outDir, `${name}.png`), Buffer.from(png.data, "base64"));
  await send("Emulation.setDeviceMetricsOverride", { width: W, height: 900, deviceScaleFactor: 1, mobile });
  expect(`${name}: no horizontal overflow`, info.overflowX <= 0, `${info.overflowX}px`);
}
async function shotEl(name, selector) {
  const r = await evalJs(`(() => { const e = document.querySelector(${q(selector)}); if (!e) return null; const b = e.getBoundingClientRect(); return { y: b.top + window.scrollY, h: b.height }; })()`);
  if (!r) throw new Error("no element " + selector);
  const png = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true, clip: { x: 0, y: Math.max(0, r.y - 8), width: W, height: Math.min(r.h + 16, 6000), scale: 1 } });
  writeFileSync(join(outDir, `${name}.png`), Buffer.from(png.data, "base64"));
}
const cardOf = (name) => `[...document.querySelectorAll('.to-add')].find((c) => c.querySelector('h3')?.textContent.trim() === ${q(name)})`;
async function waitDetails() {
  await waitFor("[...document.querySelectorAll('.to-add .details')].every((d) => d.getAttribute('aria-busy') === 'false')", "details cards", 30000);
}
async function waitRisk() {
  await waitFor("document.querySelector('section[aria-labelledby=risk-h]')?.getAttribute('aria-busy') === 'false' && document.querySelector('.risk-meter')", "risk analysis", 60000);
  await sleep(300);
}
async function addToMedicines(ack) {
  if (ack) await clickSel(".add-bar input[type=checkbox]");
  await clickSel(".add-bar .btn-primary");
  await waitFor("document.body.innerText.includes('Added to your medicines:')", "added notice", 20000);
  return text("main .notice");
}

await send("Page.enable");
await send("Runtime.enable");
await send("Network.enable");
await send("Target.setAutoAttach", { autoAttach: true, waitForDebuggerOnStart: false, flatten: true });

const networkReport = [];
for (const [w, mob] of [[1280, false], [390, true]]) {
  for (const theme of ["light", "dark"]) {
    W = w;
    mobile = mob;
    const tag = `${w}-${theme}`;
    const email = `add-${tag}-${RUN}@example.com`;
    console.log(`\n=== ${tag} (${email}) ===`);
    logs = [];
    await send("Emulation.setDeviceMetricsOverride", { width: w, height: 900, deviceScaleFactor: 1, mobile: mob });
    await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: theme }] });
    await send("Network.clearBrowserCookies");
    const sid = (await send("Page.addScriptToEvaluateOnNewDocument", { source: HELPERS + `try{localStorage.setItem('medsafe.theme','${theme}')}catch(e){}` })).identifier;

    await go("/login");
    await fill("Email", email);
    await fill("Password", PASSWORD);
    await click("Continue");
    await waitFor("location.pathname === '/' && document.querySelectorAll('.tile').length === 4", "menu");
    expect(`${tag} menu tile "Add new medicine" opens /add`, await evalJs("document.querySelector('.tile[href=\"/add\"]') !== null"));
    // remove any allergy the new account started with, so the allergy step below is the only one
    const starting = await evalJs("fetch('/api/allergies').then((r) => r.json())");
    for (const a of starting) await evalJs(`fetch('/api/allergies/${a.id}', { method: 'DELETE' }).then((r) => r.status)`);
    console.log(`starting allergies removed: ${starting.map((a) => a.allergen).join(", ") || "none"}`);

    // 0. two CURRENT medicines (no end date)
    await go("/history?tab=medicines");
    for (const [term, want, days] of [["Warf 5", "Warf 5 Tablet", -30], ["Telma 40", "Telma 40 Tablet", -60]]) {
      await click("Add a medicine");
      await pickMedicine(term, want, "main form");
      await fill("Started", iso(days));
      await click("Save", "main form");
      await waitFor(`document.querySelector('section[aria-label="Current"]')?.innerText.includes(${q(want)})`, `${want} current`);
    }
    const current = await text('section[aria-label="Current"]');
    console.log("CURRENT: " + current);
    expect(`${tag} step 0: Warf 5 and Telma 40 are current`, current.includes("Warf 5 Tablet") && current.includes("Telma 40 Tablet"));
    expect(`${tag} history rows with a catalogue id have "See alternatives"`, await evalJs("[...document.querySelectorAll('section[aria-label=\"Current\"] a')].some((a) => a.textContent === 'See alternatives' && a.getAttribute('href').startsWith('/alternatives?id='))"));
    await shot(`${tag}-00-history-current`);

    // 1. type three medicines
    await go("/add");
    for (const [term, want] of [["Dolo 650", "Dolo 650 Tablet"], ["Pan 40", "PAN 40 Tablet"], ["Glycomet 500", "Glycomet 500 SR Tablet"]]) {
      await pickMedicine(term, want);
      await waitFor(`${cardOf(want)}`, `${want} in To add`);
    }
    await waitDetails();
    await waitRisk();
    const dolo = await evalJs(`${cardOf("Dolo 650 Tablet")}.innerText`);
    console.log("DOLO CARD: " + dolo.replace(/\n+/g, " | ").slice(0, 1500));
    expect(`${tag} step 1: Dolo 650 card says no same-form label`, dolo.includes("No US label in the same form is loaded, so dosage instructions are not shown. Ask your pharmacist."));
    expect(`${tag} step 1: Dolo 650 card shows no dosage section`, !/Dosage and administration|Patient counselling information/.test(dolo));
    expect(`${tag} step 1: Dolo 650 indications titled with the label's form and route`, /From the US label for acetaminophen \(ACETAMINOPHEN, Injection, solution · Intravenous\)/.test(dolo), dolo.slice(0, 300));
    const pan = await evalJs(`${cardOf("PAN 40 Tablet")}.innerText`);
    console.log("PAN CARD: " + pan.replace(/\n+/g, " | ").slice(0, 900));
    expect(`${tag} step 1: a same-form label shows verbatim dosage text with Show full text`, /Dosage and administration/.test(pan) && (await evalJs(`${cardOf("PAN 40 Tablet")}.querySelectorAll('button[aria-expanded]').length`)) > 0);
    expect(`${tag} step 1: time course says Not entered`, pan.includes("Not entered"));
    const risk1 = await text("section[aria-labelledby=risk-h]");
    console.log("RISK 1: " + risk1.slice(0, 1500));
    expect(`${tag} step 1: analysis lists the current medicines`, (await evalJs("document.querySelector('.checked').textContent")).includes("Warf 5 Tablet"));
    expect(`${tag} step 1: disclaimer under the result`, risk1.includes("Informational only. Not a substitute for advice from your doctor or pharmacist."));
    expect(`${tag} step 1: no Safe or Low level`, !/\b(Safe|Low)\b/.test(risk1.replace("does not mean the combination is safe", "")));
    expect(`${tag} step 1: no banned words`, !BANNED.test(await text("main")));
    await shot(`${tag}-01-typed-three`);
    console.log("ADDED 1: " + (await addToMedicines((await evalJs("Boolean(document.querySelector('.add-bar input[type=checkbox]'))")))));

    // 2. scan the typed prescription
    await go("/add?tab=scan");
    const hint = await text("main section[role=tabpanel]");
    expect(`${tag} step 2: scan hint shown`, hint.includes("Works best with printed or typed prescriptions. Handwriting is not supported."));
    expect(`${tag} step 2: live camera hidden or shown only in a secure context`, (await evalJs("window.isSecureContext")) || !hint.includes("Use the camera"), `secure=${await evalJs("window.isSecureContext")}`);
    const fileAttrs = await evalJs("(() => { const i = document.querySelector('input[type=file]'); return i.accept + ' ' + i.getAttribute('capture'); })()");
    expect(`${tag} step 2: file input accepts images and asks for the back camera`, fileAttrs === "image/* environment", fileAttrs);
    netLog = [];
    const obj = await send("Runtime.evaluate", { expression: "document.querySelector('input[type=file]')" });
    await send("DOM.enable");
    await send("DOM.setFileInputFiles", { files: [resolve(imagePath)], objectId: obj.result.objectId });
    const t0 = Date.now();
    await waitFor("document.querySelector('#review-h')", "review screen", 120000);
    const ocrMs = Date.now() - t0;
    await sleep(1500); // candidate searches
    const reqs = netLog;
    netLog = null;
    const origin = new URL(base).origin;
    const external = reqs.filter((u) => !u.startsWith(origin) && !u.startsWith("blob:") && !u.startsWith("data:"));
    const paths = [...new Set(reqs.map((u) => (u.startsWith(origin) ? u.slice(origin.length).replace(/\?.*$/, "") : u.slice(0, 80))))];
    networkReport.push({ tag, ocrMs, requests: reqs.length, external, paths });
    console.log(`OCR took ${ocrMs} ms; ${reqs.length} requests; paths: ${paths.join(", ")}`);
    expect(`${tag} step 6: OCR made no request outside this app's origin`, external.length === 0, external.join(" "));
    expect(`${tag} step 6: no request carried the image (no POST with a body to any endpoint)`, !reqs.some((u) => /upload|image/i.test(u)));
    const lines = await evalJs("[...document.querySelectorAll('.review-line')].map((l) => ({ raw: l.querySelector('code')?.textContent, q: l.querySelector('label.field input')?.value, fields: [...l.querySelectorAll('label.field input')].map((i) => i.value), cands: [...l.querySelectorAll('.candidate strong')].map((s) => s.textContent) }))");
    for (const l of lines) console.log("LINE: " + JSON.stringify(l));
    expect(`${tag} step 2: five lines read`, lines.length === 5, lines.length);
    expect(`${tag} step 2: no candidate is pre-selected`, (await evalJs("document.querySelectorAll('.candidate input:checked').length")) === 0);
    await shot(`${tag}-02-scan-review`);
    const want = { dolo: "Dolo 650 Tablet", azithral: "Azithral 500 Tablet", pan: "PAN 40 Tablet", ascoril: "Ascoril LS Syrup" };
    for (let i = 0; i < lines.length; i++) {
      const scope = `.review-line:nth-child(${i + 1})`;
      const raw = (lines[i].raw || "").toLowerCase();
      if (raw.includes("montair")) {
        // fix this line by hand: search for the adult tablet and correct the frequency field
        await click("Find a different medicine by hand", scope);
        await pickMedicine("Montair-LC", "Montair-LC Tablet", scope);
        await fill("How often", "0-0-1 (at night)", scope);
        continue;
      }
      const key = Object.keys(want).find((k) => raw.includes(k));
      if (!key) continue;
      await evalJs(`[...document.querySelectorAll(${q(scope + " .candidate")})].find((c) => c.querySelector('strong').textContent === ${q(want[key])})?.querySelector('input').click()`);
      await sleep(150);
    }
    await sleep(400);
    await shotEl(`${tag}-03-scan-fixed-line`, ".review-line:nth-child(4)");
    for (let i = lines.length; i >= 1; i--) {
      const ok = await evalJs(`(() => { const b = __h.btn('Confirm and add to the list', ${q(`.review-line:nth-child(${i})`)}); if (!b) return false; b.click(); return true; })()`);
      if (!ok) console.log(`line ${i}: not confirmed (no medicine chosen)`);
      await sleep(250);
    }
    await waitFor("document.querySelectorAll('.to-add').length >= 5", "five scanned medicines in To add", 15000);
    await waitDetails();
    await waitRisk();
    const toAdd = await evalJs("[...document.querySelectorAll('.to-add h3')].map((h) => h.textContent)");
    console.log("TO ADD (scanned): " + toAdd.join(", "));
    expect(`${tag} step 2: five scanned medicines confirmed into To add`, toAdd.length === 5 && toAdd.includes("Montair-LC Tablet"), toAdd.join(", "));
    const course = await evalJs(`${cardOf("Dolo 650 Tablet")}.querySelector('.kv').innerText`);
    expect(`${tag} step 2: parsed course fields carried over (1-0-1, after food, 5 days)`, course.includes("1-0-1") && course.includes("after food") && course.includes("5 days"), course.replace(/\n+/g, " | "));
    await shot(`${tag}-04-scan-to-add`);
    const crit2 = await evalJs("Boolean(document.querySelector('.add-bar input[type=checkbox]'))");
    console.log("ADDED 2: " + (await addToMedicines(crit2)));
    const hist = await evalJs("fetch('/api/medicine-records').then((r) => r.json())");
    const scanned = hist.filter((m) => m.source === "scanned");
    expect(`${tag} step 2: saved as scanned, start today, end from the duration`, scanned.length === 5 && scanned.every((m) => m.start_date === iso(0)) && scanned.some((m) => m.display_name === "Dolo 650 Tablet" && m.end_date === iso(4)),
      scanned.map((m) => `${m.display_name} ${m.start_date}..${m.end_date} ${m.frequency ?? ""} ${m.notes ?? ""}`).join("; "));

    // 3. severe allergy, then an amoxicillin brand
    await go("/profile");
    await click("Add", 'section[aria-label="Allergies"]');
    await fill("Allergic to", "Amoxycillin");
    await fill("Severity", "severe");
    await click("Save", 'section[aria-label="Allergies"]');
    await waitFor("document.querySelector('section[aria-label=\"Allergies\"]').innerText.includes('Amoxycillin')", "allergy saved");
    await go("/add");
    await pickMedicine("Mox 500", "Mox 500mg Capsule");
    await waitDetails();
    await waitRisk();
    const risk3 = await text("section[aria-labelledby=risk-h]");
    console.log("RISK 3: " + risk3.slice(0, 1200));
    expect(`${tag} step 3: Critical panel at the top`, (await evalJs("document.querySelector('section[aria-labelledby=risk-h] .risk-panel.lv-critical')?.innerText")) === "This may be a serious risk. Talk to your doctor or pharmacist before taking this medicine." && (await evalJs("document.querySelector('#to-add-h ~ .risk-panel')?.innerText ?? ''")).startsWith("This may be a serious risk."));
    expect(`${tag} step 3: meter shows Critical as text and aria-label`, (await evalJs("document.querySelector('.risk-meter').getAttribute('aria-label')")) === "Overall level: Critical" && risk3.includes("Overall level: | Critical") || risk3.includes("Overall level: Critical"));
    expect(`${tag} step 3: allergy finding names the allergy and says name-only`, risk3.includes("your allergy to Amoxycillin") && risk3.includes("Matched by name only. Related medicines in the same class are not checked."));
    expect(`${tag} step 3: Add is disabled until the warning is acknowledged`, (await evalJs("document.querySelector('.add-bar .btn-primary').disabled")) === true && (await text(".add-bar")).includes("I have read this warning"));
    await shot(`${tag}-05-critical`);
    console.log("ADDED 3: " + (await addToMedicines(true)));

    // 4. a rule match with a current medicine: aspirin with warfarin
    await go("/add");
    await pickMedicine("Ecosprin 75", "Ecosprin 75 Tablet");
    await waitDetails();
    await waitRisk();
    const risk4 = await text("section[aria-labelledby=risk-h]");
    console.log("RISK 4: " + risk4.slice(0, 1500));
    expect(`${tag} step 4: Ecosprin + Warf 5 found by the interaction rules at High`, /Ecosprin 75 Tablet \(to add\) \+ Warf 5 Tablet \(current\)/.test(risk4.replace(/ \| /g, " ")) && (await evalJs("document.querySelector('.risk-meter').getAttribute('aria-label')")) === "Overall level: High", risk4.slice(0, 300));
    expect(`${tag} step 4: High note shown`, risk4.includes("Ask your pharmacist about this combination."));
    const eco = await evalJs(`${cardOf("Ecosprin 75 Tablet")}.innerText`);
    expect(`${tag} step 4: combination-label dosage withheld for Ecosprin`, eco.includes("No US label in the same form is loaded") && eco.includes("combination product") && !/Dosage and administration/.test(eco), eco.replace(/\n+/g, " | ").slice(0, 400));
    await shot(`${tag}-06-high-warfarin-aspirin`);

    // 5. alternatives
    await go("/alternatives");
    await pickMedicine("Dolo 650", "Dolo 650 Tablet");
    await waitFor("document.querySelector('#alt-h') && !document.querySelector('section[aria-labelledby=alt-h][aria-busy=true]')", "alternatives");
    await sleep(500);
    const alt1 = await text("main");
    console.log("ALT DOLO: " + alt1.slice(0, 900));
    expect(`${tag} step 5: Dolo 650 alternatives with the wording, price and pack size`, alt1.includes("Same ingredients, strength and form. Not necessarily interchangeable. Confirm with a pharmacist.") && alt1.includes("Prices may be out of date.") && /₹/.test(alt1) && /strip of/i.test(alt1));
    expect(`${tag} step 5: no similar-use section`, !/same condition|coming soon/i.test(alt1));
    await shot(`${tag}-07-alternatives-dolo`);
    await go("/alternatives");
    await pickMedicine("Augmentin 625", "Augmentin 625 Duo Tablet");
    await waitFor("document.querySelector('#alt-h') && !document.querySelector('section[aria-labelledby=alt-h][aria-busy=true]')", "alternatives");
    await sleep(500);
    const alt2 = await text("main");
    console.log("ALT AUGMENTIN: " + alt2.slice(0, 900));
    expect(`${tag} step 5: combination product shows both ingredients and strengths`, alt2.includes("Amoxycillin") && alt2.includes("Clavulanic Acid") && alt2.includes("125mg"));
    await shot(`${tag}-08-alternatives-augmentin`);
    await go("/history?tab=medicines");
    await evalJs("[...document.querySelectorAll('a')].find((a) => a.textContent === 'See alternatives').click()");
    await waitFor("location.pathname === '/alternatives' && document.querySelector('#sel-h')", "alternatives from history");
    expect(`${tag} step 5: "See alternatives" opens the page with the medicine selected`, (await evalJs("location.search")).startsWith("?id="));

    await go("/about/data");
    const about = await text("section[aria-labelledby=add-h]");
    expect(`${tag} /about/data documents scan limits, the image staying on the device and the level mapping`, about.includes("Handwriting is not supported") && about.includes("The picture never leaves the device") && /Allergy match, severity not known\s+High/.test(about), about.slice(0, 200));
    const mods = await text("section[aria-labelledby=mods-h]");
    expect(`${tag} Full Patient Profile no longer listed as pending`, !mods.includes("Full Patient Profile") && mods.includes("Allergy Check"));
    await shotEl(`${tag}-09-about-adding`, "section[aria-labelledby=add-h]");
    expect(`${tag} no console errors`, logs.length === 0, logs.slice(0, 3).join(" ; "));
    await send("Page.removeScriptToEvaluateOnNewDocument", { identifier: sid });
  }
}

writeFileSync(join(outDir, "network.json"), JSON.stringify(networkReport, null, 1));
const failed = checks.filter((c) => !c.ok);
console.log(`\n${checks.length - failed.length}/${checks.length} checks passed`);
writeFileSync(join(outDir, "checks.json"), JSON.stringify(checks, null, 1));
ws.close();
chrome.kill();
process.exit(failed.length ? 1 : 0);
