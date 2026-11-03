# SOURCE: NOT IN PAPERS (own tooling). Every number in the output comes from running the
# parsers on the real files in data/. Nothing is estimated, and missing data is stated as such.
"""Write DATASET_REPORT.md from real counts only.

Run from the aakaash/ folder:  python data_report.py [--max-labels-per-part N]
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from medsafe import ddi2013, tac2017  # noqa: E402
from medsafe.chunking import DEFAULT_OVERLAP, DEFAULT_SIZE, chunk_label  # noqa: E402
from medsafe.spl import CANONICAL_SECTIONS, INSTRUCTION_SECTIONS, iter_parts  # noqa: E402

ALL_SECTIONS = CANONICAL_SECTIONS + INSTRUCTION_SECTIONS  # risk sections first, then the instruction sections


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def has_files(folder: Path, pattern: str) -> bool:
    return folder.is_dir() and any(folder.rglob(pattern))


def report_dailymed(folder: Path, size, overlap, max_labels):
    lines = ["## DailyMed Rx labels (Subarea A source)", ""]
    if not has_files(folder, "*.zip"):
        return lines + [f"NOT RUN: no `.zip` files found in `{folder}`.", ""]
    by_part: dict = {}
    sec_label_counts, sec_part_counts = Counter(), Counter()
    sec_chars: dict[str, list[int]] = {s: [] for s in ALL_SECTIONS}
    chunk_counts, methods = Counter(), Counter()
    ingredient_set, set_ids = set(), set()
    labels = no_ing = no_sections = 0
    ing_src = Counter()
    for rec in iter_parts(folder, by_part, max_labels):
        labels += 1
        set_ids.add(rec["set_id"])
        ingredient_set.update(rec["ingredients"])
        ing_src[rec["ingredient_source"]] += 1
        no_ing += not rec["ingredients"]
        no_sections += not rec["sections"]
        methods.update(rec["section_methods"])
        for sec, parts in rec["sections"].items():
            sec_label_counts[sec] += 1
            sec_part_counts[sec] += len(parts)
            sec_chars[sec].append(sum(len(p["text"]) for p in parts))
        for ch in chunk_label(rec, size, overlap):
            chunk_counts[ch["section"]] += 1
    note = f"capped at {max_labels} labels per part" if max_labels else "no cap"
    lines += [f"Parts loaded ({note}):", ""]
    lines.append(md_table(
        ["part zip", "labels parsed", "parse failures", "other stats"],
        [[n, s["labels_parsed"], s["parse_failures"],
          json.dumps({k: v for k, v in s.items()
                      if k not in ("labels_parsed", "parse_failures")})]
         for n, s in by_part.items()]))
    lines += ["", f"- Labels parsed: {labels}",
              f"- Distinct set ids: {len(set_ids)}",
              f"- Distinct active ingredients (normalised strings): {len(ingredient_set)}",
              f"- Labels with no ingredient found: {no_ing}",
              f"- Labels with none of the {len(CANONICAL_SECTIONS)} sections found: {no_sections}",
              f"- Ingredient source counts: {dict(ing_src)}",
              f"- Section detection method counts: {dict(methods)}",
              f"- Chunking: size={size}, overlap={overlap}, unit=whitespace words", ""]
    rows = []
    for s in ALL_SECTIONS:
        ch = sec_chars[s]
        rows.append([s, sec_label_counts[s], sec_part_counts[s],
                     int(statistics.median(ch)) if ch else "-", chunk_counts[s]])
    lines += [md_table(["section", "labels with section", "section blocks",
                        "median chars per label", "chunks"], rows),
              f"\nTotal chunks: {sum(chunk_counts.values())}", ""]
    return lines


def report_ddi(folder: Path, out_dir: Path):
    lines = ["## DDI Extraction 2013 (Subarea B source)", ""]
    if not has_files(folder, "*.xml"):
        return lines + [f"NOT RUN: no `.xml` files found in `{folder}`.", ""]
    st = ddi2013.build_dataset(folder, out_dir)
    lines += [f"XML files by split (classified by folder name): {st['files']}"]
    if st["unclassified_examples"]:
        lines.append(f"Unclassified examples (skipped, check folder names): "
                     f"{st['unclassified_examples']}")
    lines += ["", f"Dev split: {st['dev_frac']:.0%} of train, stratified by label and grouped by "
              f"document, seed {st['seed']}. Entity markers: {st['markers']}", ""]
    rows = []
    for lab in ddi2013.ALL_LABELS:
        row = [lab]
        for sp in ("train", "dev", "test"):
            row.append(st["label_counts"][sp].get(lab, 0))
        rows.append(row)
    totals = [sum(st["label_counts"][sp].values()) for sp in ("train", "dev", "test")]
    rows.append(["**total**"] + totals)
    lines += [md_table(["class", "train", "dev", "test"], rows), ""]
    imb = []
    for sp in ("train", "dev", "test"):
        c = st["label_counts"][sp]
        neg = c.get(ddi2013.NEGATIVE, 0)
        for lab in ddi2013.POSITIVE_CLASSES:
            n = c.get(lab, 0)
            imb.append([sp, lab, f"{neg / n:.2f}" if n else "n/a"])
    lines += ["Imbalance ratio = (count of `false`) / (count of class):", "",
              md_table(["split", "class", "false : class"], imb), "",
              f"By source: {json.dumps(st['source_counts'])}", "",
              f"Parser statistics (skips and anomalies): {json.dumps(st['parse_stats'])}", ""]
    return lines


def report_tac(folder: Path):
    lines = ["## TAC 2017 ADR labels (parser sanity-check set)", ""]
    if not has_files(folder, "*.xml"):
        return lines + [f"NOT RUN: no `.xml` files found in `{folder}`.", ""]
    s = tac2017.summarize(folder)
    lines += ["Counts produced by `medsafe.tac2017.summarize`:", "", "```json",
              json.dumps(s, indent=2), "```", ""]
    return lines


def main():
    repo = HERE.parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", type=Path, default=repo / "data")
    ap.add_argument("--out", type=Path, default=HERE / "DATASET_REPORT.md")
    ap.add_argument("--artifacts", type=Path, default=HERE / "artifacts")
    ap.add_argument("--max-labels-per-part", type=int, default=None)
    ap.add_argument("--chunk-size", type=int, default=DEFAULT_SIZE)
    ap.add_argument("--overlap", type=int, default=DEFAULT_OVERLAP)
    a = ap.parse_args()
    lines = ["# Dataset report", "",
             f"Generated {datetime.now():%Y-%m-%d %H:%M} by `aakaash/data_report.py` "
             f"({' '.join(sys.argv[1:]) or 'default arguments'}). "
             "Every count below was produced by running the parsers on the real files; "
             "sections marked NOT RUN had no data present.", ""]
    mapping = a.data_root / "mappings"
    lines += report_dailymed(a.data_root / "dailymed_rx", a.chunk_size, a.overlap,
                             a.max_labels_per_part)
    lines += ["## DailyMed mapping files", "",
              ("Files present: " + ", ".join(sorted(p.name for p in mapping.iterdir()
                                                   if p.name != ".gitkeep")))
              if mapping.is_dir() and any(p.name != ".gitkeep" for p in mapping.iterdir())
              else f"NOT PRESENT: `{mapping}` is empty. Not parsed yet.", ""]
    lines += report_ddi(a.data_root / "ddi2013", a.artifacts / "ddi2013")
    lines += report_tac(a.data_root / "tac2017")
    a.out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
