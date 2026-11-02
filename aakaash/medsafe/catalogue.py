# SOURCE: NOT IN PAPERS. Own design: the Indian medicine catalogue (public GitHub
# "Indian-Medicine-Dataset", read from data/indian_meds at build time) as the primary medicine
# list, linked by ingredient to DailyMed labels. Composition parsing, exact name normalisation
# (medsafe/synonyms.csv), linking, search and same-composition alternatives. No model, no
# invented values: everything returned comes from the catalogue rows and label records passed in.
"""Pure logic (no file or network access) so it can be tested with hand-written fixtures.
scripts/build_catalogue.py does the reading and writing; api/services/catalogue.py serves it."""
from __future__ import annotations

import heapq
import json
import re
from bisect import bisect_left
from collections import Counter, defaultdict
from typing import Iterable

from .appms_match import ingredient_keys, label_keys
from .forms import UNKNOWN, classify_label, classify_product
from .names import norm
from .synonyms import canonical

try:  # rapidfuzz is optional; difflib is the fallback
    from rapidfuzz import fuzz, process
    FUZZY_BACKEND = "rapidfuzz"
except ImportError:  # pragma: no cover - depends on the environment
    import difflib
    fuzz = process = None
    FUZZY_BACKEND = "difflib"

SHORT_FIELDS = ("short_composition1", "short_composition2")
EMPTY_INTERACTIONS = '{"drug": [], "brand": [], "effect": []}'
FLAG_INCOMPLETE = 1  # two short fields and no salt_composition: the short fields hold at most two
FLAG_CONFLICT = 2    # salt_composition and the short fields disagree; salt_composition is used
FLAG_UNCLEAR = 4     # the composition repeats one normalised ingredient (e.g. Paracetamol 300mg + Paracetamol 700mg)
MIN_PREFIX = 2
MIN_SIMILAR = 3
MAX_SIMILAR = 4
SIMILAR_WHEN_FEWER_THAN = 3
FUZZY_CUTOFF = 85    # rapidfuzz ratio, 0-100, against whole words
PREFIX_SCAN_CAP = 50_000

_ITEM = re.compile(r"^(?P<name>.*?)\s*\((?P<strength>[^()]*)\)\s*$")


def clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


# ---- composition ----------------------------------------------------------------------------
def parse_item(text: str) -> dict | None:
    """'Paracetamol (650mg)' -> name and strength. A strength of NA is kept as None (not stated).
    The strength is the LAST bracket, so 'Hepatitis B Vaccine (rDNA) (NA)' keeps '(rDNA)' in the name.
    None when the text is not 'name (strength)'."""
    t = clean(text)
    m = _ITEM.match(t)
    if not m or not m.group("name").strip():
        return None
    s = m.group("strength").strip()
    return {"name": m.group("name").strip(), "strength": None if s.upper() in ("NA", "") else s, "raw": t}


def split_salt(text: str | None) -> list[str]:
    return [clean(x) for x in (text or "").split("+") if x.strip()]


def composition_source(row: dict) -> tuple[list[str], list[str], int]:
    """(items used, short items, flags). salt_composition when present, otherwise the short fields."""
    short = [clean(row.get(c)) for c in SHORT_FIELDS if clean(row.get(c))]
    salt = split_salt(row.get("salt_composition"))
    flags = 0
    if not salt and len(short) >= 2:
        flags |= FLAG_INCOMPLETE
    if salt and (salt[:len(short)] != short or (len(salt) <= 2 and len(salt) != len(short))):
        flags |= FLAG_CONFLICT
    return (salt or short), short, flags


def ingredient_key(name: str) -> str:
    """Key used for alternatives: case, punctuation and spacing ignored, approved synonyms applied.
    Salt words are KEPT (metoprolol succinate is not metoprolol tartrate)."""
    return canonical(name)


def strength_key(strength: str | None) -> str | None:
    """Strengths are compared as written, ignoring case and spaces only ('100IU/ml' != '100IU')."""
    return None if strength is None else re.sub(r"\s+", "", strength.lower())


