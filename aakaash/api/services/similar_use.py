# SOURCE: NOT IN PAPERS. Own method (task spec): cosine similarity between Indications passages of US
# labels, taking the maximum per ingredient. The cosine is P1/P2/P3's similarity measure; using it to
# suggest "medicines with similar uses" is not in the papers. Similar uses do not mean interchangeable.
"""GET /api/medicine/{id}/similar-use. Missing index or catalogue gives status="not_ready"."""
from __future__ import annotations

import re
import threading
from collections import defaultdict

import numpy as np

from medsafe.index import Index, split_sentences

from ..config import Settings
from ..schemas import (SimilarBrand, SimilarLabelRef, SimilarUseGroup, SimilarUseResponse, SimilarUseSuggestion)
from . import catalogue, retrieval

HEADING = "Medicines with similar uses"
NOTE = ("Found by comparing the uses listed on US labels. Similar uses do not mean the medicines are interchangeable, "
        "and this is not advice to switch. Ask your doctor or pharmacist.")
COMBINATION_NOTE = "This medicine has {n} ingredients. Each one is compared on its own."
GENERIC_MIN_INGREDIENTS = 5  # approved: flag a supporting sentence carried by this many ingredients or more (flag only, never hides)
GENERIC_NOTE = ("Generic wording: this sentence appears in the uses listed for {n} ingredients, so the match may reflect "
                "shared wording rather than a shared use.")
MAX_SENTENCE_WORDS = 60  # a longer run (label lists lose their line breaks in the chunks) is cut and marked with an ellipsis
MIN_SENTENCE_WORDS = 5  # shorter lines (headings such as "1 INDICATIONS AND USAGE") are not shown as the supporting sentence
NO_BRANDS_NOTE = "No brand of the same dosage form is listed in the catalogue."
UNKNOWN_FORM_NOTE = "The dosage form of the selected medicine is not known, so no brands are matched."

_lock = threading.Lock()
_pool: dict = {}


