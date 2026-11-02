# SOURCE: NOT IN PAPERS. Reads artifacts/names.json (scripts/build_names.py) and re-parses single
# labels from the DailyMed zips with medsafe.spl. Missing data gives status="not_ready"; nothing
# is invented. The APPMS rule lookup (services/appms.py) is reported not_ready when data/appms
# is absent.
"""Name search, label view, same-active-moiety list and the pair checker."""
from __future__ import annotations

import io
import json
import threading
import time
import zipfile
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException

from medsafe import appms as appms_data
from medsafe.names import FUZZY_BACKEND, NameIndex, mentions, pairs
from medsafe.spl import parse_label

from ..config import Settings
from . import appms as appms_service
from ..schemas import (Alternative, AlternativesResponse, AppmsResult, CheckerMedicine,
                       CheckerResponse, LabelSection, MedicineResponse, PairResult, SuggestResponse,
                       Suggestion, TextMatch, TextMatchResult)

NAMES_FILE = "names.json"
DAILYMED_DIRNAME = "dailymed_rx"
SECTION_ORDER = [("boxed_warning", "Boxed warning"), ("indications", "Indications"),
                 ("contraindications", "Contraindications"),
                 ("warnings_precautions", "Warnings and precautions"),
                 ("precautions", "Precautions"), ("drug_interactions", "Drug interactions"),
                 ("adverse_reactions", "Adverse reactions"),
                 ("specific_populations", "Use in specific populations")]
TEXT_MATCH_LABEL = ("text match, not a clinical judgement. Class-level mentions (for example "
                    "'anticoagulants') are not detected.")
RULES_LABEL = "Interaction rules"
SEV_RANK = {"Critical": 0, "High": 1, "Moderate": 2}


def _rule_lookup(settings: Settings, data, a: dict, b: dict) -> AppmsResult:
    """Interaction rules for a pair of labels, matched on active moieties (any combination)."""
    if data is None:
        return AppmsResult(status="not_ready", source_label=RULES_LABEL,
                           reason="The interaction rules are not loaded.", fix=appms_service.FIX)
    hits = [r for x in a["active_moieties"] for y in b["active_moieties"]
            if (r := appms_data.find_rule(data, x, y))]
    if not hits:
        return AppmsResult(status="ready", source_label=RULES_LABEL)
    r = min(hits, key=lambda h: SEV_RANK[h.severity])
    return AppmsResult(status="ready", source_label=RULES_LABEL, severity=r.severity.lower(),
                       explanation=f"{r.interaction_category}. {r.mechanism_or_risk}. {r.explanation_or_action}.")
ALT_NOTE = ("Same active ingredient, matched on its active moiety. Not necessarily "
            "interchangeable. Confirm with a pharmacist.")
MAX_MATCHES_PER_PAIR = 12

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


def suggest(settings: Settings, q: str, limit: int) -> SuggestResponse:
    idx = get_index(settings)
    if idx is None:
        return _not_ready(SuggestResponse, settings, query=q)
    t0 = time.perf_counter()
    rows = idx.suggest(q, limit)
    ms = (time.perf_counter() - t0) * 1000
    return SuggestResponse(status="ready", query=q, matcher=FUZZY_BACKEND, elapsed_ms=round(ms, 2),
                           suggestions=[Suggestion(**r) for r in rows])


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
        effective_time=lab["effective_time"], sections=[s for s in sections if s.text.strip()])


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


def _med(lab: dict) -> CheckerMedicine:
    name = lab["product_names"][0] if lab["product_names"] else lab["title"]
    return CheckerMedicine(set_id=lab["set_id"], name=name, manufacturer=lab["manufacturer"],
                           active_moieties=lab["active_moieties"],
                           has_interactions_section=bool(lab["sections"].get("drug_interactions")))


def _interaction_text(lab: dict) -> str:
    return "\n".join(s["text"] for s in lab["sections"].get("drug_interactions", []))


def _text_match(a: dict, b: dict) -> TextMatchResult:
    found, notes = [], []
    for src, tgt in ((a, b), (b, a)):
        text = _interaction_text(src)
        src_med, tgt_med = _med(src), _med(tgt)
        if not text:
            notes.append(f"The label for {src_med.name} has no Drug Interactions section in the parsed text.")
            continue
        for m in mentions(text, tgt):
            found.append(TextMatch(sentence=m["sentence"], matched_term=m["matched_term"],
                                   in_label_set_id=src_med.set_id, in_label_name=src_med.name,
                                   section="Drug interactions", names_drug=tgt_med.name))
    total = len(found)
    return TextMatchResult(source_label=TEXT_MATCH_LABEL, matches=found[:MAX_MATCHES_PER_PAIR],
                           matches_total=total, notes=notes)


def check(settings: Settings, set_ids: list[str]) -> CheckerResponse:
    if len(set(set_ids)) != len(set_ids):
        raise HTTPException(422, "Each medicine can be added only once.")
    idx = get_index(settings)
    if idx is None:
        return _not_ready(CheckerResponse, settings)
    labels = {sid: load_label(settings, idx, sid) for sid in set_ids}
    out = []
    rules = appms_service.get_data(settings)
    rules_status = (AppmsResult(status="ready", source_label=RULES_LABEL) if rules is not None else
                    _rule_lookup(settings, None, {}, {}))
    for x, y in pairs(set_ids):
        a, b = labels[x], labels[y]
        shared = bool(set(a["active_moieties"]) & set(b["active_moieties"]))
        out.append(PairResult(a=_med(a), b=_med(b), appms=_rule_lookup(settings, rules, a, b),
                              text_match=_text_match(a, b), same_active_moiety=shared))
    # rule severity first (Critical, High, Moderate, unflagged); then more text matches first
    rank = {"critical": 0, "high": 1, "moderate": 2, None: 3}
    out.sort(key=lambda p: (rank[p.appms.severity], -p.text_match.matches_total))
    return CheckerResponse(status="ready", medicines=[_med(labels[s]) for s in set_ids],
                           appms=rules_status, pairs=out)
