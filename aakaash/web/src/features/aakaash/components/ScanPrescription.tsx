import { useEffect, useRef, useState } from "react";
import { Camera, Check, ImageSquare, Trash } from "@phosphor-icons/react";
import { api } from "../api";
import type { BrandSuggestion } from "../api";
import { parseLine, type ParsedLine } from "../ocr/parseLine";
import { defaultReader, type ReadLine } from "../ocr/reader";
import type { ToAddItem } from "../toAdd";
import { emptyCourse } from "../toAdd";
import { Field } from "./Form";
import { MedicineSearch, type Recent } from "./MedicineSearch";
import { Sticker } from "./Sticker";

const CANDIDATES = 3;

type Line = {
  key: number;
  read: ReadLine;
  parsed: ParsedLine;
  query: string;
  dose: string;
  frequency: string;
  duration: string;
  food: string;
  chosen: Recent | null;
  state: "open" | "added" | "dropped";
};

type Phase =
  | { kind: "idle" }
  | { kind: "camera" }
  | { kind: "reading"; fraction: number; status: string }
  | { kind: "error"; message: string }
  | { kind: "review"; reader: string };

const isPhone = () => /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);
// getUserMedia needs a secure context (https or localhost); on plain http the button is not shown
const liveCameraAvailable = () => window.isSecureContext && !!navigator.mediaDevices?.getUserMedia && !isPhone();

/** The search text for a line: the name, plus the strength number when the name has none ("Mox" + "500mg"). */
function queryOf(p: ParsedLine): string {
  if (!p.name) return "";
  const n = p.strength?.match(/^\d+(?:\.\d+)?/)?.[0];
  return n && !/\d/.test(p.name) ? `${p.name} ${n}` : p.name;
}

/** Up to three catalogue matches for a line. Similar spellings are never offered here. Only the
 *  search text is sent to the server, the same request that typing makes. */
function useCandidates(q: string) {
  const [res, setRes] = useState<{ q: string; rows: BrandSuggestion[] } | null>(null);
  useEffect(() => {
    if (q.trim().length < 2) {
      setRes({ q, rows: [] });
      return;
    }
    const ctl = new AbortController();
    const t = window.setTimeout(async () => {
      try {
        let r = await api.suggest(q, ctl.signal, CANDIDATES);
        // "Mox 500" may not start a brand name; then try the name alone
        const plain = q.replace(/\s+\d+(?:\.\d+)?$/, "");
        if (r.status === "ready" && !r.matches.length && plain !== q) r = await api.suggest(plain, ctl.signal, CANDIDATES);
        setRes({ q, rows: r.status === "ready" ? r.matches.slice(0, CANDIDATES) : [] });
      } catch {
        if (!ctl.signal.aborted) setRes({ q, rows: [] });
      }
    }, 250);
    return () => {
      window.clearTimeout(t);
      ctl.abort();
    };
  }, [q]);
  return res && res.q === q ? res.rows : null;
}

