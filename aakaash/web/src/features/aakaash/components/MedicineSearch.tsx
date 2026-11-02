import { useCallback, useEffect, useId, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import { MagnifyingGlass, X } from "@phosphor-icons/react";
import { api } from "../api";
import type { SuggestResponse, Suggestion } from "../api";
import { Sticker } from "./Sticker";

const DEBOUNCE_MS = 150;
const RECENT_KEY = "medsafe.recent";
const RECENT_MAX = 6;

export type Recent = { name: string; set_id: string; type: Suggestion["type"]; manufacturer: string | null };

export function readRecent(): Recent[] {
  try {
    const v = JSON.parse(localStorage.getItem(RECENT_KEY) ?? "[]");
    return Array.isArray(v) ? v.filter((r) => r && typeof r.set_id === "string" && typeof r.name === "string").slice(0, RECENT_MAX) : [];
  } catch {
    return [];
  }
}

function saveRecent(s: Suggestion) {
  try {
    const rest = readRecent().filter((r) => r.set_id !== s.set_id);
    const item: Recent = { name: s.name, set_id: s.set_id, type: s.type, manufacturer: s.manufacturer };
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
  onSelect: (s: Suggestion | Recent) => void;
  placeholder?: string;
  large?: boolean;
  autoFocus?: boolean;
  /** Clear the box after a pick (the checker adds chips). */
  clearOnSelect?: boolean;
  hint?: string;
};

/** ARIA 1.2 combobox with a listbox popup. The suggestions come from GET /api/medicine/suggest. */
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
  const rows: (Suggestion | Recent)[] = showRecent ? recent : view.kind === "ok" ? view.data.suggestions : [];

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
    (r: Suggestion | Recent) => {
      saveRecent({ name: r.name, set_id: r.set_id, type: r.type, manufacturer: r.manufacturer } as Suggestion);
      setOpen(false);
      setActive(-1);
      if (clearOnSelect) onValueChange("");
      onSelect(r);
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
    else if (view.kind === "ok" && view.data.status === "ready")
      status = view.data.suggestions.length ? `${view.data.suggestions.length} suggestions. Use up and down arrows, Enter to open.` : "No medicine found";
  }

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
      <div className="combo-pop" hidden={!expanded}>
        {showRecent && recent.length > 0 && <div className="combo-group font-nav">Recent</div>}
        <ul id={listId} role="listbox" aria-label={showRecent ? "Recent searches" : "Suggestions"}>
          {rows.map((r, i) => (
            <li
              key={r.set_id + r.name}
              id={optionId(i)}
              role="option"
              aria-selected={i === active}
              className={i === active ? "combo-opt active" : "combo-opt"}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => pick(r)}
              onMouseMove={() => active !== i && setActive(i)}
            >
              <span className="combo-name">
                <Highlight text={r.name} term={showRecent ? "" : q} />
              </span>
              <span className="combo-meta">
                <Sticker>{r.type}</Sticker>
                <span className="small muted combo-maker">{r.manufacturer ?? "manufacturer not stated"}</span>
              </span>
            </li>
          ))}
        </ul>
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
            <Sticker>Not ready</Sticker> <span className="small">{view.data.reason}</span>
            <p className="small muted">
              <strong>What is needed:</strong> {view.data.fix}
            </p>
          </div>
        )}
        {!showRecent && view.kind === "ok" && view.data.status === "ready" && view.data.suggestions.length === 0 && (
          <div className="combo-state small">
            No medicine found for “{q}”. Try fewer letters or the generic name.
          </div>
        )}
        {!showRecent && view.kind === "ok" && view.data.status === "ready" && view.data.suggestions.length > 0 && (
          <div className="combo-foot small muted">
            Matched by name only ({view.data.matcher} for typos). {view.data.elapsed_ms} ms.
          </div>
        )}
      </div>
    </div>
  );
}
