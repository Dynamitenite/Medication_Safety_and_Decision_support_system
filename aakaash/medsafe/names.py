# SOURCE: NOT IN PAPERS. Own design: name search over the DailyMed name index, same-active-moiety
# lookup, and sentence-level name matching between two labels. No model, no embeddings, no
# invented values: everything returned comes from the label records passed in.
"""Pure logic (no file or network access) so it can be tested with hand-written fixtures."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from itertools import combinations

try:  # rapidfuzz is optional; difflib is the fallback
    from rapidfuzz import fuzz, process
    FUZZY_BACKEND = "rapidfuzz"
except ImportError:  # pragma: no cover - depends on the environment
    import difflib
    fuzz = process = None
    FUZZY_BACKEND = "difflib"

from .forms import describe

TYPE_RANK = {"brand": 0, "generic": 1, "ingredient": 2}
MATCH_NAMES = {0: "prefix", 1: "word", 2: "substring", 3: "fuzzy"}
FUZZY_CUTOFF = 85  # rapidfuzz WRatio, 0-100
MIN_TERM_LEN = 4   # shorter names are never used for text matching (avoids false hits)


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.lower())).strip()


def display(text: str) -> str:
    return text.title() if text.isupper() else text


@dataclass
class Entry:
    name: str  # display form
    key: str   # normalised
    type: str  # brand | generic | ingredient
    idx: int   # representative label
    count: int = 0  # labels carrying this name
    _seen: set = field(default_factory=set, repr=False)


class NameIndex:
    def __init__(self, labels: list[dict]):
        self.labels = labels
        self.by_id = {l["set_id"]: i for i, l in enumerate(labels)}
        entries: dict[str, Entry] = {}

        def add(raw: str, typ: str, i: int) -> None:
            key = norm(raw)
            if not key:
                return
            e = entries.get(key)
            if e is None:
                e = entries[key] = Entry(display(raw.strip()), key, typ, i)
            elif TYPE_RANK[typ] < TYPE_RANK[e.type]:
                e.type, e.idx, e.name = typ, i, display(raw.strip())
            if i not in e._seen:
                e._seen.add(i)
                e.count += 1

        for i, l in enumerate(labels):
            plain = {norm(x) for x in l["generic"] + l["ingredients"] + l["moieties"]}
            for p in l["products"]:
                add(p, "generic" if norm(p) in plain else "brand", i)
            for g in l["generic"]:
                add(g, "generic", i)
            for ing in l["ingredients"] + l.get("moieties_raw", []):
                add(ing, "ingredient", i)
        self.entries = sorted(entries.values(), key=lambda e: e.key)
        self._keys = [e.key for e in self.entries]
        for e in self.entries:
            del e._seen

    # ---- suggest ------------------------------------------------------------------------
    def suggest(self, q: str, limit: int = 8) -> list[dict]:
        qn = norm(q)
        if not qn:
            return []
        tiered: list[tuple[tuple, Entry, int]] = []
        padded = " " + qn
        for e in self.entries:
            k = e.key
            if k.startswith(qn):
                tier = 0
            elif padded in " " + k:
                tier = 1
            elif qn in k:
                tier = 2
            else:
                continue
            tiered.append(((tier, -e.count, len(k), TYPE_RANK[e.type], k), e, tier))
        tiered.sort(key=lambda t: t[0])
        hits = [(e, tier) for _, e, tier in tiered[:limit]]
        if len(hits) < limit and len(qn) >= 3:
            taken = {e.key for e, _ in hits}
            hits += [(e, 3) for e in self._fuzzy(qn, limit - len(hits), taken)]
        return [self._row(e, tier) for e, tier in hits]

    def _fuzzy(self, qn: str, n: int, taken: set[str]) -> list[Entry]:
        if process is not None:
            found = process.extract(qn, self._keys, scorer=fuzz.WRatio, score_cutoff=FUZZY_CUTOFF,
                                    limit=n + len(taken))
            idxs = [i for _, _, i in found]
        else:  # pragma: no cover
            close = difflib.get_close_matches(qn, self._keys, n=n + len(taken), cutoff=0.75)
            pos = {k: i for i, k in enumerate(self._keys)}
            idxs = [pos[k] for k in close]
        return [self.entries[i] for i in idxs if self._keys[i] not in taken][:n]

    def _row(self, e: Entry, tier: int) -> dict:
        l = self.labels[e.idx]
        return {"name": e.name, "type": e.type, "manufacturer": l["manufacturer"],
                "set_id": l["set_id"], "label_count": e.count, "match": MATCH_NAMES[tier]}

    # ---- same active moiety ------------------------------------------------------------
    def alternatives(self, set_id: str) -> list[dict]:
        """Other labels whose FULL set of active moieties equals this label's. Combination
        products therefore match only other products with the same combination."""
        i = self.by_id[set_id]
        moi = frozenset(self.labels[i]["moieties"])
        if not moi:
            return []
        groups: dict[tuple, dict] = {}
        for j, l in enumerate(self.labels):
            if j == i or frozenset(l["moieties"]) != moi:
                continue
            name = l["products"][0] if l["products"] else (l["generic"][0] if l["generic"] else "")
            g = groups.setdefault((norm(name), l["manufacturer"] or ""), {
                "product": name, "manufacturer": l["manufacturer"], "set_id": l["set_id"],
                "ingredients": l["ingredients"], "label_count": 0, "form": describe(l.get("dosage_forms"))})
            g["label_count"] += 1
        return sorted(groups.values(), key=lambda g: (norm(g["product"]), g["manufacturer"] or ""))


# ---- sentence-level name matching ------------------------------------------------------
_PROTECT = re.compile(r"\b(e\.g|i\.e|vs|approx|etc|cf|Inc|Co|Ltd|St)\.", re.I)
_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\[])|\n+")


def split_sentences(text: str) -> list[str]:
    t = _PROTECT.sub(lambda m: m.group(0).replace(".", "\x00"), text)
    out = (s.replace("\x00", ".").strip() for s in _SPLIT.split(t))
    return [s for s in out if s]


def drug_terms(label: dict) -> list[str]:
    """Names used to find this drug in someone else's text: product names and active moieties,
    each at least MIN_TERM_LEN characters. Longest first."""
    # accepts a name-index record (products, moieties) or a parse_label record (product_names,
    # active_moieties)
    prods = label.get("products", label.get("product_names", []))
    moi = label.get("moieties", label.get("active_moieties", []))
    terms = {norm(t) for t in prods + moi}
    return sorted((t for t in terms if len(t) >= MIN_TERM_LEN), key=len, reverse=True)


def term_regex(terms: list[str]) -> re.Pattern | None:
    if not terms:
        return None
    alts = "|".join(r"\s+".join(re.escape(w) for w in t.split()) for t in terms)
    return re.compile(rf"(?<![A-Za-z0-9])(?:{alts})(?![A-Za-z0-9])", re.I)


def excerpt(s: str, start: int, end: int, window: int = 200) -> str:
    """Long lines (drug lists flattened from tables) are cut to `window` characters each side of
    the match, at word boundaries, with an ellipsis where text was dropped."""
    if len(s) <= 2 * window + (end - start):
        return s
    a, b = max(0, start - window), min(len(s), end + window)
    if a > 0:
        a = s.find(" ", a) + 1 or a
    if b < len(s):
        b = s.rfind(" ", start, b) if s.rfind(" ", end, b) == -1 else s.rfind(" ", end, b)
    return ("… " if a > 0 else "") + s[a:b].strip() + (" …" if b < len(s) else "")


def mentions(section_text: str, target: dict) -> list[dict]:
    """Sentences of `section_text` that name `target` (word-boundary match)."""
    rx = term_regex(drug_terms(target))
    if rx is None or not section_text:
        return []
    out = []
    for s in split_sentences(section_text):
        m = rx.search(s)
        if m:
            out.append({"sentence": excerpt(s, m.start(), m.end()), "matched_term": m.group(0)})
    return out


def pairs(ids: list[str]) -> list[tuple[str, str]]:
    return list(combinations(ids, 2))
