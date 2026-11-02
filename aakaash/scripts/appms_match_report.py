# SOURCE: NOT IN PAPERS (own tooling). Reads data/appms/medications.csv and artifacts/names.json.
"""Report how many APPMS medication rows match at least one DailyMed label by active ingredient.

From the aakaash folder:  .venv\Scripts\python.exe scripts\appms_match_report.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

AAKAASH = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AAKAASH))

from medsafe import appms  # noqa: E402
from medsafe.appms_match import IngredientMatcher  # noqa: E402


def main() -> None:
    d = appms.load(AAKAASH.parent / "data" / "appms")
    names = json.loads((AAKAASH / "artifacts" / "names.json").read_text(encoding="utf-8"))
    m = IngredientMatcher(names["labels"])
    counts = Counter(x.drug_name for x in d.medications)
    print(f"DailyMed labels indexed: {len(names['labels'])} (sample run: {names['is_sample']})")
    print(f"{'drug name':28}{'rows':>6}{'labels':>8}")
    for n, c in sorted(counts.items(), key=lambda t: (-t[1], t[0])):
        print(f"{n:28}{c:>6}{len(m.match(n)):>8}")
    hit = {n for n in counts if m.match(n)}
    rows = sum(c for n, c in counts.items() if n in hit)
    print(f"\nmedication rows: {len(d.medications)}; matched to >=1 label: {rows}; unmatched: {len(d.medications) - rows}")
    print(f"distinct drug names: {len(counts)}; matched: {len(hit)}; unmatched: {len(counts) - len(hit)}")
    print("unmatched (name, rows):", [(n, c) for n, c in counts.most_common() if n not in hit])


if __name__ == "__main__":
    main()
