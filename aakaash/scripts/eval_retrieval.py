# SOURCE: NOT IN PAPERS (own evaluation). There are NO labelled relevance judgements, so this reports no
# accuracy. It is a PROXY check, not a relevance judgement: does a label of the right ingredient, in the
# right section, appear in the top 5? Sample: 100 random catalogue products (seed 13).
"""Proxy check for label search.

    .venv\Scripts\python.exe scripts\eval_retrieval.py --encoders tfidf,sbert
Queries: "<ingredient> drug interactions" -> drug_interactions section; "<ingredient> contraindications"
-> contraindications section. A product counts only if one of its linked labels HAS that section;
the others are listed apart, not counted."""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
AAKAASH = HERE.parent
sys.path.insert(0, str(AAKAASH))

from api.config import get_settings  # noqa: E402
from api.services import catalogue  # noqa: E402
from medsafe.index import load_index  # noqa: E402

QUERIES = [("drug interactions", "drug_interactions"), ("contraindications", "contraindications")]


def sample_products(cat, n: int, seed: int) -> list[tuple[str, str, int]]:
    """(brand id, ingredient written name, ingredient index) for n random products whose first
    ingredient has at least one linked US label."""
    rows = []
    for i in range(len(cat.ids)):
        items = cat.comps[cat.comp[i]]["items"]
        if items and cat.ingredients[items[0][0]]["link"]["set_ids"]:
            rows.append((cat.ids[i], items[0][2], items[0][0]))
    random.Random(seed).shuffle(rows)
    return rows[:n]


def run(settings, enc: str, n: int, seed: int) -> dict:
    cat = catalogue.get_catalogue(settings)
    idx = load_index(settings.index_dir, enc)
    prods = sample_products(cat, n, seed)
    out = {"encoder": enc, "products": len(prods), "seed": seed, "label": "proxy, not a relevance judgement", "queries": {}}
    lat = []
    for qtext, section in QUERIES:
        hit = skipped = 0
        miss = []
        for bid, name, ing in prods:
            ln = cat.ingredients[ing]["link"]
            sids = [s for s in ln["set_ids"] if s in idx.label_by_id]
            moi = set(ln["moieties"])
            own = idx.chunks_of_labels(sids)
            if not (idx.chunk_section[own] == idx.sections.index(section)).any():
                skipped += 1
                continue
            t = time.perf_counter()
            top = idx.search(f"{name} {qtext}", 5)
            lat.append((time.perf_counter() - t) * 1000)
            ok = any(idx.section(c) == section and set(idx.label(c)["moieties"]) & moi for c, _ in top)
            hit += ok
            if not ok:
                miss.append(name)
        counted = len(prods) - skipped
        out["queries"][qtext] = {"section": section, "counted": counted, "hit": hit,
                                 "share": round(hit / counted, 3) if counted else None,
                                 "skipped_no_such_section": skipped, "misses": miss}
    lat.sort()
    out["latency_ms_p50"] = round(lat[len(lat) // 2], 1) if lat else None
    out["latency_ms_p95"] = round(lat[int(len(lat) * 0.95)], 1) if lat else None
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--encoders", default="tfidf")
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--seed", type=int, default=13)
    a = ap.parse_args()
    s = get_settings()
    for enc in a.encoders.split(","):
        r = run(s, enc.strip(), a.n, a.seed)
        (s.artifacts_dir / "metrics" / f"label_search_proxy_{enc.strip()}.json").write_text(json.dumps(r, indent=1), encoding="utf-8")
        print(f"\n== encoder {r['encoder']}  ({r['label']}; {r['products']} products, seed {r['seed']})")
        for q, v in r["queries"].items():
            print(f"  '<ingredient> {q}': top-5 has a right-ingredient chunk in {v['section']}: "
                  f"{v['hit']}/{v['counted']} = {v['share']}  (not counted, no such section in any linked label: {v['skipped_no_such_section']})")
            print(f"     misses: {', '.join(v['misses'][:25])}")
        print(f"  search latency p50 {r['latency_ms_p50']} ms, p95 {r['latency_ms_p95']} ms")


if __name__ == "__main__":
    main()
