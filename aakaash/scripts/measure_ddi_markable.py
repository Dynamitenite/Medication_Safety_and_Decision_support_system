# SOURCE: NOT IN PAPERS (own tooling). Counts, on the real DailyMed label text the app reads, how many
# label sentences shown by the risk analysis / checker can be marked (<e1>/<e2>) for the DDI model,
# and (with --model-dir) classifies them to time the model. Nothing is estimated.
"""Coverage of the interaction-type model on real label sentences.

From the aakaash folder:
  .venv\\Scripts\\python.exe scripts\\measure_ddi_markable.py [--model-dir artifacts/smoke/models/ddi_smoke]
Pairs: (1) every pair in the interaction rules file (data/appms/ddi_seed_rules.csv); (2) every pair among
the distinct drugs named in those rules. Each pair is checked by generic name, exactly as the app does.
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import statistics
import sys
import time
from pathlib import Path

AAKAASH = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AAKAASH))

from api.config import get_settings  # noqa: E402
from api.schemas import DDIClassifyRequest  # noqa: E402
from api.services import catalogue, ddi  # noqa: E402
from medsafe.ddi_text import mark_sentence  # noqa: E402


def sentences(settings, a: str, b: str):
    r = catalogue.check(settings, [], [a, b])
    if r.status != "ready":
        return [], 0
    out = []
    for p in r.pairs:
        out.extend(p.text_match.matches)
    return out, sum(p.text_match.matches_total for p in r.pairs)


def measure(settings, pairs, classify: bool):
    shown = with_source = markable = 0
    total = 0
    distinct = {}
    for a, b in pairs:
        ms, n = sentences(settings, a, b)
        total += n
        for m in ms:
            shown += 1
            if not m.source_term:
                continue
            with_source += 1
            mp = mark_sentence(m.sentence, m.source_term, m.matched_term)
            if mp is not None:
                markable += 1
                distinct.setdefault(mp.marked_text, (m.sentence, m.source_term, m.matched_term))
    out = {"pairs_checked": len(pairs), "label_sentences_matching_in_labels": total, "sentences_shown": shown,
           "with_source_term": with_source, "markable": markable, "distinct_marked_inputs": len(distinct)}
    if classify and distinct:
        times, preds = [], {}
        for sent, d1, d2 in distinct.values():
            t = time.perf_counter()
            r = ddi.classify(settings, DDIClassifyRequest(sentence=sent, drug_1=d1, drug_2=d2))
            times.append((time.perf_counter() - t) * 1000)
            if r.status == "ready":
                preds[r.predicted] = preds.get(r.predicted, 0) + 1
        out["classified"] = sum(preds.values())
        out["predicted_class_counts"] = preds
        out["classify_ms_median"] = round(statistics.median(times), 1)
        out["classify_ms_max"] = round(max(times), 1)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", type=Path, default=None)
    args = ap.parse_args()
    settings = get_settings()
    if args.model_dir:
        settings = type(settings)(**{**settings.__dict__, "ddi_model_dir_override": args.model_dir.resolve()})
    rules = settings.data_dir / "appms" / "ddi_seed_rules.csv"
    with open(rules, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    rule_pairs = [(r["drug_a"], r["drug_b"]) for r in rows]
    drugs = sorted({d for p in rule_pairs for d in p})
    all_pairs = list(itertools.combinations(drugs, 2))
    res = {"rules_file_rows": len(rows), "distinct_drugs": len(drugs),
           "rule_pairs": measure(settings, rule_pairs, bool(args.model_dir)),
           "all_pairs_among_rule_drugs": measure(settings, all_pairs, bool(args.model_dir))}
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
