# SOURCE: NOT IN PAPERS. Reads artifacts/names.json (scripts/build_names.py) and re-parses single
# labels from the DailyMed zips with medsafe.spl. Missing data gives status="not_ready"; nothing
# is invented. The brand search and the checker live in services/catalogue.py.
"""US label view (text tabs) and the same-active-moiety label list, by DailyMed set id."""
from __future__ import annotations

import io
import json
import threading
import zipfile
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException

from medsafe.forms import describe
from medsafe.names import NameIndex
from medsafe.spl import parse_label

from ..config import Settings
from ..schemas import Alternative, AlternativesResponse, LabelSection, MedicineResponse

NAMES_FILE = "names.json"
DAILYMED_DIRNAME = "dailymed_rx"
SECTION_ORDER = [("boxed_warning", "Boxed warning"), ("indications", "Indications"),
                 ("contraindications", "Contraindications"),
                 ("warnings_precautions", "Warnings and precautions"),
                 ("precautions", "Precautions"), ("drug_interactions", "Drug interactions"),
                 ("adverse_reactions", "Adverse reactions"),
                 ("specific_populations", "Use in specific populations")]

ALT_NOTE = ("Same active ingredient, matched on its active moiety. Not necessarily "
            "interchangeable. Confirm with a pharmacist.")

_lock = threading.Lock()
_index: dict[str, NameIndex] = {}


def clear_cache() -> None:
    with _lock:
        _index.clear()
    parse_cached.cache_clear()


def names_path(settings: Settings) -> Path:
    return settings.artifacts_dir / NAMES_FILE


def get_index(settings: Settings) -> NameIndex | None:
    """Load names.json once per process (on first request). None if the file is missing."""
    path = names_path(settings)
    if not path.is_file():
        return None
    key = f"{path.resolve()}|{path.stat().st_mtime_ns}"
    with _lock:
        if key not in _index:
            _index.clear()
            data = json.loads(path.read_text(encoding="utf-8"))
            _index[key] = NameIndex(data["labels"])
        return _index[key]


def _not_ready(cls, settings: Settings, **kw):
    return cls(status="not_ready",
               reason=f"The name index {settings.display(names_path(settings))} is missing.",
               fix="Run scripts/build_names.py from the aakaash folder.", **kw)


@lru_cache(maxsize=64)
def parse_cached(zip_path: str, source: str, member: str) -> dict:
    """Parse one label out of its (nested) zip. `source` is 'outer.zip!inner/path.zip'."""
    _, _, inner_name = source.partition("!")
    with zipfile.ZipFile(zip_path) as outer:
        if inner_name:
            with zipfile.ZipFile(io.BytesIO(outer.read(inner_name))) as inner:
                data = inner.read(member)
        else:
            data = outer.read(member)
    return parse_label(data, source, member)


def load_label(settings: Settings, idx: NameIndex, set_id: str) -> dict:
    i = idx.by_id.get(set_id)
    if i is None:
        raise HTTPException(404, f"No label with set id {set_id}.")
    rec = idx.labels[i]
    outer = rec["source"].partition("!")[0]
    zp = settings.data_dir / DAILYMED_DIRNAME / outer
    if not zp.is_file():
        raise HTTPException(503, f"The DailyMed zip {outer} is not in {settings.display(zp.parent)}.")
    return parse_cached(str(zp), rec["source"], rec["member"])


def medicine(settings: Settings, set_id: str) -> MedicineResponse:
    idx = get_index(settings)
    if idx is None:
        return _not_ready(MedicineResponse, settings, set_id=set_id)
    lab = load_label(settings, idx, set_id)
    sections = [LabelSection(key=k, label=name, text="\n\n".join(s["text"] for s in lab["sections"][k]))
                for k, name in SECTION_ORDER if lab["sections"].get(k)]
    return MedicineResponse(
        status="ready", set_id=set_id, title=lab["title"], products=lab["product_names"],
        generic_names=lab["generic_names"], manufacturer=lab["manufacturer"],
        ingredients=lab["ingredients_raw"], active_moieties=lab["active_moieties"],
        effective_time=lab["effective_time"], form=describe(lab.get("dosage_forms")), sections=[s for s in sections if s.text.strip()])


def alternatives(settings: Settings, set_id: str) -> AlternativesResponse:
    idx = get_index(settings)
    if idx is None:
        return _not_ready(AlternativesResponse, settings, set_id=set_id)
    if set_id not in idx.by_id:
        raise HTTPException(404, f"No label with set id {set_id}.")
    moi = idx.labels[idx.by_id[set_id]]["moieties"]
    rows = idx.alternatives(set_id)
    return AlternativesResponse(
        status="ready", set_id=set_id, active_moieties=moi, note=ALT_NOTE,
        total_labels=sum(r["label_count"] for r in rows),
        alternatives=[Alternative(**r) for r in rows])
