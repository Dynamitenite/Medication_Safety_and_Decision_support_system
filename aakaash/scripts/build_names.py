# SOURCE: NOT IN PAPERS (own tooling). Every value comes from medsafe.spl on the real DailyMed
# zips. No embeddings. The output is generated data and is gitignored (aakaash/artifacts/).
"""Write artifacts/names.json: one record per label, for the name search and the medicine page.

From the aakaash folder:
    .venv\\Scripts\\python.exe scripts\\build_names.py
Sample run:  ... --max-labels-per-part 200
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
AAKAASH = HERE.parent
sys.path.insert(0, str(AAKAASH))

from medsafe.spl import INSTRUCTION_SECTIONS, iter_parts  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--data-dir", type=Path, default=AAKAASH.parent / "data" / "dailymed_rx")
    ap.add_argument("--out", type=Path, default=AAKAASH / "artifacts" / "names.json")
    ap.add_argument("--max-labels-per-part", type=int, default=None,
                    help="cap per zip; the output is then marked as a sample")
    a = ap.parse_args()
    if not list(a.data_dir.glob("*.zip")):
        sys.exit(f"No .zip files in {a.data_dir}; nothing to index.")

    t0 = time.perf_counter()
    labels, seen = [], set()
    duplicates = 0
    for rec in iter_parts(a.data_dir, None, a.max_labels_per_part):
        sid = rec["set_id"]
        if not sid or sid in seen:
            duplicates += bool(sid)
            continue
        seen.add(sid)
        labels.append({
            "set_id": sid,
            "products": rec["product_names"],
            "generic": rec["generic_names"],
            "ingredients": rec["ingredients_raw"],
            "moieties": rec["active_moieties"],
            "moieties_raw": rec["active_moieties_raw"],
            "manufacturer": rec["manufacturer"],
            "dosage_forms": rec["dosage_forms"],
            "title": rec["title"],
            "effective_time": rec["effective_time"],
            # risk sections with text: the catalogue picks the default label for an ingredient by this
            "sections": sorted(k for k, v in rec["sections"].items()
                               if k not in INSTRUCTION_SECTIONS and any(s["text"].strip() for s in v)),
            # instruction sections with text (medicine details card); not part of the count above
            "instruction_sections": sorted(k for k, v in rec["sections"].items()
                                           if k in INSTRUCTION_SECTIONS and any(s["text"].strip() for s in v)),
            "source": rec["source"],
            "member": rec["member"],
        })
    out = {"is_sample": a.max_labels_per_part is not None, "label_count": len(labels),
           "duplicate_set_ids_skipped": duplicates, "labels": labels}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    elapsed = time.perf_counter() - t0
    c = Counter()
    for l in labels:
        c["no_moiety"] += not l["moieties"]
        c["no_generic"] += not l["generic"]
        c["no_manufacturer"] += not l["manufacturer"]
        c["no_form"] += not l["dosage_forms"]
        c["no_route"] += not any(p["routes"] for p in l["dosage_forms"])
        for k in ("indications", "boxed_warning"):
            c[k] += k in l["sections"]
        for k in l["instruction_sections"]:
            c[k] += 1
    print(f"labels: {len(labels)}  duplicates skipped: {duplicates}  sample: {out['is_sample']}")
    print(f"without moiety: {c['no_moiety']}  without generic: {c['no_generic']}  "
          f"without manufacturer: {c['no_manufacturer']}  without dosage form: {c['no_form']}  "
          f"without route: {c['no_route']}")
    n = max(len(labels), 1)
    print("labels with section text: " + "  ".join(
        f"{k} {c[k]} ({c[k] / n:.1%})" for k in ("indications", "boxed_warning", *INSTRUCTION_SECTIONS)))
    print(f"time: {elapsed:.1f} s  file: {a.out.stat().st_size / 1e6:.2f} MB  ({a.out})")


if __name__ == "__main__":
    main()
