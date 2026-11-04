# SOURCE: NOT IN PAPERS (own evaluation). There are NO relevance judgements, so this makes no accuracy and no
# relevance claim. It lays the two encoders side by side (overlap, speed, size, memory, the keyword proxy
# check) and prints examples where they disagree so a person can judge by eye.
"""Compare the TF-IDF and sbert indexes. Run from the aakaash folder after scripts/install_sbert.py:

    .venv\\Scripts\\python.exe scripts\\compare_encoders.py

Each encoder is measured in its own process so peak RAM is per encoder. Writes data/eval/top5_sbert.txt (same
format as top5_tfidf.txt) and artifacts/metrics/encoder_comparison.json. Never writes top5_tfidf.txt."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
AAKAASH = HERE.parent
sys.path.insert(0, str(AAKAASH))
sys.path.insert(0, str(HERE))

PROXY_LABEL = "proxy, not a relevance judgement"
EVAL_DIR = AAKAASH.parent / "data" / "eval"
FREE_QUERIES = ["warfarin bleeding risk", "avoid in pregnancy", "severe liver disease contraindicated",
                "take with food", "decrease the dose in kidney impairment"]


def pct(xs: list[float], p: float) -> float | None:
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(len(xs) * p))], 1) if xs else None


def folder_mb(folder: Path) -> float:
    return round(sum(f.stat().st_size for f in folder.rglob("*") if f.is_file()) / 1e6, 1)


def overlap(a: list[str], b: list[str]) -> int:
    return len({x.lower() for x in a} & {x.lower() for x in b})


def format_top5(enc: str, data: dict) -> str:
    out = ["", f"######## encoder: {enc}  (printed for a pharmacist to read; nothing is marked right or wrong)"]
    for name, v in data.items():
        out.append("")
        if "note" in v:
            out.append(f"{name}: {v['note']}")
            continue
        out.append(f"{name} (compared on {v['passages']} Indications passages of {v['labels']} US labels)")
        for k, x in enumerate(v["top"], 1):
            out.append(f"  {k}. {x['ingredient']:<28} {x['similarity']:.3f}  \"{x['sentence'][:110]}\""
                       f"{'  [FLAG: generic wording]' if x['flagged'] else ''}")
    return "\n".join(out) + "\n"


def worker(enc: str, n_products: int, seed: int) -> dict:
    """Measure one encoder in this process; the caller prints the returned dict as JSON."""
    import dataclasses

    import eval_retrieval
    import eval_similar_use as esu
    from api.config import get_settings
    from api.services import catalogue, retrieval, similar_use
    from dailymed_stats import peak_working_set_mb

    s = dataclasses.replace(get_settings(), encoder_name=enc)
    idx, why = retrieval.get_index(s)
    if idx is None or idx.enc_name != enc:
        raise SystemExit(f"{enc} index cannot be used ({why or 'the app fell back to ' + str(idx.enc_name)}); nothing measured.")
    cat = catalogue.get_catalogue(s)
    t = time.perf_counter()
    idx.search("warm up", 5)  # loads the model for sbert; reported apart from per-query latency
    first_s = time.perf_counter() - t
    lat = []
    for q in FREE_QUERIES:
        for _ in range(5):
            t = time.perf_counter()
            idx.search(q, 5)
            lat.append((time.perf_counter() - t) * 1000)
    proxy = eval_retrieval.run(s, enc, n_products, seed)
    top, sim_lat = {}, []
    for name in esu.NAMED:
        j = esu.find_ing(cat, name)
        if j is None:
            top[name] = {"note": "not in the catalogue"}
            continue
        bid = esu.brand_for(cat, j)
        if bid is None:
            top[name] = {"note": "no result (no single-ingredient product)"}
            continue
        t = time.perf_counter()
        r = similar_use.similar_use(s, bid, 5)
        sim_lat.append((time.perf_counter() - t) * 1000)
        if r.status != "ready" or not r.groups or not r.groups[0].suggestions:
            top[name] = {"note": f"no result ({r.groups[0].note if r.status == 'ready' and r.groups else r.reason})"}
            continue
        g = r.groups[0]
        top[name] = {"passages": g.query_passages, "labels": g.query_labels,
                     "top": [{"ingredient": x.ingredient, "similarity": x.similarity,
                              "sentence": x.supporting_sentence, "flagged": bool(x.flags)} for x in g.suggestions]}
    return {"encoder": enc, "label": idx.encoder.label, "index_mb": folder_mb(idx.folder / enc),
            "first_query_s": round(first_s, 2),
            "label_search_ms_p50": pct(lat, 0.5), "label_search_ms_p95": pct(lat, 0.95), "label_search_queries": len(lat),
            "proxy_label": PROXY_LABEL,
            "proxy": {q: {k: v[k] for k in ("counted", "hit", "share")} for q, v in proxy["queries"].items()},
            "proxy_products": proxy["products"], "proxy_seed": proxy["seed"],
            "similar_use_ms_p50": pct(sim_lat, 0.5), "similar_use_ms_p95": pct(sim_lat, 0.95),
            "similar_use_calls": len(sim_lat), "peak_ram_mb": peak_working_set_mb(), "top5": top}


def measure(enc: str, n: int, seed: int) -> dict:
    p = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker", enc, "--n", str(n), "--seed", str(seed)],
                       capture_output=True, text=True, encoding="utf-8")
    if p.returncode:
        sys.exit(f"measuring {enc} failed:\n{p.stderr[-1500:] or p.stdout[-1500:]}")
    return json.loads(p.stdout.splitlines()[-1])


def report(a: dict, b: dict, show: int) -> None:
    print(f"\n== Overlap of the top-5 similar-use ingredients, {a['encoder']} vs {b['encoder']} (same ingredient list as top5_tfidf.txt)")
    rows = []
    for name, va in a["top5"].items():
        vb = b["top5"].get(name, {})
        if "top" not in va or "top" not in vb:
            continue
        rows.append((overlap([x["ingredient"] for x in va["top"]], [x["ingredient"] for x in vb["top"]]), name))
        print(f"  {name:<16} {rows[-1][0]}/5")
    if rows:
        print(f"  mean overlap {sum(r[0] for r in rows) / len(rows):.2f} of 5 over {len(rows)} ingredients")
    print("\n== Speed, size, memory (this machine; sbert query time includes encoding the query on the CPU)")
    for r in (a, b):
        print(f"  {r['encoder']:<6} label search p50 {r['label_search_ms_p50']} ms, p95 {r['label_search_ms_p95']} ms "
              f"({r['label_search_queries']} queries); similar-use p50 {r['similar_use_ms_p50']} ms, p95 {r['similar_use_ms_p95']} ms "
              f"({r['similar_use_calls']} calls); first query {r['first_query_s']} s; index {r['index_mb']} MB; peak RAM {r['peak_ram_mb']} MB")
    print(f"\n== Keyword proxy check ({PROXY_LABEL}; {a['proxy_products']} products, seed {a['proxy_seed']})")
    for r in (a, b):
        for q, v in r["proxy"].items():
            print(f"  {r['encoder']:<6} '<ingredient> {q}': {v['hit']}/{v['counted']} = {v['share']}")
    print(f"\n== Where the two disagree (lowest overlap first; {show} ingredients). Judge by eye; nothing is marked right or wrong.")
    for ov, name in sorted(rows)[:show]:
        ta, tb = a["top5"][name]["top"], b["top5"][name]["top"]
        names_a, names_b = {x["ingredient"].lower() for x in ta}, {x["ingredient"].lower() for x in tb}
        print(f"\n{name}  (overlap {ov}/5)")
        for r, t, other in ((a, ta, names_b), (b, tb, names_a)):
            print(f"  only in {r['encoder']}:")
            for x in t:
                if x["ingredient"].lower() not in other:
                    print(f"    {x['ingredient']:<26} {x['similarity']:.3f}  \"{x['sentence'][:100]}\"")
    print("\nNo accuracy or relevance claim is made: there are no pharmacist relevance judgements.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--n", type=int, default=100, help="products for the proxy check")
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--show", type=int, default=8, help="how many disagreeing ingredients to print")
    ap.add_argument("--worker", help=argparse.SUPPRESS)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if a.worker:
        print(json.dumps(worker(a.worker, a.n, a.seed)))
        return
    tf, sb = measure("tfidf", a.n, a.seed), measure("sbert", a.n, a.seed)
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    (EVAL_DIR / "top5_sbert.txt").write_text(format_top5("sbert", sb["top5"]), encoding="utf-8")
    metrics = AAKAASH / "artifacts" / "metrics"
    metrics.mkdir(parents=True, exist_ok=True)
    (metrics / "encoder_comparison.json").write_text(json.dumps({"tfidf": tf, "sbert": sb}, indent=1), encoding="utf-8")
    print(f"wrote {EVAL_DIR / 'top5_sbert.txt'} and {metrics / 'encoder_comparison.json'}")
    report(tf, sb, a.show)


if __name__ == "__main__":
    main()