def parse_interactions(text: str | None) -> tuple[list[list[str]], bool]:
    """drug_interactions column -> [[drug, effect], ...]. The brand strings are dropped (they look
    cut off). Second value: False when the text is filled but not readable."""
    t = (text or "").strip()
    if not t or t == EMPTY_INTERACTIONS:
        return [], True
    try:
        j = json.loads(t)
    except ValueError:
        return [], False
    drugs, effects = j.get("drug") or [], j.get("effect") or []
    return [[clean(d), clean(e)] for d, e in zip(drugs, effects) if clean(d)], len(drugs) == len(effects)


# ---- linking to DailyMed --------------------------------------------------------------------
def _eff(label: dict) -> int:
    v = label.get("effective_time") or ""
    return int(v[:8]) if v[:8].isdigit() else 0


class LabelLinker:
    """Link a normalised ingredient key to DailyMed labels (names.json records).

    1. exact: a label's ingredient name, normalised with the same synonyms, equals the key;
    2. otherwise active moiety: the key's salt-stripped forms meet the label's ingredient or
       active moiety keys (medsafe.appms_match.ingredient_keys, which never reduces to a bare
       counter-ion such as 'sodium').
    Single-ingredient labels are used; combination labels only when no single-ingredient label
    exists (marked). Default label: most sections with text, then latest effective time, then set id."""

    def __init__(self, labels: list[dict]):
        self.labels = labels
        self._by_key: dict[str, list[int]] = defaultdict(list)
        self._by_ing: dict[str, list[int]] = defaultdict(list)
        for i, l in enumerate(labels):
            for k in label_keys(l):
                self._by_key[k].append(i)
            for x in {canonical(x) for x in l.get("ingredients", [])}:
                self._by_ing[x].append(i)

    def order(self, idxs: Iterable[int]) -> list[int]:
        L = self.labels
        return sorted(set(idxs), key=lambda i: (-len(L[i].get("sections", [])), -_eff(L[i]), L[i]["set_id"]))

    def link(self, key: str) -> dict:
        # labels with no section text cannot show anything, so they are never linked
        has_text = lambda i: bool(self.labels[i].get("sections"))
        exact = [i for i in self._by_ing.get(key, []) if has_text(i)]
        moiety = [i for i in sorted({i for k in ingredient_keys(key) for i in self._by_key.get(k, [])}) if has_text(i)]
        single = lambda idxs: [i for i in idxs if len(set(self.labels[i]["moieties"])) == 1]
        # single-ingredient labels first (exact name, then moiety); combination labels only if none
        method, chosen, combo = None, [], False
        for m, idxs, is_combo in (("ingredient name", single(exact), False), ("active moiety", single(moiety), False),
                                  ("ingredient name", exact, True), ("active moiety", moiety, True)):
            if idxs:
                method, chosen, combo = m, self.order(idxs), is_combo
                break
        return {"method": method, "label_idx": chosen, "combination_only": combo,
                "moieties": sorted({m for i in chosen for m in self.labels[i]["moieties"]})}


def _sentence(text: str) -> str:
    return text[:1] + text[1:].lower()


def label_record(l: dict) -> dict:
    """Name-index label -> the compact record kept in catalogue.json. The form families come from
    the SPL formCode and routeCode; with no form in the SPL they come from the title and
    form_inferred is True."""
    fams, inferred = classify_label(l.get("dosage_forms"), l.get("title"))
    pf = l.get("dosage_forms") or []
    forms = list(dict.fromkeys(_sentence(p["form"]) for p in pf))
    routes = list(dict.fromkeys(_sentence(r) for p in pf for r in p["routes"]))
    return {"title": l.get("title") or "", "product": l["products"][0] if l["products"] else "",
            "manufacturer": l["manufacturer"], "sections": len(l.get("sections", [])),
            "effective_time": l.get("effective_time"), "moieties": l["moieties"],
            "single": len(set(l["moieties"])) == 1,
            "forms": forms, "routes": routes, "families": fams, "form_inferred": inferred}


