import { useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { useSearchParams } from "react-router-dom";
import type { MedicineResponse } from "../api";

const escapeRx = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** Split text around case-insensitive matches of `find`. Returns text pieces and the match count. */
function splitMatches(text: string, find: string): { parts: { t: string; hit: boolean }[]; count: number } {
  const f = find.trim();
  if (f.length < 2) return { parts: [{ t: text, hit: false }], count: 0 };
  const rx = new RegExp(escapeRx(f), "gi");
  const parts: { t: string; hit: boolean }[] = [];
  let last = 0;
  let count = 0;
  for (const m of text.matchAll(rx)) {
    if (m.index! > last) parts.push({ t: text.slice(last, m.index), hit: false });
    parts.push({ t: m[0], hit: true });
    last = m.index! + m[0].length;
    count++;
  }
  if (last < text.length) parts.push({ t: text.slice(last), hit: false });
  return { parts, count };
}

const countMatches = (text: string, find: string) => splitMatches(text, find).count;

// A line is shown as a heading when it is short, has no closing full stop, and either starts with a
// section number (5.1 Hepatotoxicity) or is written in capitals. The parser keeps heading lines in the text.
function isHeading(line: string): boolean {
  const l = line.trim();
  if (l.length < 3 || l.length > 110 || /[.;,]$/.test(l)) return false;
  if (/^\d+(\.\d+)*\s+\S/.test(l)) return true;
  return /[A-Z]/.test(l) && l === l.toUpperCase() && l.length < 70;
}

// The parser starts a new line after every inline reference ("[see" / "Warnings and Precautions (5.1)" / "]."),
// so a sentence arrives in pieces. Rejoin a piece onto the line before it when that line ends in "see" or the
// piece starts with closing punctuation.
function joinBrokenLines(lines: string[]): string[] {
  const out: string[] = [];
  for (const l of lines) {
    const prev = out[out.length - 1];
    if (prev !== undefined && (/[[(]\s*see$/i.test(prev) || /^[\]).,;:]/.test(l)) && !isHeading(prev)) out[out.length - 1] = `${prev} ${l}`;
    else out.push(l);
  }
  return out;
}

function Highlighted({ text, find }: { text: string; find: string }) {
  const { parts } = splitMatches(text, find);
  return (
    <>
      {parts.map((p, i) =>
        p.hit ? (
          <mark key={i} className="find-hit">
            {p.t}
          </mark>
        ) : (
          <span key={i}>{p.t}</span>
        ),
      )}
    </>
  );
}

function SectionText({ text, find }: { text: string; find: string }) {
  const lines = useMemo(() => joinBrokenLines(text.split(/\n+/).map((l) => l.trim()).filter(Boolean)), [text]);
  return (
    <div className="label-text">
      {lines.map((line, i) =>
        isHeading(line) ? (
          <h3 key={i} className="label-heading">
            <Highlighted text={line} find={find} />
          </h3>
        ) : (
          <p key={i}>
            <Highlighted text={line} find={find} />
          </p>
        ),
      )}
    </div>
  );
}

/** Section tabs with find-in-section for one US label. State (tab, find) lives in the URL. */
export function LabelTabs({ med }: { med: MedicineResponse }) {
  const [params, setParams] = useSearchParams();
  const find = params.get("find") ?? "";
  const keys = med.sections.map((s) => s.key);
  const current = med.sections.find((s) => s.key === params.get("tab")) ?? med.sections[0];
  const body = useRef<HTMLDivElement>(null);
  const [cursor, setCursor] = useState(0);
  const total = current ? countMatches(current.text, find) : 0;
  const update = (patch: Record<string, string>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(patch)) v ? next.set(k, v) : next.delete(k);
    setParams(next, { replace: true });
  };

  useEffect(() => {
    setCursor(0);
  }, [find, current?.key]);
  const jump = (n: number) => {
    if (!total) return;
    const i = (n + total) % total;
    setCursor(i);
    body.current?.querySelectorAll<HTMLElement>("mark.find-hit")[i]?.scrollIntoView({ block: "center", behavior: "smooth" });
  };
  // mark the current match
  useEffect(() => {
    body.current?.querySelectorAll("mark.find-hit").forEach((m, i) => m.classList.toggle("current", i === cursor));
  });

  function onTabKey(e: KeyboardEvent<HTMLButtonElement>, i: number) {
    let j = -1;
    if (e.key === "ArrowRight") j = (i + 1) % keys.length;
    else if (e.key === "ArrowLeft") j = (i - 1 + keys.length) % keys.length;
    else if (e.key === "Home") j = 0;
    else if (e.key === "End") j = keys.length - 1;
    if (j < 0) return;
    e.preventDefault();
    update({ tab: keys[j] });
    document.getElementById(`tab-${keys[j]}`)?.focus();
  }

  if (!current) {
    return <p className="muted">No text could be read from this label.</p>;
  }
  return (
    <>
      <div className="tabs" role="tablist" aria-label="Label sections">
        {med.sections.map((s, i) => {
          const n = countMatches(s.text, find);
          return (
            <button
              key={s.key}
              id={`tab-${s.key}`}
              type="button"
              role="tab"
              aria-selected={s.key === current.key}
              aria-controls="tabpanel"
              tabIndex={s.key === current.key ? 0 : -1}
              className={s.key === current.key ? "tab active" : "tab"}
              onClick={() => update({ tab: s.key })}
              onKeyDown={(e) => onTabKey(e, i)}
            >
              {s.label}
              {find.trim().length >= 2 && <span className="tab-count">{n}</span>}
            </button>
          );
        })}
      </div>
      <div className="find-row">
        <label htmlFor="find-input" className="small muted">
          Find in this section
        </label>
        <input
          id="find-input"
          type="search"
          value={find}
          placeholder="Type at least 2 letters"
          onChange={(e) => update({ find: e.target.value })}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              jump(cursor + (e.shiftKey ? -1 : 1));
            }
          }}
        />
        <span className="small muted find-count" role="status" aria-live="polite">
          {find.trim().length >= 2 ? (total ? `${cursor + 1} of ${total}` : "No matches in this section") : ""}
        </span>
        <button type="button" className="btn btn-secondary btn-sm" disabled={!total} onClick={() => jump(cursor + 1)}>
          Next match
        </button>
      </div>
      <div id="tabpanel" role="tabpanel" aria-labelledby={`tab-${current.key}`} tabIndex={0} ref={body} className="label-body">
        <SectionText text={current.text} find={find} />
      </div>
    </>
  );
}

export function Skeleton({ lines = 4 }: { lines?: number }) {
  return (
    <div aria-hidden="true">
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="skeleton" style={{ width: `${95 - ((i * 13) % 40)}%` }} />
      ))}
    </div>
  );
}