function ReviewLine({ line, onChange, onAdd }: { line: Line; onChange: (l: Partial<Line>) => void; onAdd: () => void }) {
  const rows = useCandidates(line.query);
  const [search, setSearch] = useState("");
  const [changing, setChanging] = useState(false);
  const confirm = useRef<HTMLButtonElement>(null);
  const group = `line-${line.key}`;
  if (line.state !== "open")
    return (
      <li className="review-line done">
        <span className="small">
          <Sticker tone={line.state === "added" ? "good" : "neutral"}>{line.state === "added" ? "Added to the list" : "Dropped"}</Sticker>{" "}
          <span className="muted">{line.read.text}</span>
        </span>
        <button type="button" className="btn btn-plain btn-sm" onClick={() => onChange({ state: "open" })}>
          Undo
        </button>
      </li>
    );
  const pick = (r: Recent) => onChange({ chosen: r });
  return (
    <li className="review-line">
      <p className="raw-line">
        <span className="small muted">Read from the image{line.read.confidence != null ? ` (confidence ${line.read.confidence}%)` : ""}:</span>
        <br />
        <code>{line.read.text}</code>
      </p>
      {!line.parsed.name && (
        <p className="small">No medicine name was found on this line. Find the medicine by hand below, or drop the line.</p>
      )}
      <div className="form-grid">
        <Field label="Name to search" hint={line.parsed.strength ? `Strength on the line: ${line.parsed.strength}` : undefined}>
          <input value={line.query} onChange={(e) => onChange({ query: e.target.value, chosen: null })} />
        </Field>
        <Field label="Dose">
          <input value={line.dose} onChange={(e) => onChange({ dose: e.target.value })} placeholder="Not read" />
        </Field>
        <Field label="How often" hint={line.parsed.frequencyText && line.frequency === line.parsed.frequency ? line.parsed.frequencyText : undefined}>
          <input value={line.frequency} onChange={(e) => onChange({ frequency: e.target.value })} placeholder="Not read" />
        </Field>
        <Field label="Duration in days" hint={line.parsed.durationText && !line.parsed.durationDays ? `On the line: ${line.parsed.durationText}` : undefined}>
          <input inputMode="numeric" value={line.duration} onChange={(e) => onChange({ duration: e.target.value.replace(/\D/g, "") })} placeholder="Not read" />
        </Field>
        <Field label="With food">
          <input value={line.food} onChange={(e) => onChange({ food: e.target.value })} placeholder="Not read" />
        </Field>
      </div>
      <fieldset className="candidates">
        <legend className="small">Medicines in our list that match “{line.query || "…"}”</legend>
        {rows === null && line.query.trim().length >= 2 && <div className="skeleton" />}
        {rows?.length === 0 && line.query.trim() && <p className="small muted">No match in our list. Change the name, or find it by hand.</p>}
        {rows?.map((r) => (
          <label key={r.id} className="candidate">
            <input type="radio" name={group} checked={line.chosen?.id === r.id} onChange={() => pick(r)} />
            <span>
              <strong>{r.name}</strong> <span className="small muted">· {r.manufacturer ?? "manufacturer not stated"}</span>
              <br />
              <span className="small muted">{r.composition}</span>
            </span>
          </label>
        ))}
        {line.chosen && !rows?.some((r) => r.id === line.chosen?.id) && (
          <p className="small">
            Chosen by hand: <strong>{line.chosen.name}</strong> <span className="muted">· {line.chosen.composition}</span>
          </p>
        )}
      </fieldset>
      {changing ? (
        <MedicineSearch
          label="Find the medicine by hand"
          value={search}
          onValueChange={setSearch}
          onSelect={(r) => {
            pick(r);
            setChanging(false);
            window.setTimeout(() => confirm.current?.focus(), 0); // the search box is gone: keep focus in this line
          }}
          clearOnSelect
          autoFocus
        />
      ) : (
        <button type="button" className="btn btn-plain btn-sm" onClick={() => setChanging(true)}>
          Find a different medicine by hand
        </button>
      )}
      <div className="form-actions">
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => onChange({ state: "dropped" })}>
          <Trash size={14} aria-hidden="true" /> Drop this line
        </button>
        <button ref={confirm} type="button" className="btn btn-primary btn-sm" disabled={!line.chosen} onClick={onAdd}>
          <Check size={14} aria-hidden="true" /> Confirm and add to the list
        </button>
      </div>
    </li>
  );
}

function LiveCamera({ onShot, onCancel }: { onShot: (b: Blob) => void; onCancel: () => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    let stream: MediaStream | null = null;
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: "environment" }, audio: false })
      .then((s) => {
        stream = s;
        if (video.current) video.current.srcObject = s;
      })
      .catch((e: unknown) => setErr(e instanceof Error ? e.message : String(e)));
    return () => stream?.getTracks().forEach((t) => t.stop());
  }, []);
  function shoot() {
    const v = video.current;
    if (!v || !v.videoWidth) return;
    const c = document.createElement("canvas");
    c.width = v.videoWidth;
    c.height = v.videoHeight;
    c.getContext("2d")?.drawImage(v, 0, 0);
    c.toBlob((b) => b && onShot(b), "image/png");
  }
  return (
    <div className="camera">
      {err ? <p role="alert">The camera could not be opened: {err}</p> : <video ref={video} autoPlay playsInline muted aria-label="Camera preview" />}
      <div className="form-actions">
        <button type="button" className="btn btn-secondary" onClick={onCancel}>
          Cancel
        </button>
        <button type="button" className="btn btn-primary" onClick={shoot} disabled={!!err}>
          Take picture
        </button>
      </div>
    </div>
  );
}

/** Scan a typed or printed prescription. Text recognition runs in this browser; the image is never
 *  uploaded or stored. Every recognised line must be confirmed, changed or dropped by the user. */
