# SOURCE: NOT IN PAPERS (own tooling). Reads artifacts/catalogue.json and prints how the dosage-form
# rules (medsafe/forms.py) sort the real catalogue: family distribution, the most used rule terms,
# the share left unknown and the commonest unknown pack labels.
"""From the aakaash folder:  .venv\Scripts\python.exe scripts\measure_forms.py"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

AAKAASH = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AAKAASH))

from medsafe.forms import UNKNOWN, classify_product, classify_text  # noqa: E402


def main() -> None:
    d = json.loads((AAKAASH / "artifacts" / "catalogue.json").read_text(encoding="utf-8"))
    b, packs = d["brands"], d["packs"]
    fam, terms, where, unk, clash = Counter(), Counter(), Counter(), Counter(), []
    for n, p in zip(b["name"], b["pack"]):
        pack = packs[p]
        f, t, w = classify_product(n, pack)
        fam[f] += 1
        terms[(f, t)] += 1
        where[w] += 1
        if f == UNKNOWN:
            unk[pack] += 1
        else:
            fn, _ = classify_text(n)
            if w == "pack" and fn not in (UNKNOWN, f):
                clash.append((n, pack, f, fn))
    total = sum(fam.values())
    print(f"products: {total}")
    for f, c in fam.most_common():
        print(f"  {f:16s} {c:8d}  {100 * c / total:5.2f}%")
    print(f"unknown share: {100 * fam[UNKNOWN] / total:.2f}%   decided by: {dict(where)}")
    print("20 most used rule terms:")
    for (f, t), c in terms.most_common(21):
        if t:
            print(f"  {t:12s} {f:16s} {c}")
    print(f"pack says one family, name says another: {len(clash)}; sample:")
    for x in clash[:12]:
        print("  ", x)
    print("most common unknown pack labels:")
    for p, c in unk.most_common(15):
        print(f"  {c:6d}  {p}")


if __name__ == "__main__":
    main()
