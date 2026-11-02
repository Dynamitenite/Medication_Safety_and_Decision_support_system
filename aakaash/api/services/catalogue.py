# SOURCE: NOT IN PAPERS. Serves artifacts/catalogue.json (scripts/build_catalogue.py): the Indian
# medicine catalogue, its alternatives and the checker over ingredient sets. Missing data gives
# status="not_ready"; nothing is invented. The interaction rules alone set the severity; the
# catalogue's own interaction lists are a separate, labelled secondary source.
"""Brand search, brand page, alternatives, catalogue summary and the interaction checker."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from fastapi import HTTPException

from medsafe import appms as appms_data
from medsafe.appms_match import ingredient_keys
from medsafe.catalogue import FUZZY_BACKEND, Catalogue, LabelLinker
from medsafe.names import mentions, norm, pairs
from medsafe.synonyms import canonical, read_rows

from ..config import Settings
from ..schemas import (AlternativeBrand, AppmsResult, BrandAlternativesResponse, BrandResponse, BrandRow,
                       BrandSuggestion, CatalogueSummaryResponse, CheckerIngredient, CheckerMedicine,
                       CheckerResponse, IngredientDetail, PairResult, RuleHit, SecondaryHit, SecondaryInteraction,
                       SecondaryResult, StrengthGroup, SuggestResponse, SynonymRow, TextMatch, TextMatchResult,
                       UnlinkedIngredient)
from . import appms as appms_service
from . import medicines

CATALOGUE_FILE = "catalogue.json"
PRICE_NOTE = "Prices may be out of date."
LABEL_NOTE = ("This brand itself is not in the US FDA label source. The text shown is from a US label for the same "
              "ingredient; strength, formulation and advice can differ from this brand.")
DEFAULT_LABEL_RULE = ("When several US labels exist for an ingredient, the one with the most label sections is shown "
                      "first (ties: the most recent label, then the label id). Labels for single-ingredient products "
                      "are used; a combination-product label is used only when there is no single-ingredient label.")
ALT_NOTE = "Same ingredients and strength. Not necessarily interchangeable. Confirm with a pharmacist."
INCOMPLETE_NOTE = ("Composition may be incomplete: the catalogue lists only two ingredients for this product, and "
                   "it may contain more.")
CONFLICT_NOTE = "The catalogue gives two different compositions for this product; the fuller one is used."
SECONDARY_LABEL = "Indian product information (origin not stated). Not used for the risk level."
TEXT_MATCH_LABEL = ("Sentences in the Drug Interactions section of each ingredient's US label that name an "
                    "ingredient of the other medicine. Class-level mentions (for example 'anticoagulants') are "
                    "not detected.")
RULES_LABEL = "Interaction rules"
SEV_RANK = {"Critical": 0, "High": 1, "Moderate": 2}
MAX_MATCHES_PER_PAIR = 12

_lock = threading.Lock()
_cache: dict[str, Catalogue] = {}
_linkers: dict[int, LabelLinker] = {}


def clear_cache() -> None:
    with _lock:
        _cache.clear()
        _linkers.clear()


def catalogue_path(settings: Settings) -> Path:
    return settings.artifacts_dir / CATALOGUE_FILE


def get_catalogue(settings: Settings) -> Catalogue | None:
    """Load catalogue.json once per process (on first request). None if the file is missing."""
    path = catalogue_path(settings)
    if not path.is_file():
        return None
    key = f"{path.resolve()}|{path.stat().st_mtime_ns}"
    with _lock:
        if key not in _cache:
            _cache.clear()
            _cache[key] = Catalogue(json.loads(path.read_text(encoding="utf-8")))
        return _cache[key]


def _not_ready(cls, settings: Settings, **kw):
    return cls(status="not_ready",
               reason=f"The medicine catalogue {settings.display(catalogue_path(settings))} is missing.",
               fix="Run scripts/build_catalogue.py from the aakaash folder.", **kw)


def _row(cat: Catalogue, cid: str) -> int:
    i = cat.by_id.get(cid)
    if i is None:
        raise HTTPException(404, f"No medicine with id {cid}.")
    return i


def suggest(settings: Settings, q: str, limit: int) -> SuggestResponse:
    cat = get_catalogue(settings)
    if cat is None:
        return _not_ready(SuggestResponse, settings, query=q)
    t0 = time.perf_counter()
    matches, similar = cat.suggest(q, limit)
    ms = (time.perf_counter() - t0) * 1000
    return SuggestResponse(status="ready", query=q, matcher=FUZZY_BACKEND, elapsed_ms=round(ms, 2),
                           matches=[BrandSuggestion(**m) for m in matches],
                           similar=[BrandSuggestion(**m) for m in similar])


def brand(settings: Settings, cid: str) -> BrandResponse:
    cat = get_catalogue(settings)
    if cat is None:
        return _not_ready(BrandResponse, settings)
    d = cat.detail(_row(cat, cid))
    return BrandResponse(
        status="ready", brand=BrandRow(**{k: d[k] for k in BrandRow.model_fields}),
        ingredient_details=[IngredientDetail(**x) for x in d["ingredient_details"]],
        short_composition=d["short_composition"], secondary_source_label=SECONDARY_LABEL,
        secondary_interactions=[SecondaryInteraction(**x) for x in d["secondary_interactions"]],
        price_note=PRICE_NOTE, label_note=LABEL_NOTE, default_label_rule=DEFAULT_LABEL_RULE)


def alternatives(settings: Settings, cid: str, include_discontinued: bool, limit: int) -> BrandAlternativesResponse:
    cat = get_catalogue(settings)
    if cat is None:
        return _not_ready(BrandAlternativesResponse, settings, id=cid)
    i = _row(cat, cid)
    a = cat.alternatives(i, include_discontinued, limit)
    caveats = []
    if cat.incomplete(i):
        caveats.append(INCOMPLETE_NOTE + " The brands below share the listed ingredients and strengths only.")
    if cat.conflict(i):
        caveats.append(CONFLICT_NOTE + " Treat the match as unconfirmed.")
    if not a["strength_stated"]:
        caveats.append("The strength of this product is not stated, so no brand can be matched on strength.")
    if a["flagged_in_same"]:
        caveats.append("Brands marked “composition may be incomplete” list only two ingredients and may contain more.")
    return BrandAlternativesResponse(
        status="ready", id=cid, note=ALT_NOTE, price_note=PRICE_NOTE, caveats=caveats,
        strength_stated=a["strength_stated"], include_discontinued=include_discontinued,
        same_total=a["same_total"], same=[AlternativeBrand(**x) for x in a["same"]],
        other_strength_groups_total=a["other_strength_groups_total"],
        other_strength=[StrengthGroup(**{**g, "brands": [AlternativeBrand(**x) for x in g["brands"]]})
                        for g in a["other_strength"]])


def summary(settings: Settings) -> CatalogueSummaryResponse:
    cat = get_catalogue(settings)
    if cat is None:
        return _not_ready(CatalogueSummaryResponse, settings)
    m, r = cat.meta, cat.meta.get("report", {})
    return CatalogueSummaryResponse(
        status="ready", source=m.get("source", ""), licence=m.get("licence", ""),
        original_source=m.get("original_source", ""), file_date=m.get("file_date"), built_at=m.get("built_at"),
        brands=r.get("rows", 0), discontinued=r.get("discontinued", 0),
        composition_incomplete=r.get("composition_incomplete", 0), composition_conflict=r.get("composition_conflict", 0),
        from_full_composition=r.get("from_salt_composition", 0), price_not_stated=r.get("price_not_stated", 0),
        distinct_ingredients=r.get("distinct_ingredients", 0), ingredients_linked=r.get("ingredients_linked", 0),
        ingredients_linked_combination_only=r.get("ingredients_linked_combination_only", 0),
        brands_all_linked=r.get("brands_all_linked", 0), brands_complete=r.get("brands_complete", 0),
        brands_complete_all_linked=r.get("brands_complete_all_linked", 0),
        secondary_interaction_rows=r.get("secondary_interaction_rows", 0),
        dailymed_parts_loaded=m.get("dailymed_parts_loaded", []), dailymed_labels_loaded=r.get("dailymed_labels_loaded", 0),
        top_unlinked=[UnlinkedIngredient(**x) for x in r.get("top_unlinked", [])],
        synonyms=[SynonymRow(**x) for x in read_rows()])


# ---- checker --------------------------------------------------------------------------------
class _Ing:
    """One ingredient of a checked medicine, with its reference US label."""

    def __init__(self, name: str, key: str, us_name: str | None, set_ids: list[str], moieties: list[str],
                 label_name: str | None, combination_only: bool = False):
        self.name, self.key, self.us_name = name, key, us_name
        self.ref = set_ids[0] if set_ids else None
        self.label_name = label_name
        # a combination label's moieties include the OTHER ingredients, so they are never search terms
        self.terms = sorted(ingredient_keys(name, key, *([] if combination_only else moieties)))


class _Med:
    def __init__(self, out: CheckerMedicine, ings: list[_Ing], row: int | None):
        self.out, self.ings, self.row = out, ings, row


def _linker(idx) -> LabelLinker:
    with _lock:
        lk = _linkers.get(id(idx))
        if lk is None:
            _linkers.clear()
            lk = _linkers[id(idx)] = LabelLinker(idx.labels)
        return lk


def _label_name(cat: Catalogue, set_id: str) -> str:
    l = cat.labels.get(set_id, {})
    return l.get("product") or l.get("title") or set_id


def _brand_med(cat: Catalogue, cid: str) -> _Med:
    i = _row(cat, cid)
    ings = []
    for ing, _, written in cat.comps[cat.comp[i]]["items"]:
        x = cat.ingredients[ing]
        ids = x["link"]["set_ids"]
        ings.append(_Ing(written, x["key"], x["us_name"], ids, x["link"]["moieties"],
                         _label_name(cat, ids[0]) if ids else None, x["link"]["combination_only"]))
    out = CheckerMedicine(key=cid, catalogue_id=cid, name=cat.names[i],
                          manufacturer=cat.manufacturers[cat.mfr_ix[i]] or None, kind="brand",
                          ingredients=[CheckerIngredient(name=g.name, us_name=g.us_name, label_set_id=g.ref,
                                                         label_name=g.label_name) for g in ings],
                          composition_incomplete=cat.incomplete(i) or cat.conflict(i))
    return _Med(out, ings, i)


def _generic_med(cat: Catalogue, idx, name: str) -> _Med:
    key = canonical(name)
    j = cat.ing_by_key.get(key)
    if j is not None:
        x = cat.ingredients[j]
        ids, moi, combo = x["link"]["set_ids"], x["link"]["moieties"], x["link"]["combination_only"]
        lname = _label_name(cat, ids[0]) if ids else None
    elif idx is not None:
        ln = _linker(idx).link(key)
        ids = [idx.labels[k]["set_id"] for k in ln["label_idx"]]
        moi, combo = ln["moieties"], ln["combination_only"]
        first = idx.labels[ln["label_idx"][0]] if ids else None
        lname = (first["products"][0] if first["products"] else first.get("title")) if first else None
    else:
        ids, moi, lname, combo = [], [], None, False
    g = _Ing(name, key, key if key != norm(name) else None, ids, moi, lname, combo)
    out = CheckerMedicine(key=f"name:{norm(name)}", catalogue_id=None, name=name, manufacturer=None, kind="generic",
                          ingredients=[CheckerIngredient(name=g.name, us_name=g.us_name, label_set_id=g.ref,
                                                         label_name=g.label_name)],
                          composition_incomplete=False)
    return _Med(out, [g], None)


def _rules(data, a: _Med, b: _Med) -> AppmsResult:
    if data is None:
        return AppmsResult(status="not_ready", source_label=RULES_LABEL,
                           reason="The interaction rules are not loaded.", fix=appms_service.FIX)
    hits, seen = [], set()
    for x in a.ings:
        for y in b.ings:
            for kx in ingredient_keys(x.name, x.key):
                for ky in ingredient_keys(y.name, y.key):
                    r = appms_data.find_rule(data, kx, ky)
                    if r and (x.name, y.name, r.drug_a, r.drug_b) not in seen:
                        seen.add((x.name, y.name, r.drug_a, r.drug_b))
                        hits.append((SEV_RANK[r.severity], RuleHit(
                            a_ingredient=x.name, b_ingredient=y.name, severity=r.severity.lower(),
                            explanation=f"{r.interaction_category}. {r.mechanism_or_risk}. {r.explanation_or_action}.")))
    if not hits:
        return AppmsResult(status="ready", source_label=RULES_LABEL)
    hits.sort(key=lambda h: h[0])
    top = hits[0][1]
    return AppmsResult(status="ready", source_label=RULES_LABEL, severity=top.severity, explanation=top.explanation,
                       hits=[h for _, h in hits])


def _text(settings: Settings, idx, a: _Med, b: _Med) -> TextMatchResult:
    found, notes = [], []
    for src, tgt in ((a, b), (b, a)):
        for g in src.ings:
            if g.ref is None:
                notes.append(f"{g.name} ({src.out.name}) has no linked US label, so its label text was not checked.")
                continue
            if idx is None:
                notes.append("Label text is not available on this server.")
                continue
            try:
                lab = medicines.load_label(settings, idx, g.ref)
            except HTTPException:
                notes.append(f"The US label for {g.name} could not be read on this server.")
                continue
            text = "\n".join(s["text"] for s in lab["sections"].get("drug_interactions", []))
            if not text:
                notes.append(f"The US label used for {g.name} has no Drug Interactions section in the parsed text.")
                continue
            for t in tgt.ings:
                for m in mentions(text, {"products": [], "moieties": t.terms}):
                    found.append(TextMatch(sentence=m["sentence"], matched_term=m["matched_term"],
                                           in_label_set_id=g.ref, in_label_name=g.label_name or g.ref,
                                           section="Drug interactions", names_drug=tgt.out.name,
                                           source_ingredient=g.name, named_ingredient=t.name))
    return TextMatchResult(source_label=TEXT_MATCH_LABEL, matches=found[:MAX_MATCHES_PER_PAIR],
                           matches_total=len(found), notes=list(dict.fromkeys(notes)))


def _secondary(cat: Catalogue, a: _Med, b: _Med) -> SecondaryResult:
    hits = []
    for src, tgt in ((a, b), (b, a)):
        if src.row is None:
            continue
        for drug, effect in cat.secondary.get(cat.ids[src.row], []):
            dk = ingredient_keys(drug)
            for t in tgt.ings:
                if dk & ingredient_keys(t.name, t.key):
                    hits.append(SecondaryHit(in_product=src.out.name, drug=drug, effect=effect, matches_ingredient=t.name))
    return SecondaryResult(source_label=SECONDARY_LABEL, hits=hits)


def check(settings: Settings, catalogue_ids: list[str], names: list[str] | None = None) -> CheckerResponse:
    names = [n.strip() for n in (names or []) if n.strip()]
    if len(set(catalogue_ids)) != len(catalogue_ids) or len({canonical(n) for n in names}) != len(names):
        raise HTTPException(422, "Each medicine can be added only once.")
    if len(catalogue_ids) + len(names) < 2:
        raise HTTPException(422, "Add at least 2 medicines.")
    cat = get_catalogue(settings)
    if cat is None:
        return _not_ready(CheckerResponse, settings)
    idx = medicines.get_index(settings)
    meds = [_brand_med(cat, c) for c in catalogue_ids] + [_generic_med(cat, idx, n) for n in names]
    rules = appms_service.get_data(settings)
    rules_status = (AppmsResult(status="ready", source_label=RULES_LABEL) if rules is not None
                    else _rules(None, meds[0], meds[1]))
    out = []
    for x, y in pairs(list(range(len(meds)))):
        a, b = meds[x], meds[y]
        shared = sorted({g.name for g in a.ings for h in b.ings if g.key == h.key})
        notes = [f"{m.out.name}: {INCOMPLETE_NOTE}" for m in (a, b) if m.out.composition_incomplete]
        out.append(PairResult(a=a.out, b=b.out, appms=_rules(rules, a, b), text_match=_text(settings, idx, a, b),
                              shared_ingredients=shared, secondary=_secondary(cat, a, b), notes=notes))
    # rule severity first (Critical, High, Moderate, unflagged); then more text matches first
    rank = {"critical": 0, "high": 1, "moderate": 2, None: 3}
    out.sort(key=lambda p: (rank[p.appms.severity], -p.text_match.matches_total))
    return CheckerResponse(status="ready", medicines=[m.out for m in meds], appms=rules_status, pairs=out)
