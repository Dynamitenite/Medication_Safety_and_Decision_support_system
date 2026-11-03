// SOURCE: NOT IN PAPERS (own tooling). Drives headless Chrome through "Search this label" on the medicine
// page and "Medicines with similar uses" on Alternative medicines, the way a person would (typing, clicking),
// prints what the page shows, and takes full-page screenshots at 1280 and 390 px in light and dark.
// Usage (API and dev server running): node scripts/search-flow.mjs http://127.0.0.1:5173 outdir
//   [search:<name>=<id>:<query> ...] [similar:<name>=<id> ...]
import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const [base, outDir, ...cases] = process.argv.slice(2);
mkdirSync(outDir, { recursive: true });
const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const port = 9500 + Math.floor(Math.random() * 400);
const chrome = spawn(CHROME, [`--remote-debugging-port=${port}`, `--user-data-dir=${mkdtempSync(join(tmpdir(), "sflow-"))}`,
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
const logs = [];
ws.onmessage = (m) => {
  const d = JSON.parse(m.data);
  if (d.id && waiting.has(d.id)) { waiting.get(d.id)(d); waiting.delete(d.id); }
  else if (d.method === "Runtime.consoleAPICalled" && ["error", "warning"].includes(d.params.type)) logs.push(d.params.args.map((a) => a.value ?? a.description).join(" "));
  else if (d.method === "Runtime.exceptionThrown") logs.push("EXC " + d.params.exceptionDetails.text);
};
const send = (method, params = {}) => new Promise((res, rej) => {
  const i = ++id;
  waiting.set(i, (d) => (d.error ? rej(new Error(JSON.stringify(d.error))) : res(d.result)));
  ws.send(JSON.stringify({ id: i, method, params }));
});
const ev = async (expr) => (await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true })).result.value;
await send("Page.enable");
await send("Runtime.enable");

const TYPE = (text) => `(() => { const i = document.querySelector('form[role=search] input'); if (!i) return false;
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(i, ${JSON.stringify(text)});
  i.dispatchEvent(new Event('input', { bubbles: true })); return true; })()`;
const CLICK = `(() => { const b = document.querySelector('form[role=search] button[type=submit]'); if (!b) return false; b.click(); return true; })()`;
const summary = {};
for (const spec of cases) {
  const [kind, rest] = spec.split(/:(.*)/s);
  const [name, tail] = rest.split("=");
  const [mid, ...qq] = tail.split(":");
  const query = qq.join(":");
  for (const [w, h, mobile] of [[1280, 900, false], [390, 844, true]]) {
    for (const theme of ["light", "dark"]) {
      logs.length = 0;
      await send("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: 1, mobile });
      await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: theme }] });
      await send("Page.navigate", { url: base + "/" });
      await sleep(500);
      await ev(`localStorage.setItem("medsafe.theme", "${theme}")`);
      // sign in through the API (an email with no account gets one), so the protected pages open
      await ev(`fetch("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: "searchflow@example.com", password: "Search-flow-pass-1" }) }).then(r => r.status)`);
      await send("Page.navigate", { url: base + (kind === "search" ? `/medicine/${mid}` : kind === "about" ? "/about/data" : `/alternatives?id=${mid}`) });
      let info;
      if (kind === "search") {
        await sleep(3500);
        const typed = await ev(TYPE(query));
        await sleep(200);
        const clicked = await ev(CLICK);
        await sleep(2500);
        info = await ev(`(() => { const sec = document.querySelector('#ls-h')?.closest('section'); return {
          typed: ${typed}, clicked: ${clicked},
          summary: sec?.querySelector('p.small.muted:not(:first-of-type)')?.innerText,
          cards: [...(sec?.querySelectorAll('.evidence') ?? [])].map(c => ({
            section: c.querySelector('.sticker')?.innerText, score: c.querySelector('.evidence-score')?.innerText,
            meta: c.querySelector('p.small.muted')?.innerText, marks: [...c.querySelectorAll('mark')].map(m => m.innerText).slice(0, 8),
            notShown: c.innerText.includes('Text not shown'), check: c.innerText.includes('Check form'),
            text: c.querySelector('.evidence-text')?.innerText.slice(0, 110) })),
          overflowX: document.documentElement.scrollWidth - window.innerWidth, height: document.documentElement.scrollHeight }; })()`);
        // scroll the search card to the top so the screenshot shows it
      } else if (kind === "about") {
        await sleep(5000);
        info = await ev(`(() => { const sec = document.querySelector('#ret-h')?.closest('section'); return {
          present: !!sec, h3: [...(sec?.querySelectorAll('h3') ?? [])].map(h => h.innerText), text: sec?.innerText.slice(0, 400),
          mentionsNotBuilt: sec?.innerText.includes('not built'), flagText: sec?.innerText.includes('Generic wording'),
          overflowX: document.documentElement.scrollWidth - window.innerWidth, height: document.documentElement.scrollHeight }; })()`);
      } else {
        await sleep(6500);
        info = await ev(`(() => { const sec = document.querySelector('#su-h')?.closest('section'); return {
          present: !!sec, heading: sec?.querySelector('h2')?.innerText, note: sec?.querySelector('p.small')?.innerText,
          groups: [...(sec?.querySelectorAll('.similar-group') ?? [])].map(g => ({ g: g.querySelector('h3')?.innerText,
            items: [...g.querySelectorAll('.similar-item')].map(i => ({ ing: i.querySelector('h4')?.innerText, sim: i.querySelector('.evidence-score')?.innerText,
              quote: i.querySelector('blockquote')?.innerText.slice(0, 120), brands: [...i.querySelectorAll('tbody th a')].map(a => a.innerText).slice(0, 3) })).slice(0, 6) })),
          overflowX: document.documentElement.scrollWidth - window.innerWidth, height: document.documentElement.scrollHeight }; })()`);
      }
      const top = await ev(`(() => { const t = document.querySelector(${kind === "search" ? "'#ls-h'" : kind === "about" ? "'#ret-h'" : "'#su-h'"}); const y = t ? t.getBoundingClientRect().top + scrollY - 12 : 0; return y; })()`);
      const full = Math.min(info.height, 6000);
      await send("Emulation.setDeviceMetricsOverride", { width: w, height: full, deviceScaleFactor: 1, mobile });
      await sleep(300);
      const shot = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true, clip: { x: 0, y: Math.max(0, Math.min(top, info.height - 200)), width: w, height: Math.min(full, kind === "about" ? 3200 : 2600), scale: 1 } });
      const file = join(outDir, `${kind}-${name}-${w}-${theme}.png`);
      writeFileSync(file, Buffer.from(shot.data, "base64"));
      summary[`${kind}-${name}-${w}-${theme}`] = { ...info, console: [...logs], file };
    }
  }
}
writeFileSync(join(outDir, "log.json"), JSON.stringify(summary, null, 1));
for (const [k, v] of Object.entries(summary)) {
  if (!k.endsWith("-1280-light") && !v.console.length && !v.overflowX) continue;
  console.log(k, JSON.stringify(v, null, 1));
}
console.log("overflow / console summary:", JSON.stringify(Object.fromEntries(Object.entries(summary).map(([k, v]) => [k, { overflowX: v.overflowX, console: v.console }]))));
ws.close();
chrome.kill();
process.exit(0);