# ---- build --------------------------------------------------------------------------------
def build(rows: Iterable[dict], labels: list[dict], *, unparseable_sample: int = 20) -> tuple[dict, dict]:
    """Catalogue rows (dicts with the updated CSV's columns) + names.json labels -> (catalogue
    data, report). The data is columnar with interned strings to keep it small in memory."""
    interned: dict[str, dict[str, int]] = {"mfr": {}, "pack": {}, "type": {}, "form": {}}
    lists: dict[str, list[str]] = {"mfr": [], "pack": [], "type": [], "form": []}

    def intern(kind: str, v: str) -> int:
        d = interned[kind]
        if v not in d:
            d[v] = len(lists[kind])
            lists[kind].append(v)
        return d[v]

    comp_ix: dict[str, int] = {}
    comps: list[dict] = []
    ing_ix: dict[str, int] = {}
    ing_names: list[Counter] = []
    ing_rows: list[int] = []
    cols: dict[str, list] = {k: [] for k in ("id", "name", "mfr", "pack", "type", "form", "price", "disc", "comp", "flags")}
    short_text: dict[str, str] = {}
    secondary: dict[str, list] = {}
    rep = Counter()
    bad_items: list[tuple[str, str]] = []
    form_terms: Counter = Counter()
    form_where: Counter = Counter()

    for r in rows:
        used, short, flags = composition_source(r)
        items, ok = [], True
        for t in used:
            it = parse_item(t)
            if it is None:
                ok = False
                rep["unparseable_items"] += 1
                if len(bad_items) < unparseable_sample:
                    bad_items.append((r["id"], t))
                continue
            items.append(it)
        if not ok:
            rep["rows_with_unparseable_items"] += 1
        text = " + ".join(it["raw"] for it in items)
        c = comp_ix.get(text)
        if c is None:
            c = comp_ix[text] = len(comps)
            out = []
            for it in items:
                k = ingredient_key(it["name"])
                if k not in ing_ix:
                    ing_ix[k] = len(ing_names)
                    ing_names.append(Counter())
                    ing_rows.append(0)
                out.append([ing_ix[k], it["strength"], it["name"]])
            comps.append({"text": text, "items": out, "unclear": len({o[0] for o in out}) != len(out)})
        for ing, _, written in comps[c]["items"]:
            ing_names[ing][written] += 1
            ing_rows[ing] += 1
        price = float(r["price"]) if clean(r.get("price")) else 0.0
        cols["id"].append(r["id"])
        cols["name"].append(clean(r["name"]))
        cols["mfr"].append(intern("mfr", clean(r["manufacturer_name"])))
        cols["pack"].append(intern("pack", clean(r["pack_size_label"])))
        cols["type"].append(intern("type", clean(r["type"])))
        fam, term, where = classify_product(clean(r["name"]), clean(r["pack_size_label"]))
        cols["form"].append(intern("form", fam))
        form_terms[(fam, term)] += 1
        form_where[where] += 1
        if comps[c]["unclear"]:
            flags |= FLAG_UNCLEAR
        cols["price"].append(price if price > 0 else None)
        cols["disc"].append(1 if clean(r["Is_discontinued"]).upper() == "TRUE" else 0)
        cols["comp"].append(c)
        cols["flags"].append(flags)
        if flags & FLAG_CONFLICT:
            short_text[r["id"]] = " + ".join(short)
        pairs, readable = parse_interactions(r.get("drug_interactions"))
        if pairs:
            secondary[r["id"]] = pairs
        rep["interactions_unreadable"] += not readable
        rep["rows"] += 1
        rep["discontinued"] += cols["disc"][-1]
        rep["composition_incomplete"] += bool(flags & FLAG_INCOMPLETE)
        rep["composition_conflict"] += bool(flags & FLAG_CONFLICT)
        rep["composition_unclear"] += bool(flags & FLAG_UNCLEAR)
        rep["price_not_stated"] += price <= 0
        rep["from_salt_composition"] += bool(split_salt(r.get("salt_composition")))

    linker = LabelLinker(labels)
    used_labels: dict[str, dict] = {}
    ingredients = []
    for key, i in sorted(ing_ix.items(), key=lambda t: t[1]):
        ln = linker.link(key)
        set_ids = [labels[j]["set_id"] for j in ln["label_idx"]]
        for j in ln["label_idx"]:
            used_labels.setdefault(labels[j]["set_id"], label_record(labels[j]))
        name = ing_names[i].most_common(1)[0][0] if ing_names[i] else key
        ingredients.append({"key": key, "name": name, "us_name": key if key != norm(name) else None,
                            "rows": ing_rows[i], "link": {"method": ln["method"], "set_ids": set_ids,
                                                          "combination_only": ln["combination_only"],
                                                          "moieties": ln["moieties"]}})

    data = {"brands": cols, "manufacturers": lists["mfr"], "packs": lists["pack"], "types": lists["type"],
            "forms": lists["form"],
            "compositions": comps, "ingredients": ingredients, "labels": used_labels,
            "short_composition": short_text, "secondary_interactions": secondary}
    report = link_report(data)
    fam_count = Counter(lists["form"][f] for f in cols["form"])
    report["dosage_form"] = {
        "families": dict(fam_count.most_common()), "unknown_share": round(fam_count[UNKNOWN] / max(len(cols["form"]), 1), 4),
        "decided_by": {str(k): v for k, v in form_where.items()},
        "top_terms": [{"term": t, "family": f, "products": n} for (f, t), n in form_terms.most_common(21) if t][:20],
        "labels_by_family": dict(Counter(f for v in used_labels.values() for f in v["families"])),
        "labels_form_inferred": sum(1 for v in used_labels.values() if v["form_inferred"])}
    report.update({k: rep[k] for k in ("rows", "discontinued", "composition_incomplete", "composition_conflict", "composition_unclear",
                                       "price_not_stated", "from_salt_composition", "unparseable_items",
                                       "rows_with_unparseable_items", "interactions_unreadable")})
    report["unparseable_sample"] = bad_items
    report["secondary_interaction_rows"] = len(secondary)
    report["distinct_compositions"] = len(comps)
    report["dailymed_labels_loaded"] = len(labels)
    report["dailymed_labels_linked"] = len(used_labels)
    return data, report


