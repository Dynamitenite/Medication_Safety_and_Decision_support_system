// SOURCE: NOT IN PAPERS (own tooling). Drives headless Chrome through the interaction-type line: the
// checker (pair opened, "Why?" opened), Add new medicine (risk analysis disclosure, "Why?") and the model
// section of /about/data, at 1280 and 390 px in light and dark. Prints what each page shows and takes screenshots.
// Usage (API and dev server already running):
//   node scripts/ddi-flow.mjs http://127.0.0.1:5321 outdir ready|notready
// "ready": the API serves a checkpoint (the smoke-test one); "notready": it has none, so no line must appear.
import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const [base, outDir, mode = "ready"] = process.argv.slice(2);
mkdirSync(outDir, { recursive: true });
const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const PASSWORD = "Flow-test-pass-1";
const RUN = Date.now().toString(36);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const q = (s) => JSON.stringify(s ?? null);
const iso = (d) => new Date(Date.now() + d * 86400000).toISOString().slice(0, 10);

const port = 9500 + Math.floor(Math.random() * 400);
const chrome = spawn(CHROME, [`--remote-debugging-port=${port}`, `--user-data-dir=${mkdtempSync(join(tmpdir(), "ddi-"))}`,
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
const HELPERS = `window.__h = {
  field(label, scope) { const root = scope ? document.querySelector(scope) : document;
    const l = root && [...root.querySelectorAll('label.field')].find((x) => x.querySelector('.field-label')?.textContent.trim() === label);
    return l && l.querySelector('input,select,textarea'); },
  set(el, v) { const proto = el.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v);
    el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); },
  btn(text, scope) { const root = scope ? document.querySelector(scope) : document;
    return root && [...root.querySelectorAll('button,a')].find((b) => b.textContent.replace(/\\s+/g, ' ').trim() === text && !b.disabled); },
};`;
const checks = [];
function expect(name, ok, detail = "") {
  checks.push({ name, ok: Boolean(ok), detail });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? "  [" + String(detail).slice(0, 500) + "]" : ""}`);
}
async function waitFor(expr, label, ms = 20000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    if (await evalJs(`Boolean(${expr})`)) return true;
    await sleep(150);
  }
  throw new Error("timed out waiting for: " + label);
}
async function go(path) {
  await send("Page.navigate", { url: base + path });
  await sleep(300);
  await waitFor("document.readyState === 'complete' && document.querySelector('h1')", `page ${path}`);
  await sleep(500);
}
async function click(label, scope) {
  const ok = await evalJs(`(() => { const b = __h.btn(${q(label)}, ${q(scope)}); if (!b) return false; b.click(); return true; })()`);
  if (!ok) throw new Error(`no button "${label}"`);
  await sleep(250);
}
async function fill(label, value, scope) {
  const r = await evalJs(`(() => { const el = __h.field(${q(label)}, ${q(scope)}); if (!el) return 'missing'; __h.set(el, ${q(value)}); return 'ok'; })()`);
  if (r !== "ok") throw new Error(`no field "${label}"`);
}
async function pickMedicine(term, want, scope = "main") {
  await evalJs(`document.querySelector(${q(scope + " [role=combobox]")}).focus()`);
  await send("Input.insertText", { text: term });
  const sel = `${scope} .combo-opt:not(.combo-similar)`;
  await waitFor(`[...document.querySelectorAll(${q(sel)})].some((o) => o.querySelector('.combo-title').textContent.trim() === ${q(want)})`, `suggestion ${want}`);
  await evalJs(`[...document.querySelectorAll(${q(sel)})].find((o) => o.querySelector('.combo-title').textContent.trim() === ${q(want)}).click()`);
  await sleep(300);
}
let W = 1280, mobile = false;
async function shot(name, selector) {
  const info = await evalJs(`({ overflowX: document.documentElement.scrollWidth - window.innerWidth, height: document.documentElement.scrollHeight })`);
  let params = { format: "png" };
  if (selector) {
    const r = await evalJs(`(() => { const e = document.querySelector(${q(selector)}); if (!e) return null; const b = e.getBoundingClientRect(); return { y: b.top + window.scrollY, h: b.height }; })()`);
    if (!r) throw new Error("no element " + selector);
    params = { format: "png", captureBeyondViewport: true, clip: { x: 0, y: Math.max(0, r.y - 8), width: W, height: Math.min(r.h + 16, 6000), scale: 1 } };
  } else await send("Emulation.setDeviceMetricsOverride", { width: W, height: Math.min(info.height, 14000), deviceScaleFactor: 1, mobile });
  await sleep(400);
  const png = await send("Page.captureScreenshot", params);
  writeFileSync(join(outDir, `${name}.png`), Buffer.from(png.data, "base64"));
  await send("Emulation.setDeviceMetricsOverride", { width: W, height: 900, deviceScaleFactor: 1, mobile });
  expect(`${name}: no horizontal overflow`, info.overflowX <= 0, `${info.overflowX}px`);
}
const T = (sel) => evalJs(`(document.querySelector(${q(sel)})?.innerText ?? '').replace(/\\s+/g, ' ')`);

await send("Page.enable");
await send("Runtime.enable");
await send("Network.enable");
const ready = mode === "ready";
for (const [w, mob] of [[1280, false], [390, true]]) {
  for (const theme of ["light", "dark"]) {
    W = w;
    mobile = mob;
    const tag = `${mode}-${w}-${theme}`;
    console.log(`\n=== ${tag} ===`);
    logs = [];
    await send("Emulation.setDeviceMetricsOverride", { width: w, height: 900, deviceScaleFactor: 1, mobile: mob });
    await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: theme }] });
    await send("Network.clearBrowserCookies").catch(() => {});
    await send("Page.addScriptToEvaluateOnNewDocument", { source: HELPERS + `try{localStorage.setItem('medsafe.theme','${theme}')}catch(e){}` });

    const email = `ddi-${tag}-${RUN}@example.com`;
    await go("/login");
    await fill("Email", email);
    await fill("Password", PASSWORD);
    await click("Continue");
    await waitFor("location.pathname === '/'", "menu");

    // 1. checker: Ecosprin (aspirin) + Brufen (ibuprofen), open the pair
    await go("/checker");
    await pickMedicine("Ecosprin 150", "Ecosprin 150 Tablet");
    await pickMedicine("Brufen 200", "Brufen 200 Tablet");
    await click("Check", "main");
    await waitFor("document.querySelector('.pair-head')", "pair card", 60000);
    const reqsBefore = await evalJs("performance.getEntriesByType('resource').filter((r) => r.name.includes('/api/ddi/classify')).length");
    expect(`${tag} checker: no classify request before a card is opened`, reqsBefore === 0, reqsBefore);
    const sev = await T(".pair-head .badge-sev");
    await evalJs("document.querySelector('.pair-head').click()");
    await sleep(300);
    await waitFor("document.querySelector('.pair-head').getAttribute('aria-expanded') === 'true' && !document.querySelector('.pair-body').hidden", "pair card open");
    expect(`${tag} checker: pair card is open`, true);
    if (ready) {
      await waitFor("document.querySelector('.pair-body .ddi-type')", "interaction type line", 60000);
      const line = await T(".pair-body .ddi-type-line");
      console.log("LINE: " + line);
      expect(`${tag} checker: line shows class, percent and Model estimate`, /interaction type: .+ · \d+%/i.test(line) && /model estimate/i.test(line), line);
      expect(`${tag} checker: smoke-test model is labelled`, /smoke-test model, not for reporting/i.test(line), line);
      const n = await evalJs("document.querySelectorAll('.pair-body .ddi-type').length");
      const reqs = await evalJs("performance.getEntriesByType('resource').filter((r) => r.name.includes('/api/ddi/classify')).length");
      expect(`${tag} checker: one request per markable sentence, none for the others`, reqs === n, `${reqs} requests, ${n} lines`);
      await shot(`${tag}-1-checker-line`, ".pair");
      await evalJs("document.querySelector('.pair-body .ddi-why summary').click()");
      await waitFor("document.querySelector('.pair-body .attr-sentence')", "why view", 60000);
      const legend = await T(".pair-body .ddi-why");
      console.log("WHY: " + legend.slice(0, 500));
      expect(`${tag} checker: Why? shows highlighted sentence and the method`, legend.includes("Integrated Gradients") && (await evalJs("document.querySelectorAll('.pair-body .attr').length")) > 3);
      await shot(`${tag}-2-checker-why`, ".pair");
    } else {
      await sleep(2500);
      const has = await evalJs("document.querySelectorAll('.ddi-type, .ddi-disclosure, .ddi-why').length");
      const bodyText = await T("main");
      expect(`${tag} checker: model not ready shows nothing`, has === 0 && !/model estimate|interaction type/i.test(bodyText), has);
      expect(`${tag} checker: no classify request when not ready`, (await evalJs("performance.getEntriesByType('resource').filter((r) => r.name.includes('/api/ddi/classify')).length")) === 0);
      await shot(`${tag}-1-checker`, ".pair");
    }
    console.log("PAIR SEVERITY: " + sev);

    // 2. add new medicine: current Ecosprin (via the API), add Brufen, open the disclosure
    const posted = await evalJs(`fetch('/api/medicine-records', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ catalogue_id: '72318', display_name: 'Ecosprin 150 Tablet', start_date: ${q(iso(-20))} }) }).then((r) => r.status)`);
    expect(`${tag} add: current medicine saved`, posted === 201, posted);
    await go("/add");
    await pickMedicine("Brufen 200", "Brufen 200 Tablet");
    await waitFor("document.querySelector('section[aria-labelledby=risk-h]')?.getAttribute('aria-busy') === 'false' && document.querySelector('.risk-meter')", "risk analysis", 60000);
    await sleep(500);
    const levelBefore = await T("section[aria-labelledby=risk-h] .finding .lv-badge");
    const disc = await evalJs("document.querySelectorAll('section[aria-labelledby=risk-h] .ddi-disclosure').length");
    if (ready) {
      expect(`${tag} add: a closed disclosure sits under each markable sentence`, disc > 0 && (await evalJs("document.querySelectorAll('section[aria-labelledby=risk-h] .ddi-disclosure[open]').length")) === 0, disc);
      expect(`${tag} add: nothing classified before opening`, (await evalJs("performance.getEntriesByType('resource').filter((r) => r.name.includes('/api/ddi/classify')).length")) === 0);
      await evalJs("document.querySelector('section[aria-labelledby=risk-h] .ddi-disclosure summary').click()");
      await waitFor("document.querySelector('section[aria-labelledby=risk-h] .ddi-type')", "disclosure result", 60000);
      const one = await evalJs("performance.getEntriesByType('resource').filter((r) => r.name.includes('/api/ddi/classify')).length");
      expect(`${tag} add: opening one disclosure classifies only that sentence`, one === 1, one);
      console.log("ADD LINE: " + (await T("section[aria-labelledby=risk-h] .ddi-disclosure")));
      await evalJs("document.querySelector('section[aria-labelledby=risk-h] .ddi-why summary').click()");
      await waitFor("document.querySelector('section[aria-labelledby=risk-h] .attr-sentence')", "why in add", 60000);
      const levelAfter = await T("section[aria-labelledby=risk-h] .finding .lv-badge");
      expect(`${tag} add: risk level unchanged by the model (${levelBefore})`, levelBefore === levelAfter && levelBefore.length > 0, `${levelBefore} -> ${levelAfter}`);
      await shot(`${tag}-3-add-why`, "section[aria-labelledby=risk-h]");
    } else {
      expect(`${tag} add: model not ready shows no disclosure`, disc === 0 && !/model estimate|interaction type/i.test(await T("main")), disc);
      await shot(`${tag}-3-add`, "section[aria-labelledby=risk-h]");
    }

    // 3. about/data
    await go("/about/data");
    await waitFor("document.querySelector('#clf-h')", "model section");
    await sleep(2500);
    const sec = await T("section[aria-labelledby=clf-h]");
    console.log("ABOUT: " + sec.slice(0, 700));
    if (ready) expect(`${tag} about: smoke-test results are flagged`, /smoke-test result, not for reporting/i.test(sec));
    else expect(`${tag} about: not_ready text shown, no numbers`, /no measured results yet/i.test(sec) && !/\d+\.\d/.test(sec.replace(/1701\.08303/,"")) && !/smoke/i.test(sec));
    expect(`${tag} about: class definitions labelled as a paraphrase`, sec.includes("paraphrase from arXiv 1701.08303, not the official annotation guideline text"));
    expect(`${tag} about: no Jia F1 quoted`, !sec.includes("83.57"));
    await shot(`${tag}-4-about-data`, "section[aria-labelledby=clf-h]");
    expect(`${tag} console clean`, logs.length === 0, logs.join(" | "));
  }
}
writeFileSync(join(outDir, `checks-${mode}.json`), JSON.stringify(checks, null, 1));
console.log(`\n${checks.filter((c) => c.ok).length}/${checks.length} checks passed`);
ws.close();
chrome.kill();
process.exit(checks.every((c) => c.ok) ? 0 : 1);
