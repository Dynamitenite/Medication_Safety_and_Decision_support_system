// SOURCE: NOT IN PAPERS. tesseract.js 7.0.0 (Apache-2.0) running in a Web Worker in the browser.
// Every file it needs is served by this app from /ocr/ (copied by scripts/copy-ocr.mjs), so it makes
// no request to a CDN; the image stays on the device. English, LSTM engine (OEM 1).
import { createWorker } from "tesseract.js";
import type { PrescriptionReader, ReadLine } from "./reader";

const base = () => `${window.location.origin}/ocr`;

export const tesseractReader: PrescriptionReader = {
  id: "tesseract.js 7.0.0 (English)",
  async recognise(image, onProgress) {
    const worker = await createWorker("eng", 1, {
      workerPath: `${base()}/worker.min.js`,
      corePath: `${base()}/core`,
      langPath: `${base()}/lang`,
      workerBlobURL: false,
      cacheMethod: "none", // nothing is written to the browser's storage
      gzip: true,
      logger: (m) => onProgress?.(typeof m.progress === "number" ? m.progress : 0, m.status),
    });
    try {
      const { data } = await worker.recognize(image, {}, { text: true, blocks: true });
      const lines: ReadLine[] = [];
      for (const b of data.blocks ?? [])
        for (const p of b.paragraphs)
          for (const l of p.lines) {
            const text = l.text.replace(/\s+/g, " ").trim();
            if (text) lines.push({ text, confidence: Number.isFinite(l.confidence) ? Math.round(l.confidence) : null });
          }
      if (!lines.length && data.text.trim()) // no layout returned: fall back to the plain text, line by line
        for (const t of data.text.split(/\r?\n/)) if (t.trim()) lines.push({ text: t.trim(), confidence: null });
      return { lines, reader: this.id };
    } finally {
      await worker.terminate();
    }
  },
};