def link_report(data: dict) -> dict:
    ings = [x for x in data["ingredients"] if x["rows"] > 0]
    linked = [x for x in ings if x["link"]["set_ids"]]
    comp_linked = [all(ings_by_ix(data, it[0])["link"]["set_ids"] for it in c["items"]) and bool(c["items"])
                   for c in data["compositions"]]
    b = data["brands"]
    tot = Counter()
    for c, f in zip(b["comp"], b["flags"]):
        grp = "incomplete" if f & (FLAG_INCOMPLETE | FLAG_CONFLICT | FLAG_UNCLEAR) else "complete"
        tot[grp] += 1
        tot[grp + "_all_linked"] += comp_linked[c]
    unl = sorted((x for x in ings if not x["link"]["set_ids"]), key=lambda x: (-x["rows"], x["key"]))
    n = len(b["id"])
    return {
        "distinct_ingredients": len(ings), "ingredients_linked": len(linked),
        "ingredients_linked_share": round(len(linked) / len(ings), 4) if ings else None,
        "ingredients_linked_by_method": dict(Counter(x["link"]["method"] for x in linked)),
        "ingredients_linked_combination_only": sum(x["link"]["combination_only"] for x in linked),
        "brands": n, "brands_all_linked": tot["complete_all_linked"] + tot["incomplete_all_linked"],
        "brands_all_linked_share": round((tot["complete_all_linked"] + tot["incomplete_all_linked"]) / n, 4) if n else None,
        "brands_complete": tot["complete"], "brands_complete_all_linked": tot["complete_all_linked"],
        "brands_flagged": tot["incomplete"], "brands_flagged_all_linked": tot["incomplete_all_linked"],
        "top_unlinked": [{"name": x["name"], "us_name": x["us_name"], "rows": x["rows"]} for x in unl[:30]],
    }


def ings_by_ix(data: dict, i: int) -> dict:
    return data["ingredients"][i]


