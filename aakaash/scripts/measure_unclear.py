# SOURCE: NOT IN PAPERS (own tooling). Reads artifacts/catalogue.json and counts how the "composition
# unclear" rule (a composition that repeats one normalised ingredient) changes the alternatives.
"""From the aakaash folder:  .venv\Scripts\python.exe scripts\measure_unclear.py"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

AAKAASH = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AAKAASH))

from medsafe.catalogue import Catalogue  # noqa: E402


def main() -> None:
    cat = Catalogue(json.loads((AAKAASH / "artifacts" / "catalogue.json").read_text(encoding="utf-8")))
    n = len(cat.ids)
    unclear = [i for i in range(n) if cat.unclear(i)]
    comps_u = {cat.comp[i] for i in unclear}
    print(f"unclear rows: {len(unclear)} of {n}; distinct unclear compositions: {len(comps_u)}")
    clear_by_set: Counter = Counter()
    for i in range(n):
        if not cat.unclear(i):
            clear_by_set[cat._set_key[cat.comp[i]]] += 1
    in_other = [i for i in unclear if clear_by_set[cat._set_key[cat.comp[i]]]]
    print(f"before: unclear rows listed as 'other strength' under clear products: {len(in_other)}; "
          f"rows with no clear product of the same ingredient set: {len(unclear) - len(in_other)}")
    sib = Counter(cat.comp[i] for i in unclear)
    print(f"before: unclear rows that had another row with the identical composition (listed as its same-strength match): "
          f"{sum(1 for i in unclear if sib[cat.comp[i]] > 1)}")
    sets_with_unclear = {cat._set_key[c] for c in comps_u}
    clear_with_group = sum(1 for i in range(n) if not cat.unclear(i) and cat._set_key[cat.comp[i]] in sets_with_unclear)
    print(f"now: clear products that show a 'Composition unclear' group: {clear_with_group}")
    # after: no unclear row in any main / different / not-stated / other-strength list of a clear product
    leak = 0
    for i in range(n):
        if cat.unclear(i) or cat._set_key[cat.comp[i]] not in sets_with_unclear:
            continue
        a = cat.alternatives(i, include_discontinued=True)
        names = {r["id"] for k in ("same", "different_form", "form_not_stated") for r in a[k]}
        names |= {r["id"] for g in a["other_strength"] for r in g["brands"]}
        leak += any(cat.unclear(cat.by_id[x]) for x in names)
    print(f"now: clear products whose match lists contain an unclear row: {leak}")
    sel = [i for i in unclear if cat._set_key[cat.comp[i]] and not clear_by_set[cat._set_key[cat.comp[i]]]]
    print("unclear rows with no clear product to list under:", len(sel))


if __name__ == "__main__":
    main()