export function ScanPrescription({ onAdd }: { onAdd: (item: ToAddItem) => void }) {
  const file = useRef<HTMLInputElement>(null);
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const [preview, setPreview] = useState<string | null>(null);
  const [lines, setLines] = useState<Line[]>([]);
  const camera = liveCameraAvailable();

  useEffect(() => () => void (preview && URL.revokeObjectURL(preview)), [preview]);

  async function read(image: Blob) {
    setPreview(URL.createObjectURL(image)); // a local object URL, only for showing the picture here
    setLines([]);
    setPhase({ kind: "reading", fraction: 0, status: "starting" });
    try {
      const reader = await defaultReader();
      const res = await reader.recognise(image, (fraction, status) => setPhase({ kind: "reading", fraction, status }));
      setLines(
        res.lines.map((r, i) => {
          const p = parseLine(r.text);
          return {
            key: i, read: r, parsed: p, query: queryOf(p), dose: p.dose ?? "", frequency: p.frequency ?? "",
            duration: p.durationDays ? String(p.durationDays) : "", food: p.food ?? "", chosen: null, state: "open",
          };
        }),
      );
      setPhase({ kind: "review", reader: res.reader });
    } catch (e) {
      setPhase({ kind: "error", message: e instanceof Error ? e.message : String(e) });
    }
  }

  const update = (key: number, patch: Partial<Line>) => setLines((ls) => ls.map((l) => (l.key === key ? { ...l, ...patch } : l)));
  const add = (l: Line) => {
    if (!l.chosen) return;
    onAdd({
      id: l.chosen.id, name: l.chosen.name, manufacturer: l.chosen.manufacturer, composition: l.chosen.composition,
      source: "scanned", raw: l.read.text, ...emptyCourse,
      dose: l.dose, frequency: l.frequency, food: l.food, duration_days: l.duration,
    });
    update(l.key, { state: "added" });
  };
  const open = lines.filter((l) => l.state === "open").length;

  return (
    <div className="scan">
      <div className="scan-actions">
        <input
          ref={file}
          type="file"
          accept="image/*"
          capture="environment"
          className="sr-only"
          tabIndex={-1}
          aria-hidden="true"
          onChange={(e) => {
            const f = e.target.files?.[0];
            e.target.value = "";
            if (f) void read(f);
          }}
        />
        <button type="button" className="btn btn-primary" onClick={() => file.current?.click()} disabled={phase.kind === "reading"}>
          <ImageSquare size={18} aria-hidden="true" /> Take a photo or upload an image
        </button>
        {camera && (
          <button type="button" className="btn btn-secondary" onClick={() => setPhase({ kind: "camera" })} disabled={phase.kind === "reading"}>
            <Camera size={18} aria-hidden="true" /> Use the camera
          </button>
        )}
      </div>
      <p className="small muted">Works best with printed or typed prescriptions. Handwriting is not supported.</p>
      <p className="small muted">The picture and the text read from it stay on this device. Only the medicine name you search for is sent, as when you type it.</p>

      {phase.kind === "camera" && <LiveCamera onShot={(b) => void read(b)} onCancel={() => setPhase({ kind: "idle" })} />}
      {preview && phase.kind !== "camera" && <img className="scan-preview" src={preview} alt="The prescription picture you chose" />}
      {phase.kind === "reading" && (
        <div className="notice" role="status" aria-live="polite">
          <span className="spinner" aria-hidden="true" /> Reading the text on this device… {Math.round(phase.fraction * 100)}%{" "}
          <span className="small muted">({phase.status})</span>
          <progress max={1} value={phase.fraction} aria-label="Reading progress" />
        </div>
      )}
      {phase.kind === "error" && (
        <div className="notice notice-error" role="alert">
          <p>The text could not be read: {phase.message}</p>
        </div>
      )}
      {phase.kind === "review" && (
        <section aria-labelledby="review-h">
          <h3 id="review-h">Check each line</h3>
          {lines.length === 0 ? (
            <p>No text was found in the picture. Try a sharper, well-lit photo of a printed prescription.</p>
          ) : (
            <p className="small">
              {lines.length} {lines.length === 1 ? "line was" : "lines were"} read ({phase.reader}, on this device). Nothing is added until you
              confirm it. {open > 0 ? `${open} still to check.` : "All lines are done."}
            </p>
          )}
          <ul className="review-list">
            {lines.map((l) => (
              <ReviewLine key={l.key} line={l} onChange={(p) => update(l.key, p)} onAdd={() => add(l)} />
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
