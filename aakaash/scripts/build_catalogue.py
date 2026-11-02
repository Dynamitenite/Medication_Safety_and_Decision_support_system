# SOURCE: NOT IN PAPERS (own tooling). Every value comes from the real catalogue CSVs in
# data/indian_meds and from artifacts/names.json. The output is generated data and is gitignored
# (aakaash/artifacts/).
"""Write artifacts/catalogue.json: the Indian medicine catalogue with parsed compositions and
DailyMed links per ingredient. Prints counts, link rates, time and file size.

From the aakaash folder (run scripts/build_names.py first):
    .venv\\Scripts\\python.exe scripts\\build_catalogue.py
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
AAKAASH = HERE.parent
sys.path.insert(0, str(AAKAASH))

from medsafe.catalogue import build  # noqa: E402

MAIN_FILE = "updated_indian_medicine_data.csv"
CHECK_FILE = "indian_medicine_data.csv"
PRICE_ALIASES = {"price(₹)": "price"}  # the two files name the price column differently


def read(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return [{PRICE_ALIASES.get(k, k): v for k, v in r.items()} for r in csv.DictReader(f)]


def check_same(main: list[dict], other: list[dict]) -> None:
    """D1: the two files must hold the same ids and the same values in every shared column."""
    by_id = {r["id"]: r for r in main}
    if len(by_id) != len(main) or {r["id"] for r in other} != set(by_id):
        sys.exit(f"{MAIN_FILE} and {CHECK_FILE} do not hold the same ids; stopping.")
    cols = [c for c in other[0] if c in main[0]]
    diff = sum(1 for r in other for c in cols if r[c] != by_id[r["id"]][c])
    if diff:
        sys.exit(f"{diff} cells differ between {MAIN_FILE} and {CHECK_FILE}; stopping.")
    print(f"check: {CHECK_FILE} matches {MAIN_FILE} on {len(cols)} shared columns for {len(other)} ids")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--data-dir", type=Path, default=AAKAASH.parent / "data" / "indian_meds")
    ap.add_argument("--names", type=Path, default=AAKAASH / "artifacts" / "names.json")
    ap.add_argument("--out", type=Path, default=AAKAASH / "artifacts" / "catalogue.json")
    a = ap.parse_args()
    main_path = a.data_dir / MAIN_FILE
    if not main_path.is_file():
        sys.exit(f"{main_path} is missing; nothing to build.")
    if not a.names.is_file():
        sys.exit(f"{a.names} is missing. Run scripts/build_names.py first.")

    t0 = time.perf_counter()
    rows = read(main_path)
    if (a.data_dir / CHECK_FILE).is_file():
        check_same(rows, read(a.data_dir / CHECK_FILE))
    else:
        print(f"check: {CHECK_FILE} not present; not compared")
    names = json.loads(a.names.read_text(encoding="utf-8"))
    if names["labels"] and "sections" not in names["labels"][0]:
        sys.exit("names.json has no section lists. Re-run scripts/build_names.py.")
    data, rep = build(rows, names["labels"])
    data["meta"] = {
        "source": "Indian-Medicine-Dataset (public GitHub repository by junioralive)",
        "licence": "MIT, as stated by the repository", "original_source": "not stated by the repository",
        "file": MAIN_FILE,
        "file_date": datetime.fromtimestamp(main_path.stat().st_mtime, timezone.utc).date().isoformat(),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dailymed_parts_loaded": sorted({l["source"].partition("!")[0] for l in names["labels"]}),
        "dailymed_is_sample": names.get("is_sample", False),
        "report": rep,
    }
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    elapsed = time.perf_counter() - t0

    pct = lambda x: f"{100 * x:.1f}%" if x is not None else "n/a"
    print(f"rows: {rep['rows']}  discontinued: {rep['discontinued']}  from salt_composition: {rep['from_salt_composition']}")
    print(f"composition may be incomplete: {rep['composition_incomplete']}  conflict: {rep['composition_conflict']}  "
          f"price not stated: {rep['price_not_stated']}")
    print(f"unparseable items: {rep['unparseable_items']} in {rep['rows_with_unparseable_items']} rows; "
          f"sample: {rep['unparseable_sample'][:10]}")
    print(f"distinct compositions: {rep['distinct_compositions']}  secondary interaction rows: "
          f"{rep['secondary_interaction_rows']}  unreadable: {rep['interactions_unreadable']}")
    print(f"DailyMed labels loaded: {rep['dailymed_labels_loaded']} ({', '.join(data['meta']['dailymed_parts_loaded'])}); "
          f"linked to an ingredient: {rep['dailymed_labels_linked']}")
    print(f"distinct ingredients: {rep['distinct_ingredients']}; linked: {rep['ingredients_linked']} "
          f"({pct(rep['ingredients_linked_share'])}); by method: {rep['ingredients_linked_by_method']}; "
          f"combination labels only: {rep['ingredients_linked_combination_only']}")
    print(f"brands with ALL ingredients linked: {rep['brands_all_linked']} of {rep['brands']} "
          f"({pct(rep['brands_all_linked_share'])}); complete compositions: {rep['brands_complete_all_linked']} of "
          f"{rep['brands_complete']}; flagged compositions: {rep['brands_flagged_all_linked']} of {rep['brands_flagged']}")
    print("30 most frequent unlinked ingredients (rows):")
    for x in rep["top_unlinked"]:
        print(f"   {x['rows']:7d}  {x['name']}" + (f"  (US name {x['us_name']})" if x["us_name"] else ""))
    print(f"time: {elapsed:.1f} s  file: {a.out.stat().st_size / 1e6:.2f} MB  ({a.out})")


if __name__ == "__main__":
    main()
