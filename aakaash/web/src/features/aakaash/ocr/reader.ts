// SOURCE: NOT IN PAPERS. A small interface so another text reader can replace tesseract.js later.
// Every reader runs on the user's device: the image is never uploaded or stored.

export type ReadLine = { text: string; confidence: number | null };
export type ReadResult = { lines: ReadLine[]; reader: string };

export interface PrescriptionReader {
  /** Short id shown on /about/data and in the review screen. */
  id: string;
  /** Recognise printed or typed text. `onProgress` gets a 0-1 fraction and a short status. */
  recognise(image: Blob, onProgress?: (fraction: number, status: string) => void): Promise<ReadResult>;
}

/** The reader the scan tab uses. Loaded only when a scan starts, so the app does not carry it otherwise. */
export async function defaultReader(): Promise<PrescriptionReader> {
  const { tesseractReader } = await import("./tesseractReader");
  return tesseractReader;
}
