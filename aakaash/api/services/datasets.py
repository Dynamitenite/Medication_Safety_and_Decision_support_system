# SOURCE: NOT IN PAPERS. Reads real files through the parsers in aakaash/medsafe and returns
# their counts. Nothing here invents a number: with no data the result is "not_ready".
"""Dataset statistics for the dashboard."""
from __future__ import annotations

import json
import threading
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from medsafe import ddi2013, tac2017

from ..config import Settings
from ..schemas import (DDIExample, DDIExamplesResponse, DDIParserStats, DDISplitStats,
                       DDIStatsResponse, DailyMedStatsResponse, TacStatsResponse, ZipFileInfo)

DDI_DIRNAME = "ddi2013"
TAC_DIRNAME = "tac2017"
DAILYMED_DIRNAME = "dailymed_rx"
DAILYMED_STATS_FILE = "dailymed_stats.json"  # written by scripts/dailymed_stats.py
SPLITS = ("train", "dev", "test")

_cache: dict[str, "DDIData"] = {}
_lock = threading.Lock()


@dataclass
class DDIData:
    files_by_split: dict[str, int]
    parse_stats: dict[str, dict[str, int]]
    rows: dict[str, list[dict]]
    dev_frac: float
    seed: int


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def ddi_root(settings: Settings) -> Path:
    return settings.data_dir / DDI_DIRNAME


def ddi_has_files(settings: Settings) -> bool:
    root = ddi_root(settings)
    return root.is_dir() and next(root.rglob("*.xml"), None) is not None


def load_ddi(settings: Settings, dev_frac: float = 0.1, seed: int = 13) -> DDIData | None:
    """Parse the corpus once per process (same dev-split settings as data_report.py)."""
    if not ddi_has_files(settings):
        return None
    root = ddi_root(settings)
    key = f"{root.resolve()}|{dev_frac}|{seed}"
    with _lock:
        if key in _cache:
            return _cache[key]
        files = ddi2013.classify_files(root)
        train_all, train_stats = ddi2013.load_split(files["train"])
        test, test_stats = ddi2013.load_split(files["test"])
        train, dev = (ddi2013.make_dev_split(train_all, dev_frac, seed) if train_all else ([], []))
        data = DDIData(
            files_by_split={k: len(v) for k, v in files.items()},
            parse_stats={"train_all": dict(train_stats), "test": dict(test_stats)},
            rows={"train": train, "dev": dev, "test": test},
            dev_frac=dev_frac, seed=seed)
        _cache[key] = data
        return data


def _ddi_not_ready(settings: Settings) -> dict:
    return {"status": "not_ready",
            "reason": f"No .xml files found under {settings.display(ddi_root(settings))}.",
            "fix": "Put the DDI Extraction 2013 corpus (the DDICorpus folder) in data/ddi2013."}


def ddi_stats(settings: Settings) -> DDIStatsResponse:
    data = load_ddi(settings)
    if data is None:
        return DDIStatsResponse(**_ddi_not_ready(settings))
    splits = []
    for name in SPLITS:
        rows = data.rows[name]
        counts = Counter(r["label"] for r in rows)
        neg = counts.get(ddi2013.NEGATIVE, 0)
        splits.append(DDISplitStats(
            split=name, instances=len(rows),
            class_counts={lab: counts.get(lab, 0) for lab in ddi2013.ALL_LABELS},
            imbalance_false_to_class={
                lab: (neg / counts[lab] if counts.get(lab) else None)
                for lab in ddi2013.POSITIVE_CLASSES},
            by_source=dict(Counter(r["source"] for r in rows))))
    return DDIStatsResponse(
        status="ready", labels=list(ddi2013.ALL_LABELS), files_by_split=data.files_by_split,
        splits=splits,
        parser=[DDIParserStats(split=k, counts=v) for k, v in data.parse_stats.items()],
        dev_frac=data.dev_frac, seed=data.seed)


def ddi_examples(settings: Settings, split: str | None, label: str | None,
                 limit: int) -> DDIExamplesResponse:
    data = load_ddi(settings)
    if data is None:
        return DDIExamplesResponse(**_ddi_not_ready(settings))
    names = [split] if split else list(SPLITS)
    matching = [(s, r) for s in names for r in data.rows[s] if label is None or r["label"] == label]
    examples = [DDIExample(split=s, **{k: r[k] for k in (
        "label", "source", "doc_id", "sent_id", "pair_id", "e1_text", "e2_text", "text",
        "marked_text")}) for s, r in matching[:limit]]
    return DDIExamplesResponse(status="ready", total_matching=len(matching), examples=examples)


# ---- DailyMed -----------------------------------------------------------------------------
def dailymed_zips(settings: Settings) -> list[Path]:
    folder = settings.data_dir / DAILYMED_DIRNAME
    return sorted(folder.glob("*.zip")) if folder.is_dir() else []


def dailymed_stats(settings: Settings) -> DailyMedStatsResponse:
    folder = settings.data_dir / DAILYMED_DIRNAME
    zips = dailymed_zips(settings)
    if not zips:
        return DailyMedStatsResponse(
            status="not_ready", reason=f"No .zip files found in {settings.display(folder)}.",
            fix="Put the DailyMed human Rx label zips (dm_spl_release_human_rx_part*.zip) in "
                "data/dailymed_rx.")
    infos = [ZipFileInfo(name=z.name, size_bytes=z.stat().st_size) for z in zips]
    summary = settings.artifacts_dir / DAILYMED_STATS_FILE
    if not summary.is_file():
        return DailyMedStatsResponse(
            status="not_ready", zip_files=infos,
            reason=f"{len(zips)} zip file(s) are present, but no label statistics have been "
                   f"computed yet ({settings.display(summary)} is missing).",
            fix=r"From the aakaash folder run: .venv\Scripts\python.exe scripts\dailymed_stats.py "
                "--max-labels-per-part 200 (sample) or without the cap (full).")
    try:
        raw = json.loads(summary.read_text(encoding="utf-8"))
        return DailyMedStatsResponse(status="ready", zip_files=infos, **raw)
    except (OSError, ValueError, ValidationError) as exc:
        return DailyMedStatsResponse(
            status="not_ready", zip_files=infos,
            reason=f"{settings.display(summary)} could not be read: "
                   f"{type(exc).__name__}: {settings.scrub(str(exc))}",
            fix="Regenerate the statistics file.")


# ---- TAC 2017 -----------------------------------------------------------------------------
def tac_stats(settings: Settings) -> TacStatsResponse:
    folder = settings.data_dir / TAC_DIRNAME
    if not folder.is_dir() or next(folder.rglob("*.xml"), None) is None:
        return TacStatsResponse(
            status="not_ready", reason=f"No .xml files found under {settings.display(folder)}.",
            fix="Put the TAC 2017 folders (train_xml, gold_xml, unannotated_xml) in data/tac2017.")
    s = tac2017.summarize(folder)
    return TacStatsResponse(
        status="ready", labels_per_split=s["splits"], section_names=s["section_names"],
        mention_types=s["mention_types"], relation_types=s["relation_types"],
        mentions=s["mentions"], relations=s["relations"], reactions=s["reactions"],
        labels_without_text=s["labels_without_text"], parse_failures=s["parse_failures"])
