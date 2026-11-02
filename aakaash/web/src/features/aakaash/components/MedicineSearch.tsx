import { useCallback, useEffect, useId, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import { MagnifyingGlass, X } from "@phosphor-icons/react";
import { api } from "../api";
import type { BrandSuggestion, SuggestResponse } from "../api";
import { Sticker } from "./Sticker";
import { FormTag } from "./viz/icons";
import { NoResultsArt } from "./viz/Illustrations";

const DEBOUNCE_MS = 150;
// v2: entries are catalogue ids. The v1 list held US label ids and is no longer read.
const RECENT_KEY = "medsafe.recent.v2";
const RECENT_MAX = 6;

export type Recent = { id: string; name: string; manufacturer: string | null; composition: string; discontinued?: boolean; form_family?: string; type?: string; price?: number | null; pack_size?: string };
type Row = Recent & { match?: BrandSuggestion["match"]; matched_ingredient?: string | null; similar?: boolean };

export function readRecent(): Recent[] {
  try {
    const v = JSON.parse(localStorage.getItem(RECENT_KEY) ?? "[]");
    return Array.isArray(v)
      ? v.filter((r) => r && typeof r.id === "string" && typeof r.name === "string" && typeof r.composition === "string").slice(0, RECENT_MAX)
      : [];
  } catch {
    return [];
  }
}

function saveRecent(s: Recent) {
  try {
    const rest = readRecent().filter((r) => r.id !== s.id);
    const item: Recent = { ...s };
    localStorage.setItem(RECENT_KEY, JSON.stringify([item, ...rest].slice(0, RECENT_MAX)));
  } catch {
    /* storage blocked or full: recent searches are a convenience only */
  }
}

/** Bold the first case-insensitive occurrence of the typed text. Fuzzy matches have none. */
export function Highlight({ text, term }: { text: string; term: string }): ReactNode {
  const t = term.trim();
  const i = t ? text.toLowerCase().indexOf(t.toLowerCase()) : -1;
  if (i < 0) return text;
  return (
    <>
      {text.slice(0, i)}
      <strong className="hit">{text.slice(i, i + t.length)}</strong>
      {text.slice(i + t.length)}
    </>
  );
}

type View =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ok"; data: SuggestResponse };

type Props = {
  label: string;
  value: string;
  onValueChange: (v: string) => void;
  onSelect: (s: Recent) => void;
  placeholder?: string;
  large?: boolean;
  autoFocus?: boolean;
  /** Clear the box after a pick (the checker adds chips). */
  clearOnSelect?: boolean;
  hint?: string;
};

/** ARIA 1.2 combobox with a listbox popup. The suggestions come from GET /api/medicine/suggest in two
 *  groups: matches, then (only when there are few matches) similar spellings, shown apart and never
 *  picked unless the user moves to one. */
export function MedicineSearch({ label, value, onValueChange, onSelect, placeholder, large, autoFocus, clearOnSelect, hint }: Props) {
  const uid = useId();
  const listId = `${uid}-list`;
  const hintId = `${uid}-hint`;
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<View>({ kind: "idle" });
  const [active, setActive] = useState(-1);
  const [recent, setRecent] = useState<Recent[]>([]);
  const [retry, setRetry] = useState(0);
  const wrap = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);

  const q = value.trim();
  const showRecent = q === "";
  const data = view.kind === "ok" && view.data.status === "ready" ? view.data : null;
  const matches: Row[] = showRecent ? recent : data ? data.matches : [];
  const similar: Row[] = !showRecent && data ? data.similar.map((s) => ({ ...s, similar: true })) : [];
  const rows: Row[] = [...matches, ...similar];

  useEffect(() => {
    if (autoFocus) input.current?.focus();
  }, [autoFocus]);

  // Debounced fetch; a newer keystroke aborts the older request so results never arrive out of order.
  useEffect(() => {
    if (!q) {
      setView({ kind: "idle" });
      return;
    }
    setView({ kind: "loading" });
    const ctl = new AbortController();
    const timer = window.setTimeout(() => {
      api
        .suggest(q, ctl.signal)
        .then((data) => {
          setView({ kind: "ok", data });
          setActive(-1);
        })
        .catch((e: unknown) => {
          if (ctl.signal.aborted) return;
          setView({ kind: "error", message: e instanceof Error ? e.message : String(e) });
        });
    }, DEBOUNCE_MS);
    return () => {
      window.clearTimeout(timer);
      ctl.abort();
    };
  }, [q, retry]);

  useEffect(() => {
    const off = (e: MouseEvent) => {
      if (wrap.current && !wrap.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", off);
    return () => document.removeEventListener("mousedown", off);
  }, []);

  const pick = useCallback(
    (r: Row) => {
      saveRecent(r);
      setOpen(false);
      setActive(-1);
      if (clearOnSelect) onValueChange("");
      onSelect({ ...r });
    },
    [clearOnSelect, onSelect, onValueChange],
  );

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!open) {
        setRecent(readRecent());
        setOpen(true);
        return;
      }
      if (rows.length === 0) return;
      const step = e.key === "ArrowDown" ? 1 : -1;
      setActive((a) => (a === -1 ? (step === 1 ? 0 : rows.length - 1) : (a + step + rows.length) % rows.length));
    } else if (e.key === "Enter") {
      // Only an option the user moved to is picked. Enter with nothing selected picks nothing,
      // so a similar spelling is never chosen for the user.
      if (open && active >= 0 && rows[active]) {
        e.preventDefault();
        pick(rows[active]);
      }
    } else if (e.key === "Escape") {
      if (open) {
        e.preventDefault();
        setOpen(false);
        setActive(-1);
      } else if (value) {
        onValueChange("");
      }
    }
  }

  const expanded = open && (showRecent ? recent.length > 0 : true);
  const optionId = (i: number) => `${uid}-opt-${i}`;

  let status = "";
  if (!showRecent) {
    if (view.kind === "loading") status = "Searching";
    else if (view.kind === "error") status = "Search failed";
    else if (data) {
      status = data.matches.length
        ? `${data.matches.length} medicines found. Use up and down arrows, Enter to open.`
        : `We couldn't find ${q} in our database.`;
      if (data.similar.length) status += ` ${data.similar.length} similar spellings, check carefully.`;
    }
  }

  const option = (r: Row, i: number) => (
    <li
      key={(r.similar ? "s" : "m") + r.id}
      id={optionId(i)}
      role="option"
      aria-selected={i === active}
      className={`combo-opt${i === active ? " active" : ""}${r.similar ? " combo-similar" : ""}`}
      onMouseDown={(e) => e.preventDefault()}
      onClick={() => pick(r)}
      onMouseMove={() => active !== i && setActive(i)}
    >
      <span className="combo-name">
        <span className="combo-title">
          <Highlight text={r.name} term={showRecent || r.similar ? "" : q} />
        </span>
        <span className="small muted combo-comp">
          {r.matched_ingredient && r.match === "ingredient" ? <Highlight text={r.composition} term={q} /> : r.composition}
        </span>
      </span>
      <span className="combo-meta">
        <span className="combo-tags"><FormTag family={r.form_family} />{r.type && <Sticker>{r.type}</Sticker>}{r.price != null && <Sticker>{`₹${r.price.toLocaleString("en-IN")} per pack`}</Sticker>}</span>
        {r.discontinued && <Sticker>Discontinued</Sticker>}
        <span className="small muted combo-maker">{r.manufacturer ?? "manufacturer not stated"}</span>
      </span>
    </li>
  );

  return (
    <div className="combo" ref={wrap}>
      <label className="combo-label" htmlFor={`${uid}-input`}>
        {label}
      </label>
      <div className={large ? "combo-box combo-large" : "combo-box"}>
        <MagnifyingGlass size={large ? 22 : 18} aria-hidden="true" className="combo-icon" />
        <input
          ref={input}
          id={`${uid}-input`}
          type="text"
          role="combobox"
          aria-expanded={expanded}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-haspopup="listbox"
          aria-activedescendant={expanded && active >= 0 ? optionId(active) : undefined}
          aria-describedby={hint ? hintId : undefined}
          autoComplete="off"
          autoCapitalize="off"
          spellCheck={false}
          placeholder={placeholder}
          value={value}
          onChange={(e) => {
            onValueChange(e.target.value);
            setOpen(true);
            setRecent(readRecent());
          }}
          onFocus={() => {
            setRecent(readRecent());
            setOpen(true);
          }}
          onKeyDown={onKeyDown}
        />
        {value && (
          <button
            type="button"
            className="btn btn-plain btn-icon btn-sm combo-clear"
            aria-label="Clear search"
            onClick={() => {
              onValueChange("");
              input.current?.focus();
            }}
          >
            <X size={16} />
          </button>
        )}
      </div>
      {hint && (
        <p id={hintId} className="small muted combo-hint">
          {hint}
        </p>
      )}
      <span className="sr-only" role="status" aria-live="polite">
        {status}
      </span>
      <div className="combo-pop" tabIndex={0} hidden={!expanded}>
        {data && data.matches.length === 0 && (
          <div className="combo-state small"><NoResultsArt />We couldn’t find “{q}” in our database.</div>
        )}
        <div id={listId} role="listbox" aria-label={showRecent ? "Recent searches" : "Suggestions"}>
          {matches.length > 0 && (
            <ul role="group" aria-label={showRecent ? "Recent" : "Matches"}>
              {showRecent && <li role="presentation" className="combo-group font-nav">Recent</li>}
              {matches.map((r, i) => option(r, i))}
            </ul>
          )}
          {similar.length > 0 && (
            <ul role="group" aria-labelledby={`${uid}-similar`} className="combo-similar-group">
              <li role="presentation" id={`${uid}-similar`} className="combo-group font-nav">
                Similar spellings, check carefully
              </li>
              {similar.map((r, i) => option(r, matches.length + i))}
            </ul>
          )}
        </div>
        {!showRecent && view.kind === "loading" && (
          <div className="combo-state" aria-hidden="true">
            <div className="skeleton" />
            <div className="skeleton" />
            <div className="skeleton" />
          </div>
        )}
        {!showRecent && view.kind === "error" && (
          <div className="combo-state" role="alert">
            <Sticker tone="danger">Error</Sticker> <span className="small">{view.message}</span>{" "}
            <button type="button" className="btn btn-secondary btn-sm" onMouseDown={(e) => e.preventDefault()} onClick={() => setRetry((n) => n + 1)}>
              Retry
            </button>
          </div>
        )}
        {!showRecent && view.kind === "ok" && view.data.status === "not_ready" && (
          <div className="combo-state">
            <Sticker>Unavailable</Sticker> <span className="small">{view.data.reason}</span>
            <p className="small muted">
              <strong>What is needed:</strong> {view.data.fix}
            </p>
          </div>
        )}
        {data && data.matches.length + data.similar.length > 0 && (
          <div className="combo-foot small muted">Matched by brand name or ingredient.</div>
        )}
      </div>
    </div>
  );
}