def _norm(sentence: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", sentence.lower()).strip()


def carrier_count(sentence: str) -> int:
    """How many ingredients' Indications text contains this sentence (call after _candidates)."""
    return _pool.get("carriers", {}).get(_norm(sentence), 0)


def _candidates(cat, idx: Index):
    """Per catalogue ingredient with US single-ingredient labels: its Indications chunks. Built once
    per (catalogue, index). Returns (ingredients, chunk array, bounds)."""
    key = (id(cat), id(idx))
    with _lock:
        if _pool.get("key") == key:
            return _pool["val"]
        ind = idx.chunks_of_section("indications")
        by_label: dict[int, list[int]] = {}
        for c in ind:
            by_label.setdefault(int(idx.chunk_label[c]), []).append(int(c))
        ings, chunks, bounds = [], [], [0]
        for j, x in enumerate(cat.ingredients):
            ln = x["link"]
            if ln["combination_only"] or not ln["set_ids"]:
                continue
            cs = [c for s in ln["set_ids"] if s in idx.label_by_id for c in by_label.get(idx.label_by_id[s], [])]
            if cs:
                ings.append(j)
                chunks += cs
                bounds.append(len(chunks))
        arr = np.asarray(chunks, dtype=np.int64)
        carriers: dict[str, set[int]] = defaultdict(set)
        for n, j in enumerate(ings):
            for c in arr[bounds[n]:bounds[n + 1]]:
                for sent in split_sentences(idx.text(int(c))):
                    if len(sent.split()) >= MIN_SENTENCE_WORDS:
                        carriers[_norm(sent)].add(j)
        _pool.clear()
        _pool.update(key=key, val=(ings, arr, np.asarray(bounds)), carriers={k: len(v) for k, v in carriers.items()})
        return _pool["val"]


def _query_chunks(cat, idx: Index, ing: int) -> tuple[np.ndarray, int, bool]:
    ln = cat.ingredients[ing]["link"]
    ids = [s for s in ln["set_ids"] if s in idx.label_by_id]
    cs = idx.chunks_of_labels(ids)
    cs = cs[idx.chunk_section[cs] == idx.sections.index("indications")] if len(cs) and "indications" in idx.sections else cs[:0]
    return cs, len(ids), bool(ln["combination_only"])


def _best_sentence(idx: Index, text: str, reference: str) -> tuple[str, str]:
    """(sentence as shown, full sentence). The shown one is cut at MAX_SENTENCE_WORDS."""
    sents = [s for s in split_sentences(text) if len(s.split()) >= MIN_SENTENCE_WORDS] or split_sentences(text)
    if not sents:
        return text[:300], text
    cos = idx.text_cosines(reference, sents)
    k = int(np.argmax(cos))
    words = sents[k].split()
    return (" ".join(words[:MAX_SENTENCE_WORDS]) + " …" if len(words) > MAX_SENTENCE_WORDS else sents[k]), sents[k]


def rank(S: np.ndarray, bounds: np.ndarray, excluded: set[int], ings: list[int], moieties: dict[int, frozenset],
         min_sim: float | None, limit: int) -> list[dict]:
    """Aggregate a (query chunks x candidate chunks) cosine matrix per ingredient. Pure numpy, tested
    on hand-written matrices. Score = maximum over all pairs; supporting = candidate chunks at or above
    min_sim (None when no minimum is set). Skips excluded ingredients, and keeps one ingredient per
    set of US active moieties (the best scoring)."""
    colmax = S.max(axis=0)
    out, seen_moi = [], set()
    for n, j in enumerate(ings):
        if j in excluded:
            continue
        sl = slice(int(bounds[n]), int(bounds[n + 1]))
        part = colmax[sl]
        best = int(np.argmax(part)) + sl.start
        out.append({"ing": j, "score": float(part.max()), "col": best, "row": int(np.argmax(S[:, best])),
                    "support": None if min_sim is None else int((part >= min_sim).sum())})
    out.sort(key=lambda r: (-r["score"], r["ing"]))
    kept = []
    for r in out:
        mo = moieties.get(r["ing"]) or frozenset({r["ing"]})
        if mo in seen_moi:
            continue
        seen_moi.add(mo)
        kept.append(r)
        if len(kept) >= limit:
            break
    return kept


def similar_use(settings: Settings, cid: str, limit: int) -> SimilarUseResponse:
    cat = catalogue.get_catalogue(settings)
    if cat is None:
        return catalogue._not_ready(SimilarUseResponse, settings, id=cid)
    idx, why = retrieval.get_index(settings)
    if idx is None:
        return retrieval._not_ready(SimilarUseResponse, why, id=cid)
    i = catalogue._row(cat, cid)
    fam = cat.family(i)
    own = list(dict.fromkeys(ing for ing, _, _ in cat.comps[cat.comp[i]]["items"]))
    own_moi = {m for ing in own for m in cat.ingredients[ing]["link"]["moieties"]}
    ings, chunks, bounds = _candidates(cat, idx)
    moi = {j: frozenset(cat.ingredients[j]["link"]["moieties"]) for j in ings}
    own_keys = {cat.ingredients[o]["key"] for o in own}
    excluded = set(own) | {j for j in ings if cat.ingredients[j]["key"] in own_keys or (moi[j] & own_moi)}
    groups = []
    for ing in own:
        x = cat.ingredients[ing]
        q, n_labels, from_combo = _query_chunks(cat, idx, ing)
        name = x["name"]
        if len(q) == 0:
            groups.append(SimilarUseGroup(
                ingredient=name, query_labels=n_labels, query_passages=0,
                note="No Indications text from a US label is loaded for this ingredient, so nothing can be compared."))
            continue
        S = idx.pair_similarity(q, chunks)
        ranked = rank(S, bounds, excluded, ings, moi, settings.similar_use_min, limit)
        sugg = []
        for r in ranked:
            c_chunk, q_chunk = int(chunks[r["col"]]), int(q[r["row"]])
            rec_c, rec_q = idx.record(c_chunk), idx.record(q_chunk)
            sentence, full = _best_sentence(idx, rec_c["text"], rec_q["text"])
            n_carry = carrier_count(full)
            flags = [GENERIC_NOTE.format(n=n_carry)] if n_carry >= GENERIC_MIN_INGREDIENTS else []
            q_sentence, _ = _best_sentence(idx, rec_q["text"], sentence)
            lab = idx.label(c_chunk)
            y = cat.ingredients[r["ing"]]
            total, brands = cat.brands_for_ingredient(r["ing"], fam, 5)
            sugg.append(SimilarUseSuggestion(
                ingredient=y["name"], us_name=y["us_name"], similarity=round(r["score"], 4),
                supporting_chunks=r["support"], supporting_sentence=sentence,
                supporting_label=SimilarLabelRef(set_id=lab["set_id"], name=lab["product"], manufacturer=lab["manufacturer"],
                                                 form=", ".join(lab["forms"]) or None, route=", ".join(lab["routes"]) or None),
                matched_query_sentence=q_sentence, flags=flags, brands_total=total,
                brands=[SimilarBrand(**b, price_difference=None, different_pack_size=False) for b in brands],
                brands_note=UNKNOWN_FORM_NOTE if fam == "unknown" else (NO_BRANDS_NOTE if not brands else None)))
        groups.append(SimilarUseGroup(
            ingredient=name, query_labels=n_labels, query_passages=len(q), from_combination_label=from_combo,
            note="Only a combination-product US label carries this ingredient, so its text also covers other ingredients."
            if from_combo else None, suggestions=sugg))
    return SimilarUseResponse(
        status="ready", id=cid, name=cat.names[i], encoder=idx.enc_name, encoder_label=idx.encoder.label,
        fallback_note=retrieval._fallback_text(settings), is_deep_learning=idx.encoder.is_deep_learning,
        min_similarity=settings.similar_use_min, heading=HEADING, note=NOTE,
        combination_note=COMBINATION_NOTE.format(n=len(own)) if len(own) > 1 else None, groups=groups)
