# SOURCE: NOT IN PAPERS (the endpoint and the wrong-form guard). The ranking is cosine similarity over
# label-text embeddings (P1, P2, P3). No boosts, no generated text. A missing or stale index gives
# status="not_ready"; nothing is invented. The guard reuses intake.label_mismatch (the rule behind
# the medicine details card).
"""POST /api/search/labels and GET /api/index/summary."""
from __future__ import annotations

import re
import time
from typing import NamedTuple

import numpy as np

from medsafe.appms_match import ingredient_keys
from medsafe.forms import UNKNOWN
from medsafe.index import Index, IndexError_, load_index
from medsafe.spl import INSTRUCTION_SECTIONS

from ..config import Settings
from ..schemas import IndexSummaryResponse, SearchLabelsRequest, SearchLabelsResponse, SearchResult
from . import catalogue, intake

NOT_READY_FIX = "Run scripts/build_index.py from the aakaash folder."
SECTION_LABELS = {
    "boxed_warning": "Boxed warning", "indications": "Indications", "contraindications": "Contraindications",
    "warnings_precautions": "Warnings and precautions", "precautions": "Precautions",
    "drug_interactions": "Drug interactions", "adverse_reactions": "Adverse reactions",
    "specific_populations": "Use in specific populations", "dosage_administration": "Dosage and administration",
    "patient_counseling": "Patient counselling information", "patient_information": "Patient information",
    "instructions_for_use": "Instructions for use",
}
NOTE = ("Passages from US FDA label text, ranked by cosine similarity to your words. Highlighted words are "
        "words from your search; the score is for the whole passage. Not medical advice.")
_STOP: frozenset[str] | None = None


SBERT_FIX = ("Build the sbert index on Kaggle with notebooks/build_sbert_index.ipynb, then run "
             "scripts/install_sbert.py sbert_index.zip from the aakaash folder.")


class FallbackInfo(NamedTuple):
    status: str  # "not_ready"
    reason: str
    fix: str

    def text(self) -> str:
        return f"{self.reason} {self.fix}"


def sbert_fallback(settings: Settings) -> FallbackInfo | None:
    """Set when ENCODER=sbert is configured but its index cannot be used. Nothing is hidden: the answering
    encoder is reported on every response and this explains why it is not the configured one."""
    if settings.encoder_name != "sbert":
        return None
    if not (settings.index_dir / "manifest.json").is_file():
        return None
    try:
        load_index(settings.index_dir, "sbert")
    except IndexError_ as e:
        return FallbackInfo("not_ready", f"The sbert index cannot be used ({e}), so TF-IDF answered instead.", SBERT_FIX)
    except ValueError as e:
        return FallbackInfo("not_ready", f"The sbert index cannot be used ({e}), so TF-IDF answered instead.", SBERT_FIX)
    return None


def get_index(settings: Settings) -> tuple[Index | None, str | None]:
    """(index, None) or (None, reason). Never raises for missing or stale files. With ENCODER=sbert and an
    unusable sbert index it falls back to the TF-IDF index (see sbert_fallback for the reason)."""
    if not (settings.index_dir / "manifest.json").is_file():
        return None, f"The label index {settings.display(settings.index_dir)} has not been built."
    try:
        return load_index(settings.index_dir, settings.encoder_name), None
    except (IndexError_, ValueError) as e:
        if settings.encoder_name == "sbert":
            try:
                return load_index(settings.index_dir, "tfidf"), None
            except (IndexError_, ValueError):
                pass
        return None, f"The label index cannot be used: {e}" if isinstance(e, IndexError_) else str(e)


def _not_ready(cls, reason: str, **kw):
    return cls(status="not_ready", reason=reason, fix=NOT_READY_FIX, **kw)


def match_terms(query: str, text: str) -> list[str]:
    """Query words (stop words dropped) that occur in the text, as whole words. For highlighting only."""
    global _STOP
    if _STOP is None:
        from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
        _STOP = frozenset(ENGLISH_STOP_WORDS)
    words = {w for w in re.findall(r"[a-z0-9]{2,}", query.lower()) if w not in _STOP}
    have = set(re.findall(r"[a-z0-9]{2,}", text.lower()))
    return sorted(w for w in words if w in have)