# ---- runtime --------------------------------------------------------------------------------
class Catalogue:
    """Search, brand detail and alternatives over the data written by build()."""

    def __init__(self, data: dict):
        b = data["brands"]
        self.ids: list[str] = b["id"]
        self.names: list[str] = b["name"]
        self.mfr_ix: list[int] = b["mfr"]
        self.pack_ix: list[int] = b["pack"]
        self.type_ix: list[int] = b["type"]
        self.forms: list[str] = data.get("forms") or [UNKNOWN]   # dosage-form families (medsafe/forms.py)
        self.form_ix: list[int] = b.get("form") or [0] * len(self.ids)
        self.price: list[float | None] = b["price"]
        self.disc: list[int] = b["disc"]
        self.comp: list[int] = b["comp"]
        self.flags: list[int] = b["flags"]
        self.manufacturers, self.packs, self.types = data["manufacturers"], data["packs"], data["types"]
        self.comps = data["compositions"]
        self.ingredients = data["ingredients"]
        self.labels = data["labels"]
        self.short_composition = data.get("short_composition", {})
        self.secondary = data.get("secondary_interactions", {})
        self.meta = data.get("meta", {})
        n = len(self.ids)
        self.by_id = {x: i for i, x in enumerate(self.ids)}
        self.ing_by_key = {x["key"]: i for i, x in enumerate(self.ingredients)}

        keys = [norm(x) for x in self.names]
        order = sorted(range(n), key=keys.__getitem__)
        self._sorted_rows = order
        self._sorted_keys = [keys[i] for i in order]
        self._alpha = [0] * n
        for pos, i in enumerate(order):
            self._alpha[i] = pos
        self._first_word = [k.split(" ", 1)[0] for k in keys]
        words: dict[str, list[int]] = defaultdict(list)
        for i, k in enumerate(keys):
            for w in set(k.split()):
                words[w].append(i)
        self._words = dict(words)
        self._word_list = sorted(self._words)

        rows_by_comp: list[list[int]] = [[] for _ in self.comps]
        for i, c in enumerate(self.comp):
            rows_by_comp[c].append(i)
        self._rows_by_comp = rows_by_comp
        by_ing: list[list[int]] = [[] for _ in self.ingredients]
        for c, rows in enumerate(rows_by_comp):
            for ing in {it[0] for it in self.comps[c]["items"]}:
                by_ing[ing].extend(rows)
        self._ing_rows = [sorted(r, key=self._rank) for r in by_ing]
        # ingredient search terms: the name as written in the catalogue and its US name
        terms: dict[str, set[int]] = defaultdict(set)
        for i, x in enumerate(self.ingredients):
            for t in {norm(x["name"]), x["key"]}:
                if t:
                    terms[t].add(i)
        self._ing_terms = dict(terms)
        self._vocab = sorted(set(self._word_list) | set(self._ing_terms))

        self._set_key: list[tuple] = []
        self._str_key: list[tuple | None] = []
        by_set: dict[tuple, list[int]] = defaultdict(list)
        by_str: dict[tuple, list[int]] = defaultdict(list)
        for c, comp in enumerate(self.comps):
            sk = tuple(sorted({it[0] for it in comp["items"]}))
            st = [(it[0], strength_key(it[1])) for it in comp["items"]]
            tk = None if any(s is None for _, s in st) or not st else tuple(sorted(st))
            self._set_key.append(sk)
            self._str_key.append(tk)
            if sk:
                by_set[sk].append(c)
            if tk is not None:
                by_str[tk].append(c)
        self._by_set, self._by_str = dict(by_set), dict(by_str)

    # ---- helpers ------------------------------------------------------------------------
    def _rank(self, i: int) -> tuple:
        """Active before discontinued, fewer ingredients first, then alphabetical."""
        return (self.disc[i], len(self.comps[self.comp[i]]["items"]), self._alpha[i])

    def _look(self, i: int) -> tuple:
        return (self._sorted_keys[self._alpha[i]], self.mfr_ix[i], self.comp[i])

    def family(self, i: int) -> str:
        return self.forms[self.form_ix[i]]

    def unclear(self, i: int) -> bool:
        return bool(self.flags[i] & FLAG_UNCLEAR)

    def incomplete(self, i: int) -> bool:
        return bool(self.flags[i] & FLAG_INCOMPLETE)

    def conflict(self, i: int) -> bool:
        return bool(self.flags[i] & FLAG_CONFLICT)

    def ingredient_names(self, i: int) -> list[str]:
        return [it[2] for it in self.comps[self.comp[i]]["items"]]

    def row(self, i: int) -> dict:
        return {"id": self.ids[i], "name": self.names[i], "manufacturer": self.manufacturers[self.mfr_ix[i]] or None,
                "type": self.types[self.type_ix[i]], "pack_size": self.packs[self.pack_ix[i]], "price": self.price[i],
                "discontinued": bool(self.disc[i]), "composition": self.comps[self.comp[i]]["text"],
                "ingredients": self.ingredient_names(i), "composition_incomplete": self.incomplete(i),
                "composition_conflict": self.conflict(i), "composition_unclear": self.unclear(i),
                "form_family": self.family(i)}

    # ---- suggest ------------------------------------------------------------------------
    def suggest(self, q: str, limit: int = 8) -> tuple[list[dict], list[dict]]:
        """(matches, similar). matches: brand name starts with the query (2+ characters), then a
        later word of the name starts with it, then an ingredient name starts with it.
        similar: only when matches has fewer than 3, the query has 3+ characters: the query inside
        a word, then typo matches; at most 4, never mixed into matches."""
        qn = norm(q)
        if len(qn) < MIN_PREFIX:
            return [], []
        cand: list[tuple] = []  # (disc, tier, inner..., row, match, matched_text)
        # tier 0: name prefix
        j = bisect_left(self._sorted_keys, qn)
        tier0 = []
        while j < len(self._sorted_keys) and self._sorted_keys[j].startswith(qn) and len(tier0) < PREFIX_SCAN_CAP:
            i = self._sorted_rows[j]
            tier0.append(i)
            j += 1
        taken = set(tier0)
        for i in heapq.nsmallest(limit * 3, tier0, key=lambda i: (self.disc[i], self._first_word[i] != qn, self._alpha[i])):
            cand.append(((self.disc[i], 0, self._first_word[i] != qn, self._alpha[i]), i, "prefix", None))
        # tier 1: a later word of the name starts with the query
        tier1 = []
        j = bisect_left(self._word_list, qn)
        while j < len(self._word_list) and self._word_list[j].startswith(qn):
            w = self._word_list[j]
            tier1.extend((i, w) for i in self._words[w] if i not in taken)
            j += 1
        best1 = {}
        for i, w in tier1:
            best1[i] = min(best1.get(i, w), w, key=lambda x: (x != qn, x))
        taken |= best1.keys()
        for i in heapq.nsmallest(limit * 3, best1, key=lambda i: (self.disc[i], best1[i] != qn, self._alpha[i])):
            cand.append(((self.disc[i], 1, best1[i] != qn, self._alpha[i]), i, "word", None))
        # tier 2: an ingredient name (as written or its US name) starts with the query
        for t, ings in self._ing_terms.items():
            if not (t.startswith(qn) or f" {qn}" in f" {t}"):
                continue
            for ing in ings:
                got = 0
                for i in self._ing_rows[ing]:
                    if i in taken:
                        continue
                    cand.append(((self.disc[i], 2, t != qn, len(self.comps[self.comp[i]]["items"]), self._alpha[i]),
                                 i, "ingredient", self.ingredients[ing]["name"]))
                    got += 1
                    if got >= limit * 3:
                        break
        matches = self._finish(cand, limit)
        similar: list[dict] = []
        if len(matches) < SIMILAR_WHEN_FEWER_THAN and len(qn) >= MIN_SIMILAR:
            similar = self._similar(qn, {m["id"] for m in matches}, MAX_SIMILAR)
        return matches, similar

    def _finish(self, cand: list[tuple], limit: int) -> list[dict]:
        cand.sort(key=lambda c: c[0])
        out, seen_rows, seen_look = [], set(), set()
        for _, i, how, txt in cand:
            look = self._look(i)
            if i in seen_rows or look in seen_look:
                continue
            seen_rows.add(i)
            seen_look.add(look)
            out.append({**self.row(i), "match": how, "matched_ingredient": txt})
            if len(out) >= limit:
                break
        return out

    def _similar(self, qn: str, exclude: set[str], cap: int) -> list[dict]:
        cand: list[tuple] = []
        sub = [w for w in self._vocab if qn in w and not any(x.startswith(qn) for x in w.split())]
        if process is not None:
            found = process.extract(qn, self._vocab, scorer=fuzz.ratio, score_cutoff=FUZZY_CUTOFF, limit=8)
            fz = [(w, s) for w, s, _ in found]
        else:  # pragma: no cover
            fz = [(w, 100.0) for w in difflib.get_close_matches(qn, self._vocab, n=8, cutoff=FUZZY_CUTOFF / 100)]
        fz = [(w, s) for w, s in fz if w not in sub and not w.startswith(qn)]
        for tier, hits in ((0, [(w, 100.0) for w in sub]), (1, fz)):
            for w, score in hits:
                for ing in sorted(self._ing_terms.get(w, ())):
                    for i in self._ing_rows[ing][:cap]:
                        cand.append(((self.disc[i], tier, -score, 1, self._rank(i)), i,
                                     "substring" if tier == 0 else "fuzzy", self.ingredients[ing]["name"]))
                rows = self._words.get(w, ())
                for i in heapq.nsmallest(cap, rows, key=self._rank):
                    cand.append(((self.disc[i], tier, -score, 0, self._rank(i)), i,  # name hits first
                                 "substring" if tier == 0 else "fuzzy", None))
        cand = [c for c in cand if self.ids[c[1]] not in exclude]
        return self._finish(cand, cap)

    # ---- brand detail -------------------------------------------------------------------
    @staticmethod
    def _few(items: list[str]) -> str | None:
        return (", ".join(items[:2]) + (" + more" if len(items) > 2 else "")) or None

    def label_ref(self, set_id: str, default: bool) -> dict:
        l = self.labels.get(set_id, {})
        return {"set_id": set_id, "title": l.get("title", ""), "product": l.get("product", ""),
                "manufacturer": l.get("manufacturer"), "sections": l.get("sections", 0),
                "effective_time": l.get("effective_time"), "single_ingredient": l.get("single", True),
                "form": self._few(l.get("forms", [])), "route": self._few(l.get("routes", [])),
                "form_family": " / ".join(l.get("families") or [UNKNOWN]),
                "form_inferred": bool(l.get("form_inferred", False)), "default": default}

    def ordered_labels(self, set_ids: list[str], family: str) -> tuple[list[str], str]:
        """The ingredient's label ids with the default first, and how the form matched.
        Default: the first label (most sections, latest, set id) whose form families include the
        brand's family; else the first label as before. Match is 'matched', 'none',
        'brand_form_unknown' or 'no_label'."""
        if not set_ids:
            return [], "no_label"
        if family == UNKNOWN:
            return list(set_ids), "brand_form_unknown"
        hit = next((k for k, s in enumerate(set_ids) if family in (self.labels.get(s, {}).get("families") or ())), None)
        if hit is None:
            return list(set_ids), "none"
        return [set_ids[hit]] + [s for k, s in enumerate(set_ids) if k != hit], "matched"

    def ingredient_info(self, ing: int, strength: str | None, written: str, family: str = UNKNOWN) -> dict:
        x = self.ingredients[ing]
        ln = x["link"]
        ids, match = self.ordered_labels(ln["set_ids"], family)
        return {"name": written, "strength": strength, "key": x["key"], "us_name": x["us_name"],
                "link_method": ln["method"], "combination_only": ln["combination_only"],
                "moieties": ln["moieties"], "form_match": match,
                "labels": [self.label_ref(s, k == 0) for k, s in enumerate(ids)]}

    def detail(self, i: int) -> dict:
        fam = self.family(i)
        return {**self.row(i),
                "ingredient_details": [self.ingredient_info(ing, st, w, fam) for ing, st, w in self.comps[self.comp[i]]["items"]],
                "short_composition": self.short_composition.get(self.ids[i]),
                "secondary_interactions": [{"drug": d, "effect": e} for d, e in self.secondary.get(self.ids[i], [])]}

    # ---- alternatives -------------------------------------------------------------------
    def _alt_row(self, i: int, sel: int) -> dict:
        p, ps = self.price[i], self.price[sel]
        return {**self.row(i), "price_difference": None if p is None or ps is None else round(p - ps, 2),
                "different_pack_size": self.pack_ix[i] != self.pack_ix[sel]}

    def _collect(self, comps: Iterable[int], sel: int, include_discontinued: bool) -> list[int]:
        out, seen = [], {self._look(sel) + (self.pack_ix[sel],)}
        for c in comps:
            for i in self._rows_by_comp[c]:
                if i == sel or (self.disc[i] and not include_discontinued):
                    continue
                look = self._look(i) + (self.pack_ix[i],)
                if look in seen:  # identical name, manufacturer, pack and composition
                    continue
                seen.add(look)
                out.append(i)
        return out

    def _by_price(self, rows: list[int]) -> list[int]:
        return sorted(rows, key=lambda i: (self.price[i] is None, self.price[i] or 0, self.disc[i], self._alpha[i]))

    def alternatives(self, sel: int, include_discontinued: bool = False, limit: int = 100,
                     group_limit: int = 5) -> dict:
        """Other brands with the same full ingredient set AND the same strengths, cheapest first, split
        by dosage-form family: `same` (the selected product's family), `different_form` (another known
        family) and `form_not_stated` (family unknown). `same` is empty when the selected product's own
        form is unknown. Separately, the same ingredient set at other strengths in the same family.
        Combinations match only on the full set. A product whose strength is not stated is never in
        the same-strength groups."""
        c = self.comp[sel]
        fam = self.family(sel)
        sk, tk = self._set_key[c], self._str_key[c]
        same_comps = self._by_str.get(tk, []) if tk is not None else []
        # a product whose composition repeats an ingredient is never a match, and has no matches: it is only
        # listed apart, under the products with the same ingredient set
        sel_unclear = self.unclear(sel)
        pool = [] if sel_unclear else [i for i in self._by_price(self._collect(same_comps, sel, include_discontinued))
                                       if not self.unclear(i)]
        same = [i for i in pool if fam != UNKNOWN and self.family(i) == fam]
        diff = [i for i in pool if self.family(i) not in (fam, UNKNOWN)]
        unknown = [i for i in pool if self.family(i) == UNKNOWN]
        other_comps = [x for x in self._by_set.get(sk, []) if tk is None or self._str_key[x] != tk]
        groups: dict = defaultdict(list)
        hidden = 0
        for i in ([] if sel_unclear else self._collect(other_comps, sel, include_discontinued)):
            if self.unclear(i):
                continue
            if self.family(i) != fam:
                hidden += 1
                continue
            k = self._str_key[self.comp[i]]
            groups[k if k is not None else ("comp", self.comp[i])].append(i)
        other = []
        for rows in groups.values():
            rows = self._by_price(rows)
            other.append({"composition": self.comps[self.comp[rows[0]]]["text"], "brands_total": len(rows),
                          "lowest_price": next((self.price[i] for i in rows if self.price[i] is not None), None),
                          "strength_stated": self._str_key[self.comp[rows[0]]] is not None,
                          "brands": [self._alt_row(i, sel) for i in rows[:group_limit]]})
        other.sort(key=lambda g: (-g["brands_total"], g["composition"]))
        unclear = self._by_price([i for i in self._collect(self._by_set.get(sk, []), sel, include_discontinued)
                                  if self.unclear(i)])
        return {"strength_stated": tk is not None, "form_family": fam, "composition_unclear": sel_unclear,
                "same_total": len(same),
                "same": [self._alt_row(i, sel) for i in same[:limit]],
                "different_form_total": len(diff), "different_form": [self._alt_row(i, sel) for i in diff[:limit]],
                "form_not_stated_total": len(unknown),
                "form_not_stated": [self._alt_row(i, sel) for i in unknown[:limit]],
                "other_strength_groups_total": len(other), "other_strength": other[:20],
                "other_strength_other_form_hidden": hidden,
                "unclear_total": len(unclear), "unclear": [self._alt_row(i, sel) for i in unclear[:limit]],
                "flagged_in_same": sum(1 for i in same if self.flags[i] & (FLAG_INCOMPLETE | FLAG_CONFLICT))}
