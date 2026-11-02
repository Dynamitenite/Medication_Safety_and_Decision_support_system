# SOURCE: NOT IN PAPERS. Own curated list (medsafe/synonyms.csv), approved by the user row by row.
"""Exact name equivalences between the names used on Indian products and the US names used in
DailyMed. Lookup is exact after normalisation (medsafe.names.norm); nothing is fuzzy."""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

from .names import norm

SYNONYMS_FILE = Path(__file__).with_name("synonyms.csv")
KINDS = ("INN/USAN name equivalence", "spelling fix")


def read_rows(path: Path = SYNONYMS_FILE) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        rows = [{k: (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f)]
    for r in rows:
        if r["kind"] not in KINDS:
            raise ValueError(f"synonyms.csv: unknown kind {r['kind']!r} for {r['name']!r}")
    return rows


@lru_cache(maxsize=4)
def table(path: Path = SYNONYMS_FILE) -> dict[str, str]:
    """norm(name) -> norm(maps_to)."""
    return {norm(r["name"]): norm(r["maps_to"]) for r in read_rows(path)}


def canonical(name: str) -> str:
    """The normalised name, mapped to its US name when the list has one."""
    n = norm(name)
    return table().get(n, n)
