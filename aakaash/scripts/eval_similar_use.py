# SOURCE: NOT IN PAPERS (own evaluation). Nothing here is labelled right or wrong by the script. It prints
# what the method returns so a pharmacist can read it. recall@10 and MRR are reported ONLY when real,
# pharmacist-judged pairs exist in data/eval/similar_use_pairs.jsonl (lines marked EXAMPLE are skipped).
"""Similar-use evaluation helpers.

    scripts\\eval_similar_use.py --top5 --encoders tfidf,sbert     # top-5 for 25 well-known ingredients
    scripts\\eval_similar_use.py --distribution --encoders tfidf   # score distribution on 20 random ingredients (seed 13)
    scripts\\eval_similar_use.py --pairs                            # recall@10 and MRR from judged pairs
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
AAKAASH = HERE.parent
sys.path.insert(0, str(AAKAASH))

from api.config import get_settings  # noqa: E402
from api.services import catalogue, retrieval, similar_use  # noqa: E402

PAIRS = AAKAASH.parent / "data" / "eval" / "similar_use_pairs.jsonl"
NAMED = ["metformin", "atorvastatin", "amlodipine", "pantoprazole", "azithromycin", "cetirizine", "paracetamol",
         "acetaminophen", "ibuprofen", "losartan", "levothyroxine", "omeprazole", "simvastatin", "lisinopril",
         "metoprolol", "amoxicillin", "ciprofloxacin", "montelukast", "sertraline", "gabapentin", "warfarin",
         "clopidogrel", "glimepiride", "telmisartan", "furosemide", "prednisolone"]


def with_encoder(settings, enc: str):
    return dataclasses.replace(settings, encoder_name=enc)


def find_ing(cat, name: str) -> int | None:
    n = name.lower()
    for j, x in enumerate(cat.ingredients):
        if x["key"] == n or (x["name"] or "").lower() == n or (x["us_name"] or "").lower() == n:
            return j
    return None


def brand_for(cat, ing: int) -> str | None:
    """A single-ingredient catalogue product of this ingredient (first by price rank)."""
    for i in cat._ing_rows[ing]:
        if len(cat.comps[cat.comp[i]]["items"]) == 1:
            return cat.ids[i]
    return None


def top_for(settings, cat, ing: int, limit: int):
    bid = brand_for(cat, ing)
    return None if bid is None else similar_use.similar_use(settings, bid, limit)


def top5(settings, encoders: list[str]) -> None:
    cat = catalogue.get_catalogue(settings)
    for enc in encoders:
        s = with_encoder(settings, enc)
        print(f"\n######## encoder: {enc}  (printed for a pharmacist to read; nothing is marked right or wrong)")
        for name in NAMED:
            j = find_ing(cat, name)
            if j is None:
                print(f"\n{name}: not in the catalogue")
                continue
            r = top_for(s, cat, j, 5)
            if r is None or r.status != "ready" or not r.groups or not r.groups[0].suggestions:
                why = ("no single-ingredient product" if r is None
                       else (r.groups[0].note if r.status == "ready" and r.groups else r.reason))
                print(f"\n{name}: no result ({why})")
                continue
            g = r.groups[0]
            print(f"\n{name} (compared on {g.query_passages} Indications passages of {g.query_labels} US labels)")
            for k, x in enumerate(g.suggestions, 1):
                print(f"  {k}. {x.ingredient:<28} {x.similarity:.3f}  \"{x.supporting_sentence[:110]}\"")


def distribution(settings, encoders: list[str], n: int = 20, seed: int = 13) -> None:
    cat = catalogue.get_catalogue(settings)
    for enc in encoders:
        s = with_encoder(settings, enc)
        idx = retrieval.get_index(s)[0]
        ings, chunks, bounds = similar_use._candidates(cat, idx)
        pool = [j for j in ings if len(similar_use._query_chunks(cat, idx, j)[0])]
        random.Random(seed).shuffle(pool)
        print(f"\n######## encoder: {enc}: {len(ings)} candidate ingredients; {n} random query ingredients (seed {seed})")
        allscores, tops = [], []
        for j in pool[:n]:
            q = similar_use._query_chunks(cat, idx, j)[0]
            S = idx.pair_similarity(q, chunks).max(axis=0)
            per = np.array([S[bounds[k]:bounds[k + 1]].max() for k in range(len(ings))])
            mo = set(cat.ingredients[j]["link"]["moieties"])
            for k, i2 in enumerate(ings):
                if i2 == j or set(cat.ingredients[i2]["link"]["moieties"]) & mo:
                    per[k] = -1
            order = np.argsort(-per)
            allscores += [float(x) for x in per if x >= 0]
            tops.append(per[order[:10]])
            print(f"  {cat.ingredients[j]['name'][:24]:<24} top1..10: " + " ".join(f"{x:.2f}" for x in per[order[:10]])
                  + f"   top1 = {cat.ingredients[ings[order[0]]]['name']}")
        a, t = np.array(allscores), np.array(tops)
        pct = lambda arr, p: float(np.percentile(arr, p))
        print(f"  all candidate scores ({len(a)}): p50 {pct(a, 50):.3f} p90 {pct(a, 90):.3f} p99 {pct(a, 99):.3f} max {a.max():.3f}")
        print(f"  top-1 per query: min {t[:, 0].min():.3f} p25 {pct(t[:, 0], 25):.3f} p50 {pct(t[:, 0], 50):.3f} max {t[:, 0].max():.3f}")
        print(f"  5th: p50 {pct(t[:, 4], 50):.3f}; 10th: p50 {pct(t[:, 9], 50):.3f}")


def hubs(settings, enc: str = "tfidf") -> None:
    """How many distinct ingredients carry the same Indications sentence (normalised: lower case, letters
    and digits only). Used to choose, with a reviewer, when to flag 'generic wording'. No threshold is set here."""
    import re
    from collections import defaultdict
    from medsafe.index import split_sentences
    cat = catalogue.get_catalogue(settings)
    idx = retrieval.get_index(with_encoder(settings, enc))[0]
    ings, chunks, bounds = similar_use._candidates(cat, idx)
    carriers = defaultdict(set)
    shown = {}
    for n, j in enumerate(ings):
        for c in chunks[bounds[n]:bounds[n + 1]]:
            for sent in split_sentences(idx.text(int(c))):
                if len(sent.split()) >= similar_use.MIN_SENTENCE_WORDS:
                    k = re.sub(r"[^a-z0-9]+", " ", sent.lower()).strip()
                    carriers[k].add(j)
                    shown.setdefault(k, sent)
    counts = np.array([len(v) for v in carriers.values()])
    print(f"{len(carriers)} distinct Indications sentences (>= {similar_use.MIN_SENTENCE_WORDS} words) over {len(ings)} ingredients")
    for t in (2, 3, 5, 10, 20):
        print(f"  carried by >= {t} ingredients: {int((counts >= t).sum())} sentences")
    print("  most shared sentences:")
    for k, v in sorted(carriers.items(), key=lambda kv: -len(kv[1]))[:12]:
        print(f"   {len(v):>3} ingredients: {shown[k][:130]}")


def pairs(settings) -> None:
    rows = []
    if PAIRS.is_file():
        for line in PAIRS.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                if not d.get("EXAMPLE") and d.get("judged_by"):
                    rows.append(d)
    if not rows:
        print(f"No pharmacist-judged pairs in {PAIRS} (lines marked EXAMPLE are skipped), so no recall@10 or MRR is reported.")
        return
    cat = catalogue.get_catalogue(settings)
    hits, rr, used = 0, 0.0, 0
    for d in rows:
        j = find_ing(cat, d["query"])
        r = top_for(settings, cat, j, 10) if j is not None else None
        if r is None or r.status != "ready" or not r.groups:
            continue
        sug = r.groups[0].suggestions
        pos = next((k for k, x in enumerate(sug, 1)
                    if d["relevant"].lower() in (x.ingredient.lower(), (x.us_name or "").lower())), None)
        used += 1
        hits += pos is not None
        rr += 1 / pos if pos else 0
    print(f"{used} judged pairs scored of {len(rows)}: recall@10 = {hits / used:.3f}, MRR = {rr / used:.3f}"
          if used else "No judged pair could be scored.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--top5", action="store_true")
    ap.add_argument("--distribution", action="store_true")
    ap.add_argument("--pairs", action="store_true")
    ap.add_argument("--hubs", action="store_true")
    ap.add_argument("--encoders", default="tfidf")
    a = ap.parse_args()
    s = get_settings()
    encs = [e.strip() for e in a.encoders.split(",")]
    if a.top5:
        top5(s, encs)
    if a.distribution:
        distribution(s, encs)
    if a.pairs:
        pairs(s)
    if a.hubs:
        hubs(s)


if __name__ == "__main__":
    main()