def _scope(settings: Settings, idx: Index, body: SearchLabelsRequest):
    """(allowed chunk indices or None, description, {set_id: (mismatch key, is_default)}, labels_searched)
    or a not-ready reason string."""
    if body.medicine_id:
        cat = catalogue.get_catalogue(settings)
        if cat is None:
            return "The medicine catalogue is missing."
        i = catalogue._row(cat, body.medicine_id)
        d = cat.detail(i)
        items = cat.comps[cat.comp[i]]["items"]
        first = {ing: w for ing, _, w in reversed(items)}
        brand_keys = [ingredient_keys(w, cat.ingredients[ing]["key"]) for ing, w in first.items()]
        fam = cat.family(i)
        guard: dict[str, tuple[str | None, bool]] = {}
        seen = set()
        for x in d["ingredient_details"]:
            if x["key"] in seen:
                continue
            seen.add(x["key"])
            for n, ref in enumerate(x["labels"]):
                sid = ref["set_id"]
                if body.scope == "default" and n > 0:
                    break
                if sid in guard and not (n == 0):
                    continue
                fams = cat.labels.get(sid, {}).get("families") or [UNKNOWN]
                fm = "brand_form_unknown" if fam == UNKNOWN else ("matched" if fam in fams else "none")
                moi = cat.labels.get(sid, {}).get("moieties", [])
                guard[sid] = (intake.label_mismatch(fm, not ref["single_ingredient"], moi, brand_keys), n == 0)
        ids = [s for s in guard if s in idx.label_by_id]
        return idx.chunks_of_labels(ids), f"{d['name']} ({'default label' if body.scope == 'default' else 'all linked labels'})", \
            {s: guard[s] for s in ids}, len(ids)
    if body.set_ids:
        ids = [s for s in body.set_ids if s in idx.label_by_id]
        return idx.chunks_of_labels(ids), "the chosen labels", {s: (None, False) for s in ids}, len(ids)
    return None, "all loaded US labels", {}, len(idx.labels)


def search_labels(settings: Settings, body: SearchLabelsRequest) -> SearchLabelsResponse:
    idx, why = get_index(settings)
    if idx is None:
        return _not_ready(SearchLabelsResponse, why)
    sc = _scope(settings, idx, body)
    if isinstance(sc, str):
        return _not_ready(SearchLabelsResponse, sc)
    allowed, desc, guard, n_labels = sc
    t0 = time.perf_counter()
    hits = idx.search(body.query, body.k, allowed)
    ms = (time.perf_counter() - t0) * 1000
    out = []
    for c, score in hits:
        rec = idx.record(c)
        lab = idx.label(c)
        sec = rec["section"]
        mm, default = guard.get(rec["set_id"], (None, False))
        withheld = bool(mm) and sec in INSTRUCTION_SECTIONS
        out.append(SearchResult(
            chunk_id=rec["chunk_id"], score=round(score, 4), section=sec, section_label=SECTION_LABELS.get(sec, sec),
            set_id=rec["set_id"], product=lab["product"], manufacturer=lab["manufacturer"],
            form=", ".join(lab["forms"]) or None, route=", ".join(lab["routes"]) or None,
            form_family=" / ".join(lab["families"]), is_default_label=default,
            text="" if withheld else rec["text"], match_terms=[] if withheld else match_terms(body.query, rec["text"]),
            withheld=withheld,
            withheld_note=intake.WITHHELD_COMBINATION_NOTE if withheld and mm == "single_for_combination"
            else (intake.WITHHELD_NOTE if withheld else None),
            mismatch_note=intake.MISMATCH_NOTE.get(mm) if mm else None))
    return SearchLabelsResponse(
        status="ready", encoder=idx.enc_name, encoder_label=idx.encoder.label,
        is_deep_learning=idx.encoder.is_deep_learning, restricted_to=desc, labels_searched=n_labels,
        elapsed_ms=round(ms, 2), note=NOTE, results=out, fallback_note=_fallback_text(settings))


def _fallback_text(settings: Settings) -> str | None:
    fb = sbert_fallback(settings)
    return fb.text() if fb else None


def summary(settings: Settings) -> IndexSummaryResponse:
    idx, why = get_index(settings)
    if idx is None:
        return _not_ready(IndexSummaryResponse, why)
    m, e = idx.manifest, idx.enc_manifest
    built = sorted(p.name for p in settings.index_dir.iterdir() if (p / "manifest.json").is_file())
    return IndexSummaryResponse(
        status="ready", labels=m["labels"], chunks=m["chunks"], chunks_per_section=m["chunks_per_section"],
        parts_loaded=m["parts_loaded"], chunk_size=m["chunk_size"], chunk_overlap=m["chunk_overlap"],
        chunk_unit=m["chunk_unit"], is_sample=m["is_sample"], encoders_built=built, active_encoder=idx.enc_name,
        active_encoder_label=idx.encoder.label, is_deep_learning=idx.encoder.is_deep_learning,
        dimension=e.get("dimension"), vectors=e.get("windows") or e.get("nnz"), vector_bytes=e.get("vector_bytes"),
        build_seconds=e.get("seconds"),
        model=e.get("model"), model_revision=e.get("model_revision"), device=e.get("device"),
        window_token_budget=e.get("window_token_budget"), window_overlap_words=e.get("window_overlap_words"),
        configured_encoder=settings.encoder_name, fallback_note=_fallback_text(settings))
