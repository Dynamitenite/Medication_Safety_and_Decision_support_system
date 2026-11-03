// SOURCE: NOT IN PAPERS (own tooling). Drives headless Chrome over the DevTools protocol to take
// full-page screenshots at 1280 and 390 px in light and dark, and prints what the page shows.
// Usage (dev server already running): node scripts/shots.mjs http://127.0.0.1:5191 outdir name=/path ...
import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const [base, outDir, ...pages] = process.argv.slice(2);
mkdirSync(outDir, { recursive: true });
const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const port = 9400 + Math.floor(Math.random() * 400);
const profile = mkdtempSync(join(tmpdir(), "shots-"));
const chrome = spawn(CHROME, [`--remote-debugging-port=${port}`, `--user-data-dir=${profile}`, "--headless=new",
  "--no-first-run", "--disable-gpu", "--hide-scrollbars", "about:blank"], { stdio: "ignore" });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function connect() {
  for (let i = 0; i < 50; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
      const t = list.find((x) => x.type === "page");
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
  if (d.id && waiting.has(d.id)) {
    waiting.get(d.id)(d);
    waiting.delete(d.id);
  } else if (d.method === "Runtime.consoleAPICalled" && ["error", "warning"].includes(d.params.type)) {
    logs.push(d.params.args.map((a) => a.value ?? a.description).join(" "));
  } else if (d.method === "Runtime.exceptionThrown") logs.push("EXC " + d.params.exceptionDetails.text);
};
const send = (method, params = {}) =>
  new Promise((res, rej) => {
    const i = ++id;
    waiting.set(i, (d) => (d.error ? rej(new Error(JSON.stringify(d.error))) : res(d.result)));
    ws.send(JSON.stringify({ id: i, method, params }));
  });
const evalJs = async (expr) => (await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true })).result.value;

await send("Page.enable");
await send("Runtime.enable");
const summary = {};
for (const spec of pages) {
  const [name, path] = spec.split("=");
  for (const [w, h, mobile] of [[1280, 900, false], [390, 844, true]]) {
    for (const theme of ["light", "dark"]) {
      logs.length = 0;
      await send("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: 1, mobile });
      await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: theme }] });
      await send("Page.navigate", { url: base + "/" });
      await sleep(600);
      await evalJs(`localStorage.setItem("medsafe.theme", "${theme}")`);
      if (process.env.SHOTS_LOGIN) // sign in through the API so protected pages open; "email:password"
        await evalJs(`fetch("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: ${JSON.stringify(process.env.SHOTS_LOGIN.split(":")[0])}, password: ${JSON.stringify(process.env.SHOTS_LOGIN.split(":")[1])} }) }).then(r => r.status)`);
      await send("Page.navigate", { url: base + path });
      await sleep(4500); // client-side fetches (brand, label text, alternatives)
      const info = await evalJs(`(() => ({
        theme: document.documentElement.dataset.theme,
        url: location.pathname,
        overflowX: document.documentElement.scrollWidth - window.innerWidth,
        h1: document.querySelector("h1")?.innerText,
        h2: [...document.querySelectorAll("h2,h3")].map(x => x.innerText.replace(/\\s+/g, " ")).slice(0, 40),
        options: [...document.querySelectorAll(".label-pick option")].map(o => o.textContent),
        notes: [...document.querySelectorAll("main p.small, main p.muted")].map(p => p.innerText.replace(/\\s+/g, " ")).filter(t => /form|unclear|Different|Check/i.test(t)).slice(0, 12),
        height: document.documentElement.scrollHeight
      }))()`);
      const full = Math.min(info.height, 16000);
      await send("Emulation.setDeviceMetricsOverride", { width: w, height: full, deviceScaleFactor: 1, mobile });
      await sleep(400);
      const shot = await send("Page.captureScreenshot", { format: "png" });
      const file = join(outDir, `${name}-${w}-${theme}.png`);
      writeFileSync(file, Buffer.from(shot.data, "base64"));
      summary[`${name}-${w}-${theme}`] = { ...info, console: [...logs], file };
    }
  }
}
writeFileSync(join(outDir, "log.json"), JSON.stringify(summary, null, 1));
console.log(JSON.stringify(Object.fromEntries(Object.entries(summary).map(([k, v]) => [k, { theme: v.theme, url: v.url, overflowX: v.overflowX, height: v.height, console: v.console }])), null, 1));
ws.close();
chrome.kill();
process.exit(0);
