// SOURCE: NOT IN PAPERS (own tooling). Copies the text-recognition files that tesseract.js would
// otherwise fetch from a CDN at run time into public/ocr/, so the browser loads them from this app's
// own origin: the worker, the LSTM builds of tesseract.js-core and the English language data.
// public/ocr/ is gitignored (the language data is a model file). Runs before `npm run dev` and
// `npm run build`; run it by hand with `node scripts/copy-ocr.mjs`.
import { copyFileSync, existsSync, mkdirSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const web = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const nm = join(web, "node_modules");
const out = join(web, "public", "ocr");
// createWorker(..., OEM 1 = LSTM only) picks one of these three by the browser's wasm features
const files = [
  ["tesseract.js/dist/worker.min.js", "worker.min.js"],
  ["tesseract.js-core/tesseract-core-lstm.wasm.js", "core/tesseract-core-lstm.wasm.js"],
  ["tesseract.js-core/tesseract-core-simd-lstm.wasm.js", "core/tesseract-core-simd-lstm.wasm.js"],
  ["tesseract.js-core/tesseract-core-relaxedsimd-lstm.wasm.js", "core/tesseract-core-relaxedsimd-lstm.wasm.js"],
  // the "best_int" English model is the one tesseract.js uses for OEM 1
  ["@tesseract.js-data/eng/4.0.0_best_int/eng.traineddata.gz", "lang/eng.traineddata.gz"],
];
for (const [from, to] of files) {
  const src = join(nm, from);
  if (!existsSync(src)) throw new Error(`Missing ${src}. Run npm install in aakaash/web.`);
  const dst = join(out, to);
  mkdirSync(dirname(dst), { recursive: true });
  if (existsSync(dst) && statSync(dst).size === statSync(src).size) continue;
  copyFileSync(src, dst);
  console.log(`copied ${to} (${(statSync(dst).size / 1e6).toFixed(1)} MB)`);
}
